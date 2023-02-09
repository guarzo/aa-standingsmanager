import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, Iterable, List, NamedTuple, Optional, Set, Tuple

from eveuniverse.models import EveEntity

from standingssync.app_settings import STANDINGSSYNC_WAR_TARGETS_LABEL_NAME


class EsiContactLabel(NamedTuple):
    id: int
    name: str

    def to_dict(self) -> dict:
        return {self.id: self.name}

    def to_esi_dict(self) -> dict:
        return {"label_id": self.id, "label_name": self.name}

    @classmethod
    def from_esi_dict(cls, esi_dict: dict):
        return cls(id=esi_dict["label_id"], name=esi_dict["label_name"])


@dataclass(unsafe_hash=True)
class EsiContact:
    """A contact in the ESI character contacts stub."""

    class ContactType(str, Enum):
        CHARACTER = "character"
        CORPORATION = "corporation"
        ALLIANCE = "alliance"

        @classmethod
        def from_esi_contact_type(cls, contact_type) -> "EsiContact.ContactType":
            mapper = {
                "character": cls.CHARACTER,
                "corporation": cls.CORPORATION,
                "alliance": cls.ALLIANCE,
            }
            return mapper[contact_type]

    contact_id: int
    contact_type: ContactType
    standing: float
    label_ids: FrozenSet[int] = field(default_factory=frozenset)

    def __setattr__(self, prop, val):
        if prop == "contact_id":
            val = int(val)
        if prop == "standing":
            val = float(val)
        if prop == "label_ids":
            if not val:
                val = []
            val = frozenset([int(obj) for obj in val])
        if prop == "contact_type":
            if val not in self.ContactType:
                raise ValueError(f"Invalid contact_type: {val}")
        super().__setattr__(prop, val)

    def to_esi_dict(self) -> dict:
        obj = {
            "contact_id": self.contact_id,
            "contact_type": self.ContactType(self.contact_type).value,
            "standing": self.standing,
        }
        if self.label_ids:
            obj["label_ids"] = sorted(list(self.label_ids))
        return obj

    @classmethod
    def from_esi_dict(cls, esi_dict: dict) -> "EsiContact":
        return cls(
            contact_id=esi_dict["contact_id"],
            contact_type=EsiContact.ContactType.from_esi_contact_type(
                esi_dict["contact_type"]
            ),
            standing=esi_dict["standing"],
            label_ids=esi_dict.get("label_ids"),
        )

    @classmethod
    def from_eve_entity(
        cls, eve_entity: EveEntity, standing: float, label_ids=None
    ) -> "EsiContact":
        """Create new instance from an EveEntity object."""
        contact_type_map = {
            EveEntity.CATEGORY_ALLIANCE: cls.ContactType.ALLIANCE,
            EveEntity.CATEGORY_CHARACTER: cls.ContactType.CHARACTER,
            EveEntity.CATEGORY_CORPORATION: cls.ContactType.CORPORATION,
        }
        return cls(
            contact_id=eve_entity.id,
            contact_type=contact_type_map[eve_entity.category],
            standing=standing,
            label_ids=label_ids,
        )

    @classmethod
    def from_eve_contact(cls, eve_contact: object, label_ids=None) -> "EsiContact":
        """Create new instance from an EveContact object."""
        contact_type_map = {
            EveEntity.CATEGORY_ALLIANCE: cls.ContactType.ALLIANCE,
            EveEntity.CATEGORY_CHARACTER: cls.ContactType.CHARACTER,
            EveEntity.CATEGORY_CORPORATION: cls.ContactType.CORPORATION,
        }
        return cls(
            contact_id=eve_contact.eve_entity.id,
            contact_type=contact_type_map[eve_contact.eve_entity.category],
            standing=eve_contact.standing,
            label_ids=label_ids,
        )

    @staticmethod
    def group_for_esi_update(
        contacts: List["EsiContact"],
    ) -> Dict[FrozenSet, Dict[float, Set[int]]]:
        """Group contacts for ESI update."""
        contacts_grouped = dict()
        for contact in contacts:
            if contact.label_ids not in contacts_grouped:
                contacts_grouped[contact.label_ids] = defaultdict(set)
            contacts_grouped[contact.label_ids][contact.standing].add(
                contact.contact_id
            )
        return contacts_grouped
        # return dict(sorted(contacts_by_standing.items()))


