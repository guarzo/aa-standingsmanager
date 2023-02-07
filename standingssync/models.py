import datetime as dt
import hashlib
import json
from typing import Optional

from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.utils.timezone import now
from esi.errors import TokenExpiredError, TokenInvalidError
from esi.models import Token
from eveuniverse.models import EveEntity

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveAllianceInfo, EveCharacter
from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from . import __title__
from .app_settings import (
    STANDINGSSYNC_ADD_WAR_TARGETS,
    STANDINGSSYNC_CHAR_MIN_STANDING,
    STANDINGSSYNC_REPLACE_CONTACTS,
    STANDINGSSYNC_TIMEOUT_CHARACTER_SYNC,
    STANDINGSSYNC_TIMEOUT_MANAGER_SYNC,
)
from .core import esi_contacts
from .managers import EveContactManager, EveWarManager

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class SyncManager(models.Model):
    """An object for managing syncing of contacts for an alliance"""

    character_ownership = models.OneToOneField(
        CharacterOwnership, on_delete=models.SET_NULL, null=True, default=None
    )  # alliance contacts are fetched from this character
    alliance = models.OneToOneField(
        EveAllianceInfo, on_delete=models.CASCADE, primary_key=True, related_name="+"
    )
    last_update_at = models.DateTimeField(null=True, default=None)
    version_hash = models.CharField(max_length=32, default="")

    def __str__(self):
        return str(self.alliance)

    @property
    def character_alliance_id(self) -> int:
        return self.character_ownership.character.alliance_id

    @property
    def is_sync_fresh(self) -> bool:
        deadline = now() - dt.timedelta(minutes=STANDINGSSYNC_TIMEOUT_MANAGER_SYNC)
        return self.last_update_at > deadline

    def effective_standing_with_character(self, character: EveCharacter) -> float:
        """Effective standing of the alliance with a character."""

        try:
            return self.contacts.get(eve_entity_id=character.character_id).standing
        except EveContact.DoesNotExist:
            pass
        try:
            return self.contacts.get(eve_entity_id=character.corporation_id).standing
        except EveContact.DoesNotExist:
            pass
        if character.alliance_id:
            try:
                return self.contacts.get(eve_entity_id=character.alliance_id).standing
            except EveContact.DoesNotExist:
                pass
        return 0.0

    def update_from_esi(self, force_sync: bool = False) -> str:
        """Update this sync manager from ESi

        Args:
        - force_sync: will ignore version_hash if set to true

        Returns:
        - newest version hash on success (or raises exception on error)
        """
        if self.character_ownership is None:
            raise RuntimeError(f"{self}: Can not sync. No character configured.")
        if not self.character_ownership.user.has_perm("standingssync.add_syncmanager"):
            raise RuntimeError(
                f"{self}: Can not sync. Character does not have sufficient permission."
            )
        token = self._fetch_token()
        if not token:
            raise RuntimeError(f"{self}: Can not sync. No valid token found.")
        new_version_hash = self._perform_update_from_esi(token, force_sync)
        return new_version_hash

    def _fetch_token(self) -> Token:
        token = (
            Token.objects.filter(
                user=self.character_ownership.user,
                character_id=self.character_ownership.character.character_id,
            )
            .require_scopes(self.get_esi_scopes())
            .require_valid()
            .first()
        )
        return token

    def _perform_update_from_esi(self, token: Token, force_sync: bool) -> str:
        """Update alliance contacts incl. war targets."""
        contacts = esi_contacts.fetch_alliance_contacts(
            self.alliance.alliance_id, token
        )
        war_target_ids = self._add_war_targets(contacts)
        new_version_hash = self._calculate_version_hash(contacts)
        if force_sync or new_version_hash != self.version_hash:
            with transaction.atomic():
                self.contacts.all().delete()
                contacts = [
                    EveContact(
                        manager=self,
                        eve_entity=EveEntity.objects.get_or_create(id=contact_id)[0],
                        standing=contact["standing"],
                        is_war_target=contact_id in war_target_ids,
                    )
                    for contact_id, contact in contacts.items()
                ]
                EveContact.objects.bulk_create(contacts, batch_size=500)
                self.version_hash = new_version_hash
                self.save()
                logger.info(
                    "%s: Stored alliance update with %d contacts", self, len(contacts)
                )
        else:
            logger.info("%s: Alliance contacts are unchanged.", self)

        self.last_update_at = now()
        self.save()
        return new_version_hash

    def _add_war_targets(self, contacts: dict):
        """Add war targets to contacts (if enabled).

        Returns contact IDs of war targets.
        """
        if not STANDINGSSYNC_ADD_WAR_TARGETS:
            return set()
        war_targets = EveWar.objects.war_targets(self.character_alliance_id)
        for war_target in war_targets:
            contacts[war_target.id] = esi_contacts.eve_entity_to_dict(war_target, -10.0)
        return {war_target.id for war_target in war_targets}

    @staticmethod
    def _calculate_version_hash(contacts: dict) -> str:
        """Calculate hash for contacts."""
        return hashlib.md5(json.dumps(contacts).encode("utf-8")).hexdigest()

    @classmethod
    def get_esi_scopes(cls) -> list:
        return ["esi-alliances.read_contacts.v1"]


