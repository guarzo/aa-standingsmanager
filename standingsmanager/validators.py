"""Validation logic for standingsmanager.

This module provides validation functions for scope requirements,
token validation, and corporation token coverage.
"""

from typing import List, Optional, Tuple

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from esi.models import Token

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo

from .app_settings import STANDINGS_SCOPE_REQUIREMENTS
from .models import SyncedCharacter


def get_required_scopes_for_user(user: User) -> List[str]:
    """Get required ESI scopes for a user based on their Auth state.

    Args:
        user: User object

    Returns:
        List of required scope strings
    """
    # Get user's main character's state
    try:
        main_character = user.profile.main_character
        if main_character and hasattr(main_character, "character_ownership"):
            state = main_character.character_ownership.user.profile.state
        else:
            # Fallback to user's current state
            state = user.profile.state
    except (AttributeError, ObjectDoesNotExist):
        state = None

    # Get base scopes (required for everyone)
    base_scopes = SyncedCharacter.get_esi_scopes()

    # Get additional scopes for this state
    if state and state.name in STANDINGS_SCOPE_REQUIREMENTS:
        additional_scopes = STANDINGS_SCOPE_REQUIREMENTS[state.name]
        return list(set(base_scopes + additional_scopes))

    return base_scopes


def character_has_required_scopes(
    character: EveCharacter, user: User
) -> Tuple[bool, List[str]]:
    """Check if a character has all required ESI scopes.

    Args:
        character: EveCharacter to check
        user: User who owns the character

    Returns:
        Tuple of (has_all_scopes: bool, missing_scopes: List[str])
    """
    required_scopes = get_required_scopes_for_user(user)

    # Get character's token
    try:
        token = (
            Token.objects.filter(
                user=user,
                character_id=character.character_id,
            )
            .require_valid()
            .first()
        )
    except Exception:
        # No valid token
        return False, required_scopes

    if not token:
        return False, required_scopes

    # Check which scopes are missing
    token_scopes = set(token.scopes.values_list("name", flat=True))
    required_scopes_set = set(required_scopes)
    missing_scopes = list(required_scopes_set - token_scopes)

    return len(missing_scopes) == 0, missing_scopes


def validate_character_token(character: EveCharacter, user: User) -> None:
    """Validate that a character has valid token with required scopes.

    Args:
        character: EveCharacter to validate
        user: User who owns the character

    Raises:
        ValidationError: If token is missing or doesn't have required scopes
    """
    # Check ownership
    if not CharacterOwnership.objects.filter(user=user, character=character).exists():
        raise ValidationError(f"You do not own character {character.character_name}")

    # Check scopes
    has_scopes, missing_scopes = character_has_required_scopes(character, user)

    if not has_scopes:
        scope_list = ", ".join(missing_scopes)
        raise ValidationError(
            f"Character {character.character_name} is missing required scopes: {scope_list}"
        )


def validate_corporation_token_coverage(
    corporation: EveCorporationInfo, user: User
) -> Tuple[bool, List[str]]:
    """Validate that user has tokens for all characters in a corporation.

    For corporation standing requests, users must have valid tokens with
    required scopes for ALL their characters in that corporation.

    Args:
        corporation: EveCorporationInfo to check
        user: User making the request

    Returns:
        Tuple of (has_full_coverage: bool, characters_without_tokens: List[str])

    Raises:
        ValidationError: If user has no characters in the corporation
    """
    # Get all user's characters in this corporation
    user_chars_in_corp = EveCharacter.objects.filter(
        character_ownership__user=user,
        corporation_id=corporation.corporation_id,
    )

    if not user_chars_in_corp.exists():
        raise ValidationError(
            f"You have no characters in {corporation.corporation_name}"
        )

    characters_without_tokens = []

    # Check each character
    for character in user_chars_in_corp:
        has_scopes, _ = character_has_required_scopes(character, user)
        if not has_scopes:
            characters_without_tokens.append(character.character_name)

    has_full_coverage = len(characters_without_tokens) == 0

    return has_full_coverage, characters_without_tokens


