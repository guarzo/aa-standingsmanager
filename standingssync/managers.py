from collections import defaultdict
from typing import Dict, Optional, Set, Tuple

from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import Exists, OuterRef
from django.utils.timezone import now
from eveuniverse.models import EveEntity

from allianceauth.eveonline.models import EveAllianceInfo
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from . import __title__
from .core import esi_api

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class EveContactQuerySet(models.QuerySet):
    def grouped_by_standing(self) -> Dict[int, models.Model]:
        """Group alliance contacts by standing and convert into sorted dict."""
        contacts_by_standing = defaultdict(set)
        for contact in self.all():
            contacts_by_standing[contact.standing].add(contact)
        return dict(sorted(contacts_by_standing.items()))


class EveContactManagerBase(models.Manager):
    pass


EveContactManager = EveContactManagerBase.from_queryset(EveContactQuerySet)


class EveWarQuerySet(models.QuerySet):
    def annotate_active_wars(self) -> models.QuerySet:
        from .models import EveWar

        return self.annotate(
            active=Exists(EveWar.objects.active_wars().filter(pk=OuterRef("pk")))
        )

    def active_wars(self) -> models.QuerySet:
        return self.filter(started__lt=now(), finished__gt=now()) | self.filter(
            started__lt=now(), finished__isnull=True
        )

    def finished_wars(self) -> models.QuerySet:
        return self.filter(finished__lte=now())


class EveWarManagerBase(models.Manager):
    def war_targets(self, alliance_id: int) -> models.QuerySet[EveEntity]:
        """Return list of current war targets for given alliance as EveEntity objects
        or an empty list if there are None.
        """
        war_target_ids = set()
        for war in self.active_wars():
            # case 1 alliance is aggressor
            if war.aggressor_id == alliance_id:
                war_target_ids.add(war.defender_id)
                if war.allies:
                    war_target_ids |= set(war.allies.values_list("id", flat=True))

            # case 2 alliance is defender
            if war.defender_id == alliance_id:
                war_target_ids.add(war.aggressor_id)

            # case 3 alliance is ally
            if war.allies.filter(id=alliance_id).exists():
                war_target_ids.add(war.aggressor_id)

        return EveEntity.objects.filter(id__in=war_target_ids)

    def update_or_create_from_esi(self, id: int) -> Tuple[models.Model, bool]:
        """Updates existing or creates new objects from ESI with given ID."""

        logger.info("Retrieving war details for ID %s", id)
        new_entity_ids = set()
        war_info = esi_api.fetch_war(war_id=id)
        aggressor_id = self._extract_id_from_war_participant(war_info["aggressor"])
        aggressor, _ = EveEntity.objects.get_or_create(id=aggressor_id)
        new_entity_ids.add(aggressor_id)
        defender_id = self._extract_id_from_war_participant(war_info["defender"])
        defender, _ = EveEntity.objects.get_or_create(id=defender_id)
        new_entity_ids.add(defender_id)
        with transaction.atomic():
            war, created = self.update_or_create(
                id=id,
                defaults={
                    "aggressor": aggressor,
                    "declared": war_info["declared"],
                    "defender": defender,
                    "is_mutual": war_info["mutual"],
                    "is_open_for_allies": war_info["open_for_allies"],
                    "retracted": war_info.get("retracted"),
                    "started": war_info.get("started"),
                    "finished": war_info.get("finished"),
                },
            )
            war.allies.clear()
            if war_info.get("allies"):
                for ally_info in war_info.get("allies"):
                    ally_id = self._extract_id_from_war_participant(ally_info)
                    ally, _ = EveEntity.objects.get_or_create(id=ally_id)
                    war.allies.add(ally)
                    new_entity_ids.add(ally_id)

        EveEntity.objects.bulk_create_esi(new_entity_ids)
        return war, created

    @staticmethod
    def _extract_id_from_war_participant(participant: dict) -> int:
        alliance_id = participant.get("alliance_id")
        corporation_id = participant.get("corporation_id")
        if not alliance_id and not corporation_id:
            raise ValueError(f"Invalid participant: {participant}")
        return alliance_id or corporation_id

    def fetch_active_war_ids_esi(self) -> Set[int]:
        """Fetch IDs of all currently active wars."""
        war_ids = esi_api.fetch_war_ids()
        finished_war_ids = set(self.finished_wars().values_list("id", flat=True))
        war_ids = set(war_ids)
        return war_ids.difference(finished_war_ids)


EveWarManager = EveWarManagerBase.from_queryset(EveWarQuerySet)


class SyncManagerManager(models.Manager):
    def fetch_for_user(self, user: User) -> Optional[models.Model]:
        """Fetch sync manager for given user. Return None if no match is found."""
        if not user.profile.main_character:
            return None
        try:
            alliance = EveAllianceInfo.objects.get(
                alliance_id=user.profile.main_character.alliance_id
            )
        except EveAllianceInfo.DoesNotExist:
            return None
        try:
            return self.get(alliance=alliance)
        except self.model.DoesNotExist:
            return None
