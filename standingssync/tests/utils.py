"""Utility functions and classes for tests"""

from dataclasses import dataclass
from typing import Iterable, Set
from unittest.mock import MagicMock

from eveuniverse.models import EveEntity

from allianceauth.eveonline.models import (
    EveAllianceInfo,
    EveCharacter,
    EveCorporationInfo,
)
from app_utils.esi_testing import BravadoOperationStub, build_http_error

from standingssync.core.esi_contacts import (
    EsiContact,
    EsiContactLabel,
    EsiContactsContainer,
)


def create_esi_contact(eve_entity: EveEntity, standing: int = 5.0) -> dict:
    if standing < -10 or standing > 10:
        raise ValueError(f"Invalid standing: {standing}")
    params = {
        "contact_id": int(eve_entity.id),
        "contact_type": eve_entity.category,
        "standing": float(standing),
    }
    return params


ALLIANCE_CONTACTS = [
    {"contact_id": 1002, "contact_type": "character", "standing": 10.0},
    {"contact_id": 1004, "contact_type": "character", "standing": 10.0},
    {"contact_id": 1005, "contact_type": "character", "standing": -10.0},
    {"contact_id": 1012, "contact_type": "character", "standing": -10.0},
    {"contact_id": 1013, "contact_type": "character", "standing": -5.0},
    {"contact_id": 1014, "contact_type": "character", "standing": 0.0},
    {"contact_id": 1015, "contact_type": "character", "standing": 5.0},
    {"contact_id": 1016, "contact_type": "character", "standing": 10.0},
    {"contact_id": 2011, "contact_type": "corporation", "standing": -10.0},
    {"contact_id": 2012, "contact_type": "corporation", "standing": -5.0},
    {"contact_id": 2014, "contact_type": "corporation", "standing": 0.0},
    {"contact_id": 2013, "contact_type": "corporation", "standing": 5.0},
    {"contact_id": 2015, "contact_type": "corporation", "standing": 10.0},
    {"contact_id": 3011, "contact_type": "alliance", "standing": -10.0},
    {"contact_id": 3012, "contact_type": "alliance", "standing": -5.0},
    {"contact_id": 3013, "contact_type": "alliance", "standing": 0.0},
    {"contact_id": 3014, "contact_type": "alliance", "standing": 5.0},
    {"contact_id": 3015, "contact_type": "alliance", "standing": 10.0},
]


def load_eve_entities():
    auth_to_eve_entities()
    map_to_category = {
        "alliance": EveEntity.CATEGORY_ALLIANCE,
        "corporation": EveEntity.CATEGORY_CORPORATION,
        "character": EveEntity.CATEGORY_CHARACTER,
    }
    for info in ALLIANCE_CONTACTS:
        EveEntity.objects.get_or_create(
            id=info["contact_id"],
            defaults={
                "category": map_to_category[info["contact_type"]],
                "name": f"dummy_{info['contact_id']}",
            },
        )


def auth_to_eve_entities():
    """Creates EveEntity objects from existing Auth objects."""
    for obj in EveAllianceInfo.objects.all():
        EveEntity.objects.get_or_create(
            id=obj.alliance_id,
            defaults={
                "name": obj.alliance_name,
                "category": EveEntity.CATEGORY_ALLIANCE,
            },
        )
    for obj in EveCorporationInfo.objects.all():
        EveEntity.objects.get_or_create(
            id=obj.corporation_id,
            defaults={
                "name": obj.corporation_name,
                "category": EveEntity.CATEGORY_CORPORATION,
            },
        )
    for obj in EveCharacter.objects.all():
        EveEntity.objects.get_or_create(
            id=obj.character_id,
            defaults={
                "name": obj.character_name,
                "category": EveEntity.CATEGORY_CHARACTER,
            },
        )