def validate_corporation_request(corporation: EveCorporationInfo, user: User) -> None:
    """Validate a corporation standing request.

    Args:
        corporation: EveCorporationInfo to request standing for
        user: User making the request

    Raises:
        ValidationError: If validation fails
    """
    has_coverage, missing_chars = validate_corporation_token_coverage(corporation, user)

    if not has_coverage:
        char_list = ", ".join(missing_chars)
        raise ValidationError(
            f"You must have valid tokens for ALL your characters in "
            f"{corporation.corporation_name}. Missing tokens for: {char_list}"
        )


def can_user_request_character_standing(
    character: EveCharacter, user: User
) -> Tuple[bool, Optional[str]]:
    """Check if a user can request standing for a character.

    Args:
        character: EveCharacter to check
        user: User making the request

    Returns:
        Tuple of (can_request: bool, error_message: Optional[str])
    """
    # Check user has basic permission
    if not user.has_perm("standingsmanager.add_syncedcharacter"):
        return False, "You do not have permission to request standings"

    # Check ownership
    if not CharacterOwnership.objects.filter(user=user, character=character).exists():
        return False, f"You do not own character {character.character_name}"

    # Check scopes
    has_scopes, missing_scopes = character_has_required_scopes(character, user)
    if not has_scopes:
        scope_list = ", ".join(missing_scopes)
        return (
            False,
            f"Character {character.character_name} is missing required scopes: {scope_list}",
        )

    # Check if already has standing
    from eveuniverse.models import EveEntity

    from .models import StandingRequest, StandingsEntry

    try:
        eve_entity = EveEntity.objects.get(id=character.character_id)
        if StandingsEntry.objects.filter(eve_entity=eve_entity).exists():
            return False, f"{character.character_name} already has a standing"
    except EveEntity.DoesNotExist:
        pass

    # Check if already has pending request
    try:
        eve_entity = EveEntity.objects.get(id=character.character_id)
        if StandingRequest.objects.filter(
            eve_entity=eve_entity, state="pending"
        ).exists():
            return (
                False,
                f"A pending request already exists for {character.character_name}",
            )
    except EveEntity.DoesNotExist:
        pass

    return True, None


def can_user_request_corporation_standing(
    corporation: EveCorporationInfo, user: User
) -> Tuple[bool, Optional[str]]:
    """Check if a user can request standing for a corporation.

    Args:
        corporation: EveCorporationInfo to check
        user: User making the request

    Returns:
        Tuple of (can_request: bool, error_message: Optional[str])
    """
    # Check user has basic permission
    if not user.has_perm("standingsmanager.add_syncedcharacter"):
        return False, "You do not have permission to request standings"

    # Check token coverage
    try:
        has_coverage, missing_chars = validate_corporation_token_coverage(
            corporation, user
        )
        if not has_coverage:
            char_list = ", ".join(missing_chars)
            return (
                False,
                f"You must have valid tokens for ALL your characters. Missing: {char_list}",
            )
    except ValidationError as e:
        return False, str(e)

    # Check if already has standing
    from eveuniverse.models import EveEntity

    from .models import StandingRequest, StandingsEntry

    try:
        eve_entity = EveEntity.objects.get(id=corporation.corporation_id)
        if StandingsEntry.objects.filter(eve_entity=eve_entity).exists():
            return False, f"{corporation.corporation_name} already has a standing"
    except EveEntity.DoesNotExist:
        pass

    # Check if already has pending request
    try:
        eve_entity = EveEntity.objects.get(id=corporation.corporation_id)
        if StandingRequest.objects.filter(
            eve_entity=eve_entity, state="pending"
        ).exists():
            return (
                False,
                f"A pending request already exists for {corporation.corporation_name}",
            )
    except EveEntity.DoesNotExist:
        pass

    return True, None
