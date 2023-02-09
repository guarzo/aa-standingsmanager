"""Wrapper for handling all access to the ESI API."""

from typing import Dict, Iterable, List, Set

from esi.models import Token
from eveuniverse.models import EveEntity

from allianceauth.services.hooks import get_extension_logger
from app_utils.helpers import chunks
from app_utils.logging import LoggerAddTag

from standingssync import __title__
from standingssync.app_settings import (
    STANDINGSSYNC_MINIMUM_UNFINISHED_WAR_ID,
    STANDINGSSYNC_SPECIAL_WAR_IDS,
)
from standingssync.providers import esi

from .esi_contacts import EsiContact

logger = LoggerAddTag(get_extension_logger(__name__), __title__)

FETCH_WARS_MAX_ITEMS = 2000

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


def eve_entity_to_dict(eve_entity: EveEntity, standing: float) -> dict:
    """Convert EveEntity to ESI contact dict."""
    return {
        "contact_id": eve_entity.id,
        "contact_type": eve_entity.category,
        "standing": standing,
    }


def fetch_alliance_contacts(alliance_id: int, token: Token) -> Set[EsiContact]:
    """Fetch alliance contacts from ESI."""
    contacts_raw = esi.client.Contacts.get_alliances_alliance_id_contacts(
        token=token.valid_access_token(), alliance_id=alliance_id
    ).results()
    contacts = {
        int(row["contact_id"]): EsiContact.from_esi_dict(row) for row in contacts_raw
    }
    # add the sync alliance with max standing to contacts
    contacts[alliance_id] = EsiContact(
        contact_id=alliance_id,
        contact_type=EsiContact.ContactType.ALLIANCE,
        standing=10,
    )
    return set(contacts.values())


def fetch_character_contacts(token: Token) -> Dict[int, dict]:
    """Fetch character contacts from ESI."""
    logger.info("%s: Fetching current contacts", token.character_name)
    character_contacts_raw = esi.client.Contacts.get_characters_character_id_contacts(
        token=token.valid_access_token(), character_id=token.character_id
    ).results()
    character_contacts = {
        contact["contact_id"]: contact for contact in character_contacts_raw
    }
    return character_contacts


def fetch_character_contact_labels(token: Token) -> List[dict]:
    """Fetch contact labels for character from ESI."""
    logger.info("%s: Fetching current labels", token.character_name)
    labels = esi.client.Contacts.get_characters_character_id_contacts_labels(
        character_id=token.character_id, token=token.valid_access_token()
    ).results()
    return labels


def delete_character_contacts(token: Token, contact_ids: list):
    """Delete character contacts on ESI."""
    max_items = 20
    contact_ids_chunks = chunks(list(contact_ids), max_items)
    for contact_ids_chunk in contact_ids_chunks:
        esi.client.Contacts.delete_characters_character_id_contacts(
            token=token.valid_access_token(),
            character_id=token.character_id,
            contact_ids=contact_ids_chunk,
        ).results()


def add_character_contacts(
    token: Token,
    contacts_by_standing: Dict[float, Iterable[int]],
    label_ids: list = None,
) -> bool:
    """Add new character contacts on ESI.

    Returns False if not all contacts could be added.
    """
    return _update_character_contacts(
        token=token,
        contacts_by_standing=contacts_by_standing,
        esi_method=esi.client.Contacts.post_characters_character_id_contacts,
        label_ids=label_ids,
    )


def update_character_contacts(
    token: Token,
    contacts_by_standing: Dict[float, Iterable[int]],
    label_ids: list = None,
) -> bool:
    """Update existing character contacts on ESI.

    Returns False if not all contacts could be updated.
    """
    return _update_character_contacts(
        token=token,
        contacts_by_standing=contacts_by_standing,
        esi_method=esi.client.Contacts.put_characters_character_id_contacts,
        label_ids=label_ids,
    )


def _update_character_contacts(
    token: Token,
    contacts_by_standing: Dict[float, Iterable[int]],
    esi_method,
    label_ids: list = None,
) -> bool:
    """Add new or update existing character contacts on ESI."""
    max_items = 100
    requested_contact_ids = set()
    updated_contact_ids = set()
    for standing in contacts_by_standing:
        contact_ids = sorted(list(contacts_by_standing[standing]))
        requested_contact_ids.update(contact_ids)
        for contact_ids_chunk in chunks(contact_ids, max_items):
            params = {
                "token": token.valid_access_token(),
                "character_id": token.character_id,
                "contact_ids": contact_ids_chunk,
                "standing": standing,
            }
            if label_ids is not None:
                params["label_ids"] = sorted(list(label_ids))
            response = esi_method(**params).results()
            updated_contact_ids.update(response)

    result = updated_contact_ids == requested_contact_ids
    if not result:
        logger.warning(
            "%s: Failed to add/update contacts: %s",
            token.character_name,
            requested_contact_ids - updated_contact_ids,
        )
    return result


def fetch_war_ids() -> Set[int]:
    """Fetch IDs for new and unfinished wars from ESI.

    Will ignore older wars which are known to be already finished.
    """
    logger.info("Fetching war IDs from ESI")
    war_ids = []
    war_ids_page = esi.client.Wars.get_wars().results(ignore_cache=True)
    while True:
        war_ids += war_ids_page
        if (
            len(war_ids_page) < FETCH_WARS_MAX_ITEMS
            or min(war_ids_page) < STANDINGSSYNC_MINIMUM_UNFINISHED_WAR_ID
        ):
            break
        max_war_id = min(war_ids)
        war_ids_page = esi.client.Wars.get_wars(max_war_id=max_war_id).results(
            ignore_cache=True
        )
    war_ids = set(
        [
            war_id
            for war_id in war_ids
            if war_id >= STANDINGSSYNC_MINIMUM_UNFINISHED_WAR_ID
        ]
    )
    war_ids = war_ids.union(set(STANDINGSSYNC_SPECIAL_WAR_IDS))
    return war_ids


def fetch_war(war_id: int) -> dict:
    """Fetch details about a war from ESI."""
    logger.info("%d: Retrieving war", war_id)
    war_info = esi.client.Wars.get_wars_war_id(war_id=war_id).results(ignore_cache=True)
    return war_info
