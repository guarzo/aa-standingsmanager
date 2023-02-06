"""Wrapper for handling access to wars on ESI."""

from typing import Set

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from standingssync import __title__
from standingssync.app_settings import (
    STANDINGSSYNC_MINIMUM_UNFINISHED_WAR_ID,
    STANDINGSSYNC_SPECIAL_WAR_IDS,
)
from standingssync.providers import esi

logger = LoggerAddTag(get_extension_logger(__name__), __title__)

FETCH_WARS_MAX_ITEMS = 2000


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
    logger.info("%: Retrieving war", war_id)
    war_info = esi.client.Wars.get_wars_war_id(war_id=war_id).results(ignore_cache=True)
    return war_info