class SyncedCharacter(models.Model):
    """A character that has his personal contacts synced with an alliance"""

    character_ownership = models.OneToOneField(
        CharacterOwnership, on_delete=models.CASCADE, primary_key=True
    )
    has_war_targets_label = models.BooleanField(default=None, null=True)
    last_update_at = models.DateTimeField(null=True, default=None)
    manager = models.ForeignKey(
        SyncManager, on_delete=models.CASCADE, related_name="synced_characters"
    )
    version_hash_manager = models.CharField(max_length=32, default="")
    version_hash_character = models.CharField(max_length=32, default="")

    def __str__(self):
        try:
            character_name = self.character_ownership.character.character_name
        except ObjectDoesNotExist:
            character_name = f"[{self.pk}]"
        return f"{character_name} - {self.manager}"

    @property
    def character(self) -> EveCharacter:
        return self.character_ownership.character

    @property
    def character_id(self) -> int:
        return self.character.character_id

    @property
    def is_sync_fresh(self) -> bool:
        if not self.last_update_at:
            return False
        deadline = now() - dt.timedelta(minutes=STANDINGSSYNC_TIMEOUT_CHARACTER_SYNC)
        return self.last_update_at > deadline

    def get_status_message(self):
        if self.is_sync_fresh:
            return "OK"
        return "Sync is outdated."

    def update(self, force_sync: bool = False) -> bool:
        """updates in-game contacts for given character

        Will delete the sync character if necessary,
        e.g. if token is no longer valid or character is no longer blue

        Args:
        - force_sync: will ignore version_hash if set to true

        Returns:
        - False when the sync character was deleted
        - None when no update was needed
        - True when update was done successfully
        """
        logger.info("%s: Updating character", self)
        if not self._has_owner_permissions():
            return False
        if not force_sync and not self._is_update_needed():
            return None
        token = self._fetch_token()
        if not token:
            logger.error("%s: Can not sync. No valid token found.", self)
            return False
        if not self.manager.contacts.exists():
            logger.info("%s: No contacts to sync", self)
            return None
        if not self._has_character_standing():
            return False

        character_contacts = esi_contacts.fetch_character_contacts(token)
        wt_label_id = esi_contacts.determine_character_wt_label_id(token)
        if wt_label_id:
            logger.debug("%s: Has war target label", self)
            self.has_war_targets_label = True
            self.save()
        else:
            logger.debug("%s: Does not have war target label", self)
            self.has_war_targets_label = False
            self.save()

        if STANDINGSSYNC_REPLACE_CONTACTS:
            self._replace_character_contacts(token, character_contacts, wt_label_id)
        else:
            self._update_character_contacts(token, character_contacts, wt_label_id)

        self._store_new_version_hash()
        return True

    def _has_owner_permissions(self) -> bool:
        if not self.character_ownership.user.has_perm(
            "standingssync.add_syncedcharacter"
        ):
            logger.info(
                "%s: sync deactivated due to insufficient user permissions", self
            )
            self._deactivate_sync("you no longer have permission for this service")
            return False
        return True

    def _is_update_needed(self) -> bool:
        if self.manager.version_hash != self.version_hash_manager:
            return True
        logger.info("%s: contacts of this char are up-to-date, no sync required", self)
        self.last_update_at = now()
        self.save()
        return False

    def _fetch_token(self) -> Optional[Token]:
        try:
            token = (
                Token.objects.filter(
                    user=self.character_ownership.user,
                    character_id=self.character_ownership.character.character_id,
                )
                .require_scopes(self.get_esi_scopes())
                .require_valid()
                .first()
            )
        except TokenInvalidError:
            logger.info("%s: sync deactivated due to invalid token", self)
            self._deactivate_sync("your token is no longer valid")
            return None

        except TokenExpiredError:
            logger.info("%s: sync deactivated due to expired token", self)
            self._deactivate_sync("your token has expired")
            return None

        if token is None:
            logger.info("%s: can not find suitable token for synced char", self)
            self._deactivate_sync("you do not have a token anymore")
            return None

        return token

    def _deactivate_sync(self, message):
        message = (
            "Standings Sync has been deactivated for your "
            f"character {self}, because {message}.\n"
            "Feel free to activate sync for your character again, "
            "once the issue has been resolved."
        )
        notify(
            self.character_ownership.user,
            f"Standings Sync deactivated for {self}",
            message,
        )
        self.delete()

    def _has_character_standing(self) -> bool:
        character_eff_standing = self.manager.effective_standing_with_character(
            self.character_ownership.character
        )
        if character_eff_standing < STANDINGSSYNC_CHAR_MIN_STANDING:
            logger.info(
                "%s: sync deactivated because character is no longer considered blue. "
                f"It's standing is: {character_eff_standing}, "
                f"while STANDINGSSYNC_CHAR_MIN_STANDING is: {STANDINGSSYNC_CHAR_MIN_STANDING} ",
                self,
            )
            self._deactivate_sync(
                "your character is no longer blue with the alliance. "
                f"The standing value is: {character_eff_standing:.1f} "
            )
            return False
        return True

    def _replace_character_contacts(self, token, character_contacts, wt_label_id):
        logger.info("%s: Deleting current contacts", self)
        esi_contacts.delete_character_contacts(
            token=token, contact_ids=list(character_contacts.keys())
        )
        logger.info("%s: Adding alliance contacts", self)
        esi_contacts.add_character_contacts(
            token=token,
            contacts_by_standing=self.manager.contacts.exclude(
                eve_entity_id=self.character_id
            )
            .filter(is_war_target=False)
            .grouped_by_standing(),
        )
        if STANDINGSSYNC_ADD_WAR_TARGETS:
            logger.info("%s: Adding war targets", self)
            esi_contacts.add_character_contacts(
                token=token,
                contacts_by_standing=self.manager.contacts.filter(
                    is_war_target=True
                ).grouped_by_standing(),
                label_ids=[wt_label_id] if wt_label_id else None,
            )

    def _update_character_contacts(self, token, character_contacts, wt_label_id):
        qs_war_targets = self.manager.contacts.filter(is_war_target=True)

        # Handle outdated WTs
        character_wt_contacts = {
            contact_id
            for contact_id, contact in character_contacts.items()
            if contact.get("label_ids") and wt_label_id in contact["label_ids"]
        }
        current_wt_contacts = set(
            qs_war_targets.values_list("eve_entity_id", flat=True)
        )
        obsolete_wt_contacts = character_wt_contacts - current_wt_contacts
        if obsolete_wt_contacts:
            logger.info("%s: Remove obsolete WT contacts", self)
            esi_contacts.delete_character_contacts(token, obsolete_wt_contacts)

        qs_non_war_targets = self.manager.contacts.filter(is_war_target=False)
        logger.info("%s: Update existing contacts", self)
        contacts_by_standing = qs_non_war_targets.filter(
            eve_entity_id__in=character_contacts.keys()
        ).grouped_by_standing()
        esi_contacts.update_character_contacts(
            token=token, contacts_by_standing=contacts_by_standing
        )
        logger.info("%s: Add new contacts", self)
        contacts_by_standing = (
            qs_non_war_targets.exclude(eve_entity_id__in=character_contacts.keys())
            .exclude(eve_entity_id=self.character_id)
            .grouped_by_standing()
        )
        esi_contacts.add_character_contacts(
            token=token, contacts_by_standing=contacts_by_standing
        )

        if STANDINGSSYNC_ADD_WAR_TARGETS and qs_war_targets.exists():
            logger.info("%s: Update existing contacts to war target", self)
            contacts_by_standing = qs_war_targets.filter(
                eve_entity_id__in=character_contacts.keys()
            ).grouped_by_standing()
            esi_contacts.update_character_contacts(
                token=token,
                contacts_by_standing=contacts_by_standing,
                label_ids=[wt_label_id] if wt_label_id else None,
            )
            logger.info("%s: Add new war target contacts", self)
            contacts_by_standing = qs_war_targets.exclude(
                eve_entity_id__in=character_contacts.keys()
            ).grouped_by_standing()
            esi_contacts.add_character_contacts(
                token=token,
                contacts_by_standing=contacts_by_standing,
                label_ids=[wt_label_id] if wt_label_id else None,
            )

    def _store_new_version_hash(self):
        self.version_hash_manager = self.manager.version_hash
        self.last_update_at = now()
        self.save()

    @staticmethod
    def get_esi_scopes() -> list:
        return ["esi-characters.read_contacts.v1", "esi-characters.write_contacts.v1"]


