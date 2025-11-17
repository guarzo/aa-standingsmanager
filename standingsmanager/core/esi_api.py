"""Wrapper for handling all access to the ESI API."""

import time
from collections import defaultdict
from typing import Callable, Dict, FrozenSet, Iterable, Optional, Set

from requests.exceptions import HTTPError

from esi.models import Token

from allianceauth.services.hooks import get_extension_logger
from app_utils.helpers import chunks
from app_utils.logging import LoggerAddTag

from standingsmanager import __title__
from standingsmanager.providers import esi

from .esi_contacts import EsiContact, EsiContactLabel

logger = LoggerAddTag(get_extension_logger(__name__), __title__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 1  # seconds
BACKOFF_MULTIPLIER = 2


def esi_retry(func):
    """Decorator to add retry logic with exponential backoff to ESI calls.

    Retries on rate limiting (429) and server errors (5xx).
    """

    def wrapper(*args, **kwargs):
        retries = 0
        backoff = INITIAL_BACKOFF

        while retries < MAX_RETRIES:
            try:
                return func(*args, **kwargs)
            except HTTPError as ex:
                status_code = ex.response.status_code if ex.response else None

                # Retry on rate limit or server errors
                if status_code in [429, 500, 502, 503, 504]:
                    retries += 1
                    if retries >= MAX_RETRIES:
                        logger.exception(
                            "ESI API call failed after %d retries: %s",
                            MAX_RETRIES,
                            ex,
                        )
                        raise

                    wait_time = backoff * (BACKOFF_MULTIPLIER ** (retries - 1))
                    logger.warning(
                        "ESI returned %s, retrying in %s seconds (attempt %d/%d)",
                        status_code,
                        wait_time,
                        retries,
                        MAX_RETRIES,
                    )
                    time.sleep(wait_time)
                else:
                    # Don't retry on client errors (4xx except 429)
                    raise
            except Exception as ex:
                logger.exception("ESI API call failed with unexpected error: %s", ex)
                raise

        return None

    return wrapper


# Alliance contacts function removed - not used in refactored AA Standings Manager
# New implementation syncs to individual characters, not alliance level


@esi_retry
def fetch_character_contacts(token: Token) -> Set[EsiContact]:
    """Fetch character contacts from ESI."""
    character_contacts_raw = esi.client.Contacts.get_characters_character_id_contacts(
        token=token.valid_access_token(), character_id=token.character_id
    ).results(ignore_cache=True)
    logger.info(
        "%s: Fetched %d current contacts",
        token.character_name,
        len(character_contacts_raw),
    )
    character_contacts = {
        EsiContact.from_esi_dict(contact) for contact in character_contacts_raw
    }
    return character_contacts


@esi_retry
def fetch_character_contact_labels(token: Token) -> Set[EsiContactLabel]:
    """Fetch contact labels for character from ESI."""
    labels_raw = esi.client.Contacts.get_characters_character_id_contacts_labels(
        character_id=token.character_id, token=token.valid_access_token()
    ).results(ignore_cache=True)
    logger.info("%s: Fetched %d current labels", token.character_name, len(labels_raw))
    labels = {EsiContactLabel.from_esi_dict(label) for label in labels_raw}
    return labels


@esi_retry
def delete_character_contacts(token: Token, contacts: Iterable[EsiContact]):
    """Delete character contacts on ESI."""
    max_items = 20
    contact_ids = sorted([contact.contact_id for contact in contacts])
    contact_ids_chunks = chunks(contact_ids, max_items)
    for contact_ids_chunk in contact_ids_chunks:
        esi.client.Contacts.delete_characters_character_id_contacts(
            token=token.valid_access_token(),
            character_id=token.character_id,
            contact_ids=contact_ids_chunk,
        ).results()

    logger.info("%s: Deleted %d contacts", token.character_name, len(contact_ids))


@esi_retry
def add_character_contacts(token: Token, contacts: Iterable[EsiContact]) -> None:
    """Add new contacts on ESI for a character."""
    _update_character_contacts(
        token=token,
        contacts=contacts,
        esi_method=esi.client.Contacts.post_characters_character_id_contacts,
    )
    logger.info("%s: Added %d contacts", token.character_name, len(contacts))


@esi_retry
def update_character_contacts(token: Token, contacts: Iterable[EsiContact]) -> None:
    """Update existing character contacts on ESI."""
    _update_character_contacts(
        token=token,
        contacts=contacts,
        esi_method=esi.client.Contacts.put_characters_character_id_contacts,
    )
    logger.info("%s: Updated %d contacts", token.character_name, len(contacts))


def _update_character_contacts(
    token: Token, contacts: Iterable[EsiContact], esi_method: Callable
) -> None:
    for (
        label_ids,
        contacts_by_standing,
    ) in _group_for_esi_update(contacts).items():
        _update_character_contacts_esi(
            token=token,
            contacts_by_standing=contacts_by_standing,
            esi_method=esi_method,
            label_ids=list(label_ids) if label_ids else None,
        )


def _update_character_contacts_esi(
    token: Token,
    contacts_by_standing: Dict[float, Iterable[int]],
    esi_method: Callable,
    label_ids: Optional[list] = None,
) -> None:
    """Add new or update existing character contacts on ESI."""
    max_items = 100
    for standing in contacts_by_standing:
        contact_ids = sorted(list(contacts_by_standing[standing]))
        for contact_ids_chunk in chunks(contact_ids, max_items):
            params = {
                "token": token.valid_access_token(),
                "character_id": token.character_id,
                "contact_ids": contact_ids_chunk,
                "standing": standing,
            }
            if label_ids is not None:
                params["label_ids"] = sorted(list(label_ids))
            esi_method(**params).results()


def _group_for_esi_update(
    contacts: Iterable["EsiContact"],
) -> Dict[FrozenSet, Dict[float, Iterable[int]]]:
    """Group contacts for ESI update."""
    contacts_grouped = {}
    for contact in contacts:
        if contact.label_ids not in contacts_grouped:
            contacts_grouped[contact.label_ids] = defaultdict(set)
        contacts_grouped[contact.label_ids][contact.standing].add(contact.contact_id)
    return contacts_grouped


# War functionality removed - not used in refactored AA Standings Manager
# War targets are no longer supported in the new implementation