@dataclass
class EsiCharacterContactsStub:
    """Simulates the contacts for a character on ESI"""

    _character_id: int
    _contacts: EsiContactsContainer = None

    def contacts(self) -> Set[EsiContact]:
        return self._contacts.contacts()

    def contact_ids(self) -> Set[int]:
        return {contact.contact_id for contact in self._contacts.contacts()}

    def _setup_esi_mock(self, mock_esi):
        """Sets the mock for ESI to this object."""
        mock_esi.client.Contacts.get_characters_character_id_contacts.side_effect = (
            self._esi_get_characters_character_id_contacts
        )
        mock_esi.client.Contacts.delete_characters_character_id_contacts.side_effect = (
            self._esi_delete_characters_character_id_contacts
        )
        mock_esi.client.Contacts.post_characters_character_id_contacts = (
            self._esi_post_characters_character_id_contacts
        )
        mock_esi.client.Contacts.put_characters_character_id_contacts = (
            self._esi_put_characters_character_id_contacts
        )
        mock_esi.client.Contacts.get_characters_character_id_contacts_labels = (
            self._esi_get_characters_character_id_contacts_labels
        )

    def _setup_contacts(self, contacts):
        for contact in contacts:
            self._contacts.add_contact(contact)

    def _setup_labels(self, labels):
        for label in labels:
            self._contacts.add_label(label)

    @classmethod
    def create(
        cls,
        character_id: int,
        mock_esi: MagicMock,
        *,
        contacts: Iterable[EsiContact] = None,
        labels: Iterable[EsiContactLabel] = None,
    ) -> "EsiCharacterContactsStub":
        """Create new obj for tests."""
        obj = cls(character_id, EsiContactsContainer())
        if labels:
            obj._setup_labels(labels)
        if contacts:
            obj._setup_contacts(contacts)
        if mock_esi:
            obj._setup_esi_mock(mock_esi)
        return obj

    def _esi_get_characters_character_id_contacts(self, character_id, token, page=None):
        self._assert_correct_character(character_id)
        contacts = sorted(
            [obj.to_esi_dict() for obj in self._contacts.contacts()],
            key=lambda obj: obj["contact_id"],
        )
        return BravadoOperationStub(contacts)

    def _esi_get_characters_character_id_contacts_labels(
        self, character_id, token, page=None
    ):
        self._assert_correct_character(character_id)
        labels = sorted(
            [label.to_esi_dict() for label in self._contacts.labels()],
            key=lambda obj: obj["label_id"],
        )
        return BravadoOperationStub(labels)

    def _esi_post_characters_character_id_contacts(
        self, character_id, contact_ids, standing, token, label_ids=None
    ):
        self._assert_correct_character(character_id)
        self._check_label_ids_valid(character_id, label_ids)
        contact_type_map = {
            EveEntity.CATEGORY_CHARACTER: EsiContact.ContactType.CHARACTER,
            EveEntity.CATEGORY_CORPORATION: EsiContact.ContactType.CORPORATION,
            EveEntity.CATEGORY_ALLIANCE: EsiContact.ContactType.ALLIANCE,
        }
        for contact_id in contact_ids:
            eve_entity = EveEntity.objects.get(id=contact_id)
            self._contacts.add_contact(
                EsiContact(
                    contact_id=contact_id,
                    contact_type=contact_type_map[eve_entity.category],
                    standing=standing,
                    label_ids=label_ids if label_ids else [],
                )
            )
        return BravadoOperationStub(contact_ids)

    def _esi_put_characters_character_id_contacts(
        self, character_id, contact_ids, standing, token, label_ids=None
    ):
        self._assert_correct_character(character_id)
        self._check_label_ids_valid(character_id, label_ids)
        for contact_id in contact_ids:
            try:
                old_contact = self._contacts.contact_by_id(contact_id)
            except ValueError:
                continue
            params = {"standing": standing}
            if label_ids:
                params["label_ids"] = list(old_contact.label_ids) + list(label_ids)
            new_contact = old_contact.clone(**params)
            self._contacts.remove_contact(old_contact)
            self._contacts.add_contact(new_contact)
        return BravadoOperationStub(None)

    def _esi_delete_characters_character_id_contacts(
        self, character_id, contact_ids, token
    ):
        self._assert_correct_character(character_id)
        for contact_id in contact_ids:
            try:
                contact = self._contacts.contact_by_id(contact_id)
            except ValueError:
                continue
            self._contacts.remove_contact(contact)
        return BravadoOperationStub([])

    def _assert_correct_character(self, character_id: int):
        if character_id != self._character_id:
            raise build_http_error(404, f"Unknown character ID: {character_id}")

    def _check_label_ids_valid(self, character_id, label_ids):
        if label_ids:
            for label_id in label_ids:
                self._contacts.label_by_id(label_id)