class EveContact(models.Model):
    """An Eve Online contact"""

    manager = models.ForeignKey(
        SyncManager, on_delete=models.CASCADE, related_name="contacts"
    )
    eve_entity = models.ForeignKey(
        EveEntity, on_delete=models.CASCADE, related_name="+"
    )
    standing = models.FloatField()
    is_war_target = models.BooleanField()

    objects = EveContactManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["manager", "eve_entity"], name="fk_eve_contact"
            )
        ]

    def __str__(self):
        return f"{self.eve_entity}"


class EveWar(models.Model):
    """An EveOnline war"""

    id = models.PositiveIntegerField(primary_key=True)
    aggressor = models.ForeignKey(EveEntity, on_delete=models.CASCADE, related_name="+")
    allies = models.ManyToManyField(EveEntity, related_name="+")
    declared = models.DateTimeField()
    defender = models.ForeignKey(EveEntity, on_delete=models.CASCADE, related_name="+")
    finished = models.DateTimeField(null=True, default=None, db_index=True)
    is_mutual = models.BooleanField()
    is_open_for_allies = models.BooleanField()
    retracted = models.DateTimeField(null=True, default=None)
    started = models.DateTimeField(null=True, default=None, db_index=True)

    objects = EveWarManager()

    def __str__(self) -> str:
        return f"{self.aggressor} vs. {self.defender}"
