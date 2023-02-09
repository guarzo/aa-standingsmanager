"""Wrapper for handling access to contacts on ESI."""

from typing import Dict, Iterable, List

from esi.models import Token
from eveuniverse.models import EveEntity

from allianceauth.services.hooks import get_extension_logger
from app_utils.helpers import chunks
from app_utils.logging import LoggerAddTag

from standingssync import __title__
from standingssync.providers import esi

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


def eve_entity_to_dict(eve_entity: EveEntity, standing: float) -> dict:
    """Convert EveEntity to ESI contact dict."""
    return {
        "contact_id": eve_entity.id,
        "contact_type": eve_entity.category,
        "standing": standing,
    }


def fetch_alliance_contacts(alliance_id: int, token: Token) -> Dict[int, dict]:
    """Fetch alliance contacts from ESI."""
    contacts_raw = esi.client.Contacts.get_alliances_alliance_id_contacts(
        token=token.valid_access_token(), alliance_id=alliance_id
    ).results()
    contacts = {int(row["contact_id"]): row for row in contacts_raw}
    # add the sync alliance with max standing to contacts
    contacts[alliance_id] = {
        "contact_id": alliance_id,
        "contact_type": "alliance",
        "standing": 10,
    }
    return contacts


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


# def determine_character_wt_label_id(token: Token) -> Optional[int]:
#     """Determine ID of the war target label for character contacts."""
#     labels_raw = fetch_character_contact_labels(token)
#     for row in labels_raw:
#         if (
#             row.get("label_name").lower()
#             == STANDINGSSYNC_WAR_TARGETS_LABEL_NAME.lower()
#         ):
#             wt_label_id = row.get("label_id")
#             break
#     else:
#         wt_label_id = None
#     logger.info(f"WT Label ID = {wt_label_id}")
#     return wt_label_id


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
