"""Settings for standingsmanager - Refactored for AA Standings Manager."""

import logging

from app_utils.app_settings import clean_setting

logger = logging.getLogger(__name__)


# ============================================================================
# Label Configuration
# ============================================================================

STANDINGS_LABEL_NAME = clean_setting("STANDINGS_LABEL_NAME", "ORGANIZATION")
"""Name of the EVE contact label for managed standings.

This label must be created by users in-game for each synced character.
The plugin will only manage contacts that have this label.

Default: "ORGANIZATION"
Examples: "COALITION", "BLUE DONUT", "FRIENDS", etc.
"""


# ============================================================================
# Sync Configuration
# ============================================================================

STANDINGS_SYNC_INTERVAL = clean_setting("STANDINGS_SYNC_INTERVAL", 30)
"""Sync interval in minutes.

How often the background task will sync all characters.

Default: 30 minutes
"""

STANDINGS_SYNC_TIMEOUT = clean_setting("STANDINGS_SYNC_TIMEOUT", 180)
"""Sync timeout in minutes.

Duration after which a delayed sync is reported as stale.
This value should be aligned with the frequency of the sync task.

Default: 180 minutes (3 hours)
"""


# ============================================================================
# Standing Configuration
# ============================================================================

STANDINGS_DEFAULT_STANDING = clean_setting(
    "STANDINGS_DEFAULT_STANDING", default_value=5.0, min_value=-10, max_value=10
)
"""Default standing value for approved entities.

When a standing request is approved without specifying a value,
this default will be used.

Default: 5.0
Range: -10.0 to +10.0
"""


# ============================================================================
# Scope Requirements
# ============================================================================

STANDINGS_SCOPE_REQUIREMENTS = clean_setting(
    "STANDINGS_SCOPE_REQUIREMENTS",
    {
        "Member": [
            "esi-characters.read_contacts.v1",
            "esi-characters.write_contacts.v1",
        ],
        "Blue": [
            "esi-characters.read_contacts.v1",
            "esi-characters.write_contacts.v1",
        ],
    },
)
"""Required ESI scopes per Alliance Auth state.

Define which ESI scopes are required for users in different Auth states
to request standings. This allows different scope requirements for
different user groups.

Format: Dict[str, List[str]]
- Key: Alliance Auth state name (e.g., "Member", "Blue")
- Value: List of required ESI scope names

Example:
{
    'Member': [
        'esi-characters.read_contacts.v1',
        'esi-characters.write_contacts.v1',
        'esi-assets.read_assets.v1',  # For verification
    ],
    'Blue': [
        'esi-characters.read_contacts.v1',
        'esi-characters.write_contacts.v1',
    ],
}

Default: Basic contact scopes for Member and Blue states
"""


# ============================================================================
# Auto-Validation Configuration
# ============================================================================

STANDINGS_AUTO_VALIDATE_INTERVAL = clean_setting(
    "STANDINGS_AUTO_VALIDATE_INTERVAL", 360
)
"""Auto-validation interval in minutes.

How often to validate that synced characters are still eligible
(have permissions, valid tokens, required scopes).

Characters that fail validation are automatically removed.

Default: 360 minutes (6 hours)
"""


# ============================================================================
# Debug Settings
# ============================================================================

STANDINGSSYNC_STORE_ESI_CONTACTS_ENABLED = clean_setting(
    "STANDINGSSYNC_STORE_ESI_CONTACTS_ENABLED", False
)
"""Whether to store contacts received from ESI to disk.

This is for debugging purposes only.

Default: False
"""


# ============================================================================
# Backward Compatibility (Deprecated)
# ============================================================================

# The following settings are from the old version and are no longer used.
# They are kept here for reference during migration but will be removed
# in a future version.

# DEPRECATED: War targets feature removed
# STANDINGSSYNC_ADD_WAR_TARGETS = False
# STANDINGSSYNC_WAR_TARGETS_LABEL_NAME = "WAR TARGETS"

# DEPRECATED: Alliance contacts replaced by persistent standings
# STANDINGSSYNC_ALLIANCE_CONTACTS_LABEL_NAME = "ALLIANCE"

# DEPRECATED: Contact modes replaced by single label-based mode
# STANDINGSSYNC_REPLACE_CONTACTS = "merge"

# DEPRECATED: Minimum standing replaced by approval workflow
# STANDINGSSYNC_CHAR_MIN_STANDING = 0.1

# DEPRECATED: War ID tracking removed
# STANDINGSSYNC_UNFINISHED_WARS_MINIMUM_ID = 719979
# STANDINGSSYNC_UNFINISHED_WARS_EXCEPTION_IDS = [...]


# ============================================================================
# Settings Validation
# ============================================================================


def validate_settings():
    """Validate app settings.

    Raises:
        ValueError: If any setting is invalid
    """
    # Validate label name
    if not STANDINGS_LABEL_NAME or not isinstance(STANDINGS_LABEL_NAME, str):
        raise ValueError("STANDINGS_LABEL_NAME must be a non-empty string")

    if len(STANDINGS_LABEL_NAME) > 50:
        raise ValueError("STANDINGS_LABEL_NAME must be 50 characters or less")

    # Validate sync interval
    if STANDINGS_SYNC_INTERVAL <= 0:
        raise ValueError("STANDINGS_SYNC_INTERVAL must be greater than 0")

    # Validate sync timeout
    if STANDINGS_SYNC_TIMEOUT <= 0:
        raise ValueError("STANDINGS_SYNC_TIMEOUT must be greater than 0")

    # Validate default standing
    if not -10.0 <= STANDINGS_DEFAULT_STANDING <= 10.0:
        raise ValueError("STANDINGS_DEFAULT_STANDING must be between -10.0 and +10.0")

    # Validate scope requirements
    if not isinstance(STANDINGS_SCOPE_REQUIREMENTS, dict):
        raise ValueError("STANDINGS_SCOPE_REQUIREMENTS must be a dictionary")

    for state, scopes in STANDINGS_SCOPE_REQUIREMENTS.items():
        if not isinstance(state, str):
            raise ValueError(
                f"STANDINGS_SCOPE_REQUIREMENTS keys must be strings, got: {type(state)}"
            )
        if not isinstance(scopes, list):
            raise ValueError(
                f"STANDINGS_SCOPE_REQUIREMENTS[{state}] must be a list, got: {type(scopes)}"
            )
        if not all(isinstance(scope, str) for scope in scopes):
            raise ValueError(
                f"STANDINGS_SCOPE_REQUIREMENTS[{state}] must contain only strings"
            )

    # Validate auto-validation interval
    if STANDINGS_AUTO_VALIDATE_INTERVAL <= 0:
        raise ValueError("STANDINGS_AUTO_VALIDATE_INTERVAL must be greater than 0")

    logger.info("All standings settings validated successfully")


# Run validation on import
try:
    validate_settings()
except ValueError as ex:
    logger.exception("Settings validation failed: %s", ex)
    raise