@dataclass
class EsiContactsClone:
    """Clone of ESI contacts for a character.

    This is needed to calculate the version hash after an update.
    The ESI contacts endpoint can not be used for this,
    because it is cached for several minutes.
    """

    character_id: int
    _contacts: Dict[int, EsiContact] = field(
        default_factory=dict, init=False, repr=False
    )
    _labels: Dict[int, EsiContactLabel] = field(
        default_factory=dict, init=False, repr=False
    )

    def add_label(self, label: EsiContactLabel):
        """Add contact label."""
        self._labels[label.id] = deepcopy(label)

    def add_contact(self, contact: EsiContact):
        """Add contact."""
        if contact.label_ids:
            for label_id in contact.label_ids:
                if label_id not in self._labels:
                    raise ValueError(f"Invalid label_id: {label_id}")
        self._contacts[contact.contact_id] = deepcopy(contact)

    def add_eve_contacts(self, contacts: List[object], label_ids: List[int] = None):
        for contact in contacts:
            self.add_contact(EsiContact.from_eve_contact(contact, label_ids=label_ids))

    def remove_contact(self, contact_id: int):
        """Remove contact."""
        try:
            del self._contacts[contact_id]
        except KeyError:
            raise RuntimeError(f"Contact with ID {contact_id} not found") from None

    def contacts(self) -> Set[EsiContact]:
        """Set of all contacts."""
        return set(self._contacts.values())

    def contact_ids(self) -> Set[int]:
        """Set of all contact IDs."""
        return set(self._contacts.keys())

    def war_target_label_id(self) -> Optional[int]:
        for label in self._labels.values():
            if label.name.lower() == STANDINGSSYNC_WAR_TARGETS_LABEL_NAME.lower():
                return label.id
        return None

    def contacts_difference(self, other: "EsiContactsClone") -> Tuple[set, set, set]:
        """Identify which contacts have been added, removed or changed."""
        current_contact_ids = set(self._contacts.keys())
        other_contact_ids = set(other._contacts.keys())
        removed = {
            contact
            for contact_id, contact in self._contacts.items()
            if contact_id in (current_contact_ids - other_contact_ids)
        }
        added = {
            contact
            for contact_id, contact in other._contacts.items()
            if contact_id in (other_contact_ids - current_contact_ids)
        }
        raw_difference = set(self._contacts.values()) - set(other._contacts.values())
        changed = raw_difference - removed
        return added, removed, changed

    def contacts_to_esi_dicts(self) -> List[dict]:
        return [
            obj.to_esi_dict()
            for obj in sorted(self._contacts.values(), key=lambda o: o.contact_id)
        ]

    def labels_to_esi_dicts(self) -> List[dict]:
        return [
            obj.to_esi_dict()
            for obj in sorted(self._labels.values(), key=lambda o: o.id)
        ]

    def _to_dict(self) -> dict:
        """Convert obj into a dictionary."""
        data = {
            "character_id": self.character_id,
            "contacts": self.contacts_to_esi_dicts(),
            "labels": self.labels_to_esi_dicts(),
        }
        return data

    def version_hash(self) -> str:
        """Calculate hash for current contacts in order to compare versions.

        Note that has is calculated for contacts only.
        """
        data = self.contacts_to_esi_dicts()
        return hashlib.md5(json.dumps(data).encode("utf-8")).hexdigest()

    @classmethod
    def from_esi_contacts(
        cls,
        character_id: int,
        contacts: Iterable[EsiContact],
        labels: Iterable[EsiContactLabel] = None,
    ):
        """Create new object from Esi contacts."""
        obj = cls(character_id)
        if labels:
            for label in labels:
                obj.add_label(label)
        for contact in contacts:
            obj.add_contact(contact)
        return obj

    @classmethod
    def from_esi_dicts(
        cls,
        character_id: int,
        contacts: Iterable[dict] = None,
        labels: Iterable[dict] = None,
    ):
        """Create new object from ESI contacts and labels."""
        obj = cls(character_id)
        if labels:
            for label in labels:
                obj.add_label(EsiContactLabel.from_esi_dict(label))
        if contacts:
            for contact in contacts:
                obj.add_contact(EsiContact.from_esi_dict(contact))
        return obj
