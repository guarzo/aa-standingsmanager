import datetime as dt
import hashlib
import json
from typing import Dict, Optional, Set

from django.conf import settings
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
from .core import esi_api
from .core.esi_contacts import EsiContact, EsiContactsClone
from .helpers import store_json
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
        current_contacts = {
            obj.contact_id: obj
            for obj in esi_api.fetch_alliance_contacts(self.alliance.alliance_id, token)
        }
        war_target_ids = self._add_war_targets(current_contacts)
        new_version_hash = self._calculate_version_hash(current_contacts)
        if force_sync or new_version_hash != self.version_hash:
            self._save_new_contacts(current_contacts, war_target_ids, new_version_hash)
        else:
            logger.info("%s: Alliance contacts are unchanged.", self)
        self.last_update_at = now()
        self.save()

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

    def _add_war_targets(self, contacts: Dict[int, EsiContact]) -> Set[int]:
        """Add war targets to contacts (if enabled).

        Returns contact IDs of war targets.
        """
        if not STANDINGSSYNC_ADD_WAR_TARGETS:
            return set()
        war_targets = EveWar.objects.war_targets(self.character_alliance_id)
        for war_target in war_targets:
            contacts[war_target.id] = EsiContact.from_eve_entity(war_target, -10.0)
        return {war_target.id for war_target in war_targets}

    def _save_new_contacts(
        self,
        current_contacts: Dict[int, EsiContact],
        war_target_ids: Set[int],
        new_version_hash: str,
    ):
        with transaction.atomic():
            self.contacts.all().delete()
            contacts = [
                EveContact(
                    manager=self,
                    eve_entity=EveEntity.objects.get_or_create(id=contact_id)[0],
                    standing=contact.standing,
                    is_war_target=contact_id in war_target_ids,
                )
                for contact_id, contact in current_contacts.items()
            ]
            EveContact.objects.bulk_create(contacts, batch_size=500)
            self.version_hash = new_version_hash
            self.save()
            logger.info(
                "%s: Stored alliance update with %d contacts", self, len(contacts)
            )

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
        if not self._has_character_standing():
            return False
        token = self._fetch_token()
        if not token:
            logger.error("%s: Can not sync. No valid token found.", self)
            return False
        if not self.manager.contacts.exists():
            logger.info("%s: No contacts to sync", self)
            return None

        current_contacts, labels = self._fetch_current_contacts(token)

        # check if we need to update
        if force_sync:
            logger.info("%s: Forced update requested.", self)
        elif not self._is_update_needed(current_contacts):
            logger.info("%s: contacts are current; no update required", self)
            return None

        # new contacts
        new_contacts = EsiContactsClone.from_esi_dicts(
            character_id=self.character_id, labels=labels
        )
        new_contacts.add_eve_contacts(
            self.manager.contacts.exclude(eve_entity_id=self.character_id).filter(
                is_war_target=False
            )
        )
        if STANDINGSSYNC_ADD_WAR_TARGETS:
            wt_label_id = current_contacts.war_target_label_id()
            if wt_label_id:
                logger.debug("%s: Has war target label", self)
                self.has_war_targets_label = True
                self.save()
            else:
                logger.debug("%s: Does not have war target label", self)
                self.has_war_targets_label = False
                self.save()
            new_contacts.add_eve_contacts(
                self.manager.contacts.filter(is_war_target=True),
                label_ids=[wt_label_id] if wt_label_id else None,
            )

        # update contacts on ESI
        if STANDINGSSYNC_REPLACE_CONTACTS:
            # added, removed, changed = current_contacts.contacts_difference(new_contacts)
            logger.info("%s: Adding missing contacts", self)
            for (
                label_ids,
                contacts_by_standing,
            ) in new_contacts.contacts_for_esi_update().items():
                esi_api.add_character_contacts(
                    token=token,
                    contacts_by_standing=contacts_by_standing,
                    label_ids=list(label_ids) if label_ids else None,
                )
            logger.info("%s: Deleting added contacts", self)
            esi_api.delete_character_contacts(
                token=token, contact_ids=current_contacts.contact_ids()
            )
        else:
            ...
            # self._update_character_contacts(token, contacts_clone)

        self._store_new_version_hash(new_contacts.version_hash())
        if settings.DEBUG:
            store_json(new_contacts._to_dict(), "new_contacts")
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

    def _is_update_needed(self, current_contacts) -> bool:
        """Determine if contacts have to be updated."""
        if self.version_hash_manager != self.manager.version_hash:
            logger.info("%s: manager contacts have changed. Update needed.", self)
            return True
        if self.version_hash_character != current_contacts.version_hash():
            logger.info("%s: character contacts have changes. Update needed.", self)
            return True
        if not self.is_sync_fresh:
            logger.info("%s: Data has become stale. Update needed.", self)
            return True
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

    def _fetch_current_contacts(self, token: Token):
        contacts = esi_api.fetch_character_contacts(token)
        labels = esi_api.fetch_character_contact_labels(token)
        current_contacts = EsiContactsClone.from_esi_dicts(
            character_id=self.character_id, contacts=contacts.values(), labels=labels
        )
        if settings.DEBUG:
            store_json(current_contacts._to_dict(), "current_contacts")
            logger.debug(
                "%s: new version hash: %s", self, current_contacts.version_hash()
            )
            logger.debug("%s: old version hash: %s", self, self.version_hash_character)
        return current_contacts, labels

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
            esi_api.delete_character_contacts(token, obsolete_wt_contacts)

        qs_non_war_targets = self.manager.contacts.filter(is_war_target=False)
        logger.info("%s: Update existing contacts", self)
        contacts_by_standing = qs_non_war_targets.filter(
            eve_entity_id__in=character_contacts.keys()
        ).grouped_by_standing()
        esi_api.update_character_contacts(
            token=token, contacts_by_standing=contacts_by_standing
        )
        logger.info("%s: Add new contacts", self)
        contacts_by_standing = (
            qs_non_war_targets.exclude(eve_entity_id__in=character_contacts.keys())
            .exclude(eve_entity_id=self.character_id)
            .grouped_by_standing()
        )
        esi_api.add_character_contacts(
            token=token, contacts_by_standing=contacts_by_standing
        )

        if STANDINGSSYNC_ADD_WAR_TARGETS and qs_war_targets.exists():
            logger.info("%s: Update existing contacts to war target", self)
            contacts_by_standing = qs_war_targets.filter(
                eve_entity_id__in=character_contacts.keys()
            ).grouped_by_standing()
            esi_api.update_character_contacts(
                token=token,
                contacts_by_standing=contacts_by_standing,
                label_ids=[wt_label_id] if wt_label_id else None,
            )
            logger.info("%s: Add new war target contacts", self)
            contacts_by_standing = qs_war_targets.exclude(
                eve_entity_id__in=character_contacts.keys()
            ).grouped_by_standing()
            esi_api.add_character_contacts(
                token=token,
                contacts_by_standing=contacts_by_standing,
                label_ids=[wt_label_id] if wt_label_id else None,
            )

    def _store_new_version_hash(self, version_has_character: str):
        self.version_hash_manager = self.manager.version_hash
        self.version_hash_character = version_has_character
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
