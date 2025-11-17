"""Views for standingsmanager."""

import csv

from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from . import __title__, tasks
from .app_settings import STANDINGS_LABEL_NAME
from .models import (
    EveEntity,
    StandingRequest,
    StandingRevocation,
    StandingsEntry,
    SyncedCharacter,
)
from .validators import (
    can_user_request_character_standing,
    can_user_request_corporation_standing,
    character_has_required_scopes,
    get_required_scopes_for_user,
    validate_corporation_token_coverage,
)

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


def common_context(ctx: dict) -> dict:
    """Return common context used by several views."""
    result = {
        "app_title": __title__,
        "page_title": "PLACEHOLDER",
        "label_name": STANDINGS_LABEL_NAME,
    }
    result.update(ctx)
    return result


# ============================================================================
# Main Navigation Views
# ============================================================================


@login_required
@permission_required("standingsmanager.add_syncedcharacter")
def index(request):
    """Render index page - redirect to request standings."""
    return redirect("standingsmanager:request_standings")


# ============================================================================
# User Views - Request Standings
# ============================================================================


@login_required
@permission_required("standingsmanager.add_syncedcharacter")
def request_standings(request):
    """
    View for users to request standings for their characters and corporations.

    Shows all user's characters with their status:
    - Already has standing
    - Pending request
    - Can request standing
    - Cannot request (missing scopes, etc.)
    """
    user = request.user

    # Get all user's characters
    character_ownerships = CharacterOwnership.objects.filter(
        user=user
    ).select_related("character")

    characters_data = []
    corporations_data = {}

    # Get required scopes for this user
    required_scopes = get_required_scopes_for_user(user)

    for co in character_ownerships:
        character = co.character
        character_id = character.character_id

        # Check if character has standing
        try:
            entity = EveEntity.objects.get(
                eve_id=character_id, entity_type=EveEntity.EntityType.CHARACTER
            )
            has_standing = StandingsEntry.objects.filter(eve_entity=entity).exists()
        except EveEntity.DoesNotExist:
            has_standing = False

        # Check if there's a pending request
        try:
            entity = EveEntity.objects.get(
                eve_id=character_id, entity_type=EveEntity.EntityType.CHARACTER
            )
            pending_request = StandingRequest.objects.filter(
                eve_entity=entity, state=StandingRequest.RequestState.PENDING
            ).exists()
        except EveEntity.DoesNotExist:
            pending_request = False

        # Check eligibility
        can_request, error_message = can_user_request_character_standing(character, user)

        # Check scopes
        has_scopes, missing_scopes = character_has_required_scopes(character, user)

        # Determine status
        if has_standing:
            status = "approved"
            status_text = "Approved"
            can_remove = True
        elif pending_request:
            status = "pending"
            status_text = "Pending Approval"
            can_remove = False
        elif can_request:
            status = "can_request"
            status_text = "Can Request"
            can_remove = False
        else:
            status = "cannot_request"
            status_text = error_message or "Cannot Request"
            can_remove = False

        character_data = {
            "id": character_id,
            "name": character.character_name,
            "portrait_url": character.portrait_url(),
            "corporation_name": character.corporation_name,
            "corporation_id": character.corporation_id,
            "corporation_ticker": character.corporation_ticker,
            "alliance_name": character.alliance_name or "",
            "alliance_ticker": character.alliance_ticker or "",
            "status": status,
            "status_text": status_text,
            "can_request": can_request,
            "can_remove": can_remove,
            "has_scopes": has_scopes,
            "missing_scopes": missing_scopes,
            "error_message": error_message,
        }
        characters_data.append(character_data)

        # Track corporations for corp-level requests
        corp_id = character.corporation_id
        if corp_id not in corporations_data:
            corporations_data[corp_id] = {
                "id": corp_id,
                "name": character.corporation_name,
                "ticker": character.corporation_ticker,
                "logo_url": f"https://images.evetech.net/corporations/{corp_id}/logo?size=64",
                "alliance_name": character.alliance_name or "",
                "characters": [],
                "character_count": 0,
            }
        corporations_data[corp_id]["characters"].append(character_data)
        corporations_data[corp_id]["character_count"] += 1

    # Process corporation data
    corporations_list = []
    for corp_data in corporations_data.values():
        corp_id = corp_data["id"]

        # Check if corporation has standing
        try:
            entity = EveEntity.objects.get(
                eve_id=corp_id, entity_type=EveEntity.EntityType.CORPORATION
            )
            has_standing = StandingsEntry.objects.filter(eve_entity=entity).exists()
        except EveEntity.DoesNotExist:
            has_standing = False

        # Check if there's a pending request
        try:
            entity = EveEntity.objects.get(
                eve_id=corp_id, entity_type=EveEntity.EntityType.CORPORATION
            )
            pending_request = StandingRequest.objects.filter(
                eve_entity=entity, state=StandingRequest.RequestState.PENDING
            ).exists()
        except EveEntity.DoesNotExist:
            pending_request = False

        # Check token coverage
        try:
            corp_info = EveCorporationInfo.objects.get(corporation_id=corp_id)
            has_full_coverage, missing_characters = validate_corporation_token_coverage(
                corp_info, user
            )
        except EveCorporationInfo.DoesNotExist:
            # Create corporation info if it doesn't exist
            corp_info = EveCorporationInfo.objects.create_corporation(corp_id)
            has_full_coverage, missing_characters = validate_corporation_token_coverage(
                corp_info, user
            )

        # Check eligibility
        can_request, error_message = can_user_request_corporation_standing(
            corp_info, user
        )

        # Determine status
        if has_standing:
            status = "approved"
            status_text = "Approved"
            can_remove = True
        elif pending_request:
            status = "pending"
            status_text = "Pending Approval"
            can_remove = False
        elif can_request:
            status = "can_request"
            status_text = "Can Request"
            can_remove = False
        else:
            status = "cannot_request"
            status_text = error_message or "Cannot Request"
            can_remove = False

        corp_data.update(
            {
                "status": status,
                "status_text": status_text,
                "can_request": can_request,
                "can_remove": can_remove,
                "has_full_coverage": has_full_coverage,
                "missing_characters": missing_characters,
                "error_message": error_message,
            }
        )
        corporations_list.append(corp_data)

    context = {
        "page_title": "Request Standings",
        "characters": characters_data,
        "corporations": corporations_list,
        "required_scopes": required_scopes,
    }

    return render(request, "standingsmanager/request.html", common_context(context))


# ============================================================================
# User Views - My Synced Characters
# ============================================================================


@login_required
@permission_required("standingsmanager.add_syncedcharacter")
def my_synced_characters(request):
    """
    View for users to manage their synced characters.

    Shows all user's characters and their sync status.
    """
    user = request.user

    # Get all user's characters
    character_ownerships = CharacterOwnership.objects.filter(
        user=user
    ).select_related("character")

    characters_data = []

    for co in character_ownerships:
        character = co.character
        character_id = character.character_id

        # Check if character is synced
        try:
            synced_char = SyncedCharacter.objects.get(character_ownership=co)
            is_synced = True
            has_label = synced_char.has_label
            last_sync_at = synced_char.last_sync_at
            last_error = synced_char.last_error
            is_fresh = synced_char.is_sync_fresh

            # Determine sync status
            if last_error:
                sync_status = "error"
                sync_status_text = f"Error: {last_error}"
            elif not has_label:
                sync_status = "no_label"
                sync_status_text = f"Missing label: {STANDINGS_LABEL_NAME}"
            elif is_fresh:
                sync_status = "fresh"
                sync_status_text = "Synced"
            else:
                sync_status = "stale"
                sync_status_text = "Needs sync"

        except SyncedCharacter.DoesNotExist:
            is_synced = False
            has_label = None
            last_sync_at = None
            last_error = None
            sync_status = "not_synced"
            sync_status_text = "Not synced"

        # Check if character has standing (required for sync)
        try:
            entity = EveEntity.objects.get(
                eve_id=character_id, entity_type=EveEntity.EntityType.CHARACTER
            )
            has_standing = StandingsEntry.objects.filter(eve_entity=entity).exists()
        except EveEntity.DoesNotExist:
            has_standing = False

        character_data = {
            "id": character_id,
            "name": character.character_name,
            "portrait_url": character.portrait_url(),
            "corporation_name": character.corporation_name,
            "corporation_ticker": character.corporation_ticker,
            "alliance_name": character.alliance_name or "",
            "is_synced": is_synced,
            "has_label": has_label,
            "last_sync_at": last_sync_at,
            "last_error": last_error,
            "sync_status": sync_status,
            "sync_status_text": sync_status_text,
            "has_standing": has_standing,
            "can_add_sync": has_standing and not is_synced,
            "can_remove_sync": is_synced,
            "synced_char_pk": synced_char.pk if is_synced else None,
        }
        characters_data.append(character_data)

    context = {
        "page_title": "My Synced Characters",
        "characters": characters_data,
        "label_name": STANDINGS_LABEL_NAME,
    }

    return render(request, "standingsmanager/sync.html", common_context(context))


# ============================================================================
# Approver Views - Manage Requests
# ============================================================================


@login_required
@permission_required("standingsmanager.approve_standings")
def manage_requests(request):
    """
    View for approvers to manage pending standing requests.

    Shows all pending requests with details about the requester.
    """
    # Get all pending requests
    pending_requests = (
        StandingRequest.objects.filter(state=StandingRequest.RequestState.PENDING)
        .select_related("eve_entity", "requested_by")
        .order_by("-request_date")
    )

    requests_data = []
    for req in pending_requests:
        entity = req.eve_entity
        requester = req.requested_by

        # Get entity details
        entity_name = entity.name
        entity_id = entity.eve_id
        entity_type = entity.entity_type

        # Get requester main character
        main_char = requester.profile.main_character if requester.profile else None

        request_data = {
            "pk": req.pk,
            "entity_id": entity_id,
            "entity_name": entity_name,
            "entity_type": entity_type,
            "entity_type_display": entity.get_entity_type_display(),
            "requester_name": requester.username,
            "requester_main": main_char.character_name if main_char else "Unknown",
            "requester_main_corporation": (
                main_char.corporation_name if main_char else ""
            ),
            "requester_main_alliance": main_char.alliance_name if main_char else "",
            "request_date": req.request_date,
            "age_days": (timezone.now() - req.request_date).days,
        }

        # Add entity-specific details
        if entity_type == EveEntity.EntityType.CHARACTER:
            request_data["portrait_url"] = (
                f"https://images.evetech.net/characters/{entity_id}/portrait?size=64"
            )
        elif entity_type == EveEntity.EntityType.CORPORATION:
            request_data["logo_url"] = (
                f"https://images.evetech.net/corporations/{entity_id}/logo?size=64"
            )
        elif entity_type == EveEntity.EntityType.ALLIANCE:
            request_data["logo_url"] = (
                f"https://images.evetech.net/alliances/{entity_id}/logo?size=64"
            )

        requests_data.append(request_data)

    context = {
        "page_title": "Manage Standing Requests",
        "requests": requests_data,
        "request_count": len(requests_data),
    }

    return render(
        request, "standingsmanager/manage_requests.html", common_context(context)
    )


@login_required
@permission_required("standingsmanager.approve_standings")
def manage_revocations(request):
    """
    View for approvers to manage pending standing revocations.

    Shows all pending revocations with details about the requester.
    """
    # Get all pending revocations
    pending_revocations = (
        StandingRevocation.objects.filter(
            state=StandingRevocation.RevocationState.PENDING
        )
        .select_related("eve_entity", "requested_by")
        .order_by("-request_date")
    )

    revocations_data = []
    for rev in pending_revocations:
        entity = rev.eve_entity
        requester = rev.requested_by

        # Get entity details
        entity_name = entity.name
        entity_id = entity.eve_id
        entity_type = entity.entity_type

        # Handle auto-revocations (system-initiated)
        if requester is None:
            requester_name = "System (Auto)"
            requester_main = "N/A"
            requester_main_corporation = ""
            requester_main_alliance = ""
        else:
            requester_name = requester.username
            main_char = requester.profile.main_character if requester.profile else None
            requester_main = main_char.character_name if main_char else "Unknown"
            requester_main_corporation = main_char.corporation_name if main_char else ""
            requester_main_alliance = main_char.alliance_name if main_char else ""

        revocation_data = {
            "pk": rev.pk,
            "entity_id": entity_id,
            "entity_name": entity_name,
            "entity_type": entity_type,
            "entity_type_display": entity.get_entity_type_display(),
            "requester_name": requester_name,
            "requester_main": requester_main,
            "requester_main_corporation": requester_main_corporation,
            "requester_main_alliance": requester_main_alliance,
            "request_date": rev.request_date,
            "reason": rev.get_reason_display(),
            "age_days": (timezone.now() - rev.request_date).days,
            "is_auto": requester is None,
        }

        # Add entity-specific details
        if entity_type == EveEntity.EntityType.CHARACTER:
            revocation_data["portrait_url"] = (
                f"https://images.evetech.net/characters/{entity_id}/portrait?size=64"
            )
        elif entity_type == EveEntity.EntityType.CORPORATION:
            revocation_data["logo_url"] = (
                f"https://images.evetech.net/corporations/{entity_id}/logo?size=64"
            )
        elif entity_type == EveEntity.EntityType.ALLIANCE:
            revocation_data["logo_url"] = (
                f"https://images.evetech.net/alliances/{entity_id}/logo?size=64"
            )

        revocations_data.append(revocation_data)

    context = {
        "page_title": "Manage Standing Revocations",
        "revocations": revocations_data,
        "revocation_count": len(revocations_data),
    }

    return render(
        request, "standingsmanager/manage_revocations.html", common_context(context)
    )


# ============================================================================
# Approver Views - View Standings
# ============================================================================


@login_required
@permission_required("standingsmanager.approve_standings")
def view_standings(request):
    """
    View for approvers to view all current standings.

    Shows all standings entries grouped by type.
    """
    # Get all standings
    all_standings = StandingsEntry.objects.select_related(
        "eve_entity", "added_by"
    ).order_by("entity_type", "eve_entity__name")

    # Group by entity type
    characters = []
    corporations = []
    alliances = []

    for standing in all_standings:
        entity = standing.eve_entity
        added_by = standing.added_by

        # Get added_by information, handling None case
        if added_by:
            added_by_username = added_by.username
            main_char = added_by.profile.main_character if added_by.profile else None
            added_by_main = main_char.character_name if main_char else "Unknown"
        else:
            added_by_username = "Unknown"
            added_by_main = "Unknown"

        standing_data = {
            "entity_id": entity.eve_id,
            "entity_name": entity.name,
            "entity_type": entity.entity_type,
            "standing": standing.standing,
            "added_by": added_by_username,
            "added_by_main": added_by_main,
            "added_date": standing.added_date,
            "notes": standing.notes,
        }

        # Add entity-specific details
        if entity.entity_type == EveEntity.EntityType.CHARACTER:
            standing_data["portrait_url"] = (
                f"https://images.evetech.net/characters/{entity.eve_id}/portrait?size=64"
            )
            characters.append(standing_data)
        elif entity.entity_type == EveEntity.EntityType.CORPORATION:
            standing_data["logo_url"] = (
                f"https://images.evetech.net/corporations/{entity.eve_id}/logo?size=64"
            )
            corporations.append(standing_data)
        elif entity.entity_type == EveEntity.EntityType.ALLIANCE:
            standing_data["logo_url"] = (
                f"https://images.evetech.net/alliances/{entity.eve_id}/logo?size=64"
            )
            alliances.append(standing_data)

    context = {
        "page_title": "View Standings",
        "characters": characters,
        "corporations": corporations,
        "alliances": alliances,
        "total_count": len(all_standings),
        "character_count": len(characters),
        "corporation_count": len(corporations),
        "alliance_count": len(alliances),
    }

    return render(request, "standingsmanager/view_standings.html", common_context(context))


# ============================================================================
# CSV Export
# ============================================================================


@login_required
@permission_required("standingsmanager.approve_standings")
def export_standings_csv(request):
    """
    Export all standings to CSV format.
    """
    # Create the HttpResponse object with CSV header
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="standings_export.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Entity Type",
            "Entity ID",
            "Entity Name",
            "Standing",
            "Requested By",
            "Added Date",
            "Notes",
        ]
    )

    # Get all standings
    all_standings = StandingsEntry.objects.select_related(
        "eve_entity", "added_by"
    ).order_by("entity_type", "eve_entity__name")

    for standing in all_standings:
        # Handle None case for added_by
        added_by_username = standing.added_by.username if standing.added_by else "Unknown"

        writer.writerow(
            [
                standing.eve_entity.get_entity_type_display(),
                standing.eve_entity.eve_id,
                standing.eve_entity.name,
                standing.standing,
                added_by_username,
                standing.added_date.strftime("%Y-%m-%d %H:%M:%S"),
                standing.notes or "",
            ]
        )

    return response


# ============================================================================
# User API Endpoints
# ============================================================================


@login_required
@permission_required("standingsmanager.add_syncedcharacter")
@require_http_methods(["POST"])
def api_request_character_standing(request, character_id):
    """
    API endpoint to create a character standing request.

    Args:
        character_id: EVE character ID

    Returns:
        JSON response with success/error status
    """
    try:
        # Get character
        character = get_object_or_404(EveCharacter, character_id=character_id)

        # Check if user owns character
        if not CharacterOwnership.objects.filter(
            user=request.user, character=character
        ).exists():
            return JsonResponse(
                {"success": False, "error": "You do not own this character."}, status=403
            )

        # Check eligibility
        can_request, error_message = can_user_request_character_standing(
            character, request.user
        )
        if not can_request:
            return JsonResponse(
                {"success": False, "error": error_message}, status=400
            )

        # Create request
        standing_request = StandingRequest.objects.create_character_request(
            character, request.user
        )

        logger.info(
            f"User {request.user.username} created standing request for character {character.character_name}"
        )

        return JsonResponse(
            {
                "success": True,
                "message": f"Standing request created for {character.character_name}",
                "request_pk": standing_request.pk,
            }
        )

    except Exception as e:
        logger.exception(f"Error creating character standing request: {e}")
        return JsonResponse(
            {"success": False, "error": "An unexpected error occurred."}, status=500
        )


@login_required
@permission_required("standingsmanager.add_syncedcharacter")
@require_http_methods(["POST"])
def api_request_corporation_standing(request, corporation_id):
    """
    API endpoint to create a corporation standing request.

    Args:
        corporation_id: EVE corporation ID

    Returns:
        JSON response with success/error status
    """
    try:
        # Get corporation
        try:
            corporation = EveCorporationInfo.objects.get(corporation_id=corporation_id)
        except EveCorporationInfo.DoesNotExist:
            corporation = EveCorporationInfo.objects.create_corporation(corporation_id)

        # Check eligibility
        can_request, error_message = can_user_request_corporation_standing(
            corporation, request.user
        )
        if not can_request:
            return JsonResponse(
                {"success": False, "error": error_message}, status=400
            )

        # Create request
        standing_request = StandingRequest.objects.create_corporation_request(
            corporation, request.user
        )

        logger.info(
            f"User {request.user.username} created standing request for corporation {corporation.corporation_name}"
        )

        return JsonResponse(
            {
                "success": True,
                "message": f"Standing request created for {corporation.corporation_name}",
                "request_pk": standing_request.pk,
            }
        )

    except Exception as e:
        logger.exception(f"Error creating corporation standing request: {e}")
        return JsonResponse(
            {"success": False, "error": "An unexpected error occurred."}, status=500
        )


@login_required
@permission_required("standingsmanager.add_syncedcharacter")
@require_http_methods(["POST"])
def api_remove_standing(request, entity_id):
    """
    API endpoint to create a revocation request for a standing.

    Args:
        entity_id: EVE entity ID (character, corp, or alliance)

    Returns:
        JSON response with success/error status
    """
    try:
        # Find entity
        try:
            entity = EveEntity.objects.get(eve_id=entity_id)
        except EveEntity.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Entity not found."}, status=404
            )

        # Check if standing exists
        if not StandingsEntry.objects.filter(eve_entity=entity).exists():
            return JsonResponse(
                {"success": False, "error": "No standing exists for this entity."},
                status=404,
            )

        # Check if user owns this entity
        # For characters, verify ownership
        if entity.entity_type == EveEntity.EntityType.CHARACTER:
            try:
                CharacterOwnership.objects.get(
                    user=request.user, character__character_id=entity_id
                )
            except CharacterOwnership.DoesNotExist:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "You can only request removal of your own standings.",
                    },
                    status=403,
                )

        # Create revocation
        revocation = StandingRevocation.objects.create_for_entity(
            entity, request.user, StandingRevocation.RevocationReason.USER_REQUEST
        )

        logger.info(
            f"User {request.user.username} created revocation request for {entity.name}"
        )

        return JsonResponse(
            {
                "success": True,
                "message": f"Revocation request created for {entity.name}",
                "revocation_pk": revocation.pk,
            }
        )

    except Exception as e:
        logger.exception(f"Error creating revocation request: {e}")
        return JsonResponse(
            {"success": False, "error": "An unexpected error occurred."}, status=500
        )


@login_required
@permission_required("standingsmanager.add_syncedcharacter")
@require_http_methods(["POST"])
def api_add_character_to_sync(request, character_id):
    """
    API endpoint to add a character to sync.

    Args:
        character_id: EVE character ID

    Returns:
        JSON response with success/error status
    """
    try:
        # Get character
        character = get_object_or_404(EveCharacter, character_id=character_id)

        # Check if user owns character
        try:
            character_ownership = CharacterOwnership.objects.get(
                user=request.user, character=character
            )
        except CharacterOwnership.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "You do not own this character."}, status=403
            )

        # Check if character has standing
        try:
            entity = EveEntity.objects.get(
                eve_id=character_id, entity_type=EveEntity.EntityType.CHARACTER
            )
            has_standing = StandingsEntry.objects.filter(eve_entity=entity).exists()
        except EveEntity.DoesNotExist:
            has_standing = False

        if not has_standing:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Character must have an approved standing before adding to sync.",
                },
                status=400,
            )

        # Check if already synced
        if SyncedCharacter.objects.filter(character_ownership=character_ownership).exists():
            return JsonResponse(
                {"success": False, "error": "Character is already synced."}, status=400
            )

        # Create synced character
        synced_char = SyncedCharacter.objects.create(
            character_ownership=character_ownership
        )

        # Trigger initial sync
        tasks.sync_character.delay(synced_char.pk)

        logger.info(
            f"User {request.user.username} added character {character.character_name} to sync"
        )

        return JsonResponse(
            {
                "success": True,
                "message": f"{character.character_name} added to sync",
                "synced_char_pk": synced_char.pk,
            }
        )

    except Exception as e:
        logger.exception(f"Error adding character to sync: {e}")
        return JsonResponse(
            {"success": False, "error": "An unexpected error occurred."}, status=500
        )


@login_required
@permission_required("standingsmanager.add_syncedcharacter")
@require_http_methods(["POST"])
def api_remove_character_from_sync(request, synced_char_pk):
    """
    API endpoint to remove a character from sync.

    Args:
        synced_char_pk: SyncedCharacter primary key

    Returns:
        JSON response with success/error status
    """
    try:
        # Get synced character
        synced_char = get_object_or_404(SyncedCharacter, pk=synced_char_pk)

        # Verify ownership
        if synced_char.character_ownership.user != request.user:
            return JsonResponse(
                {
                    "success": False,
                    "error": "You do not own this synced character.",
                },
                status=403,
            )

        character_name = synced_char.character.character_name

        # Delete synced character
        synced_char.delete()

        logger.info(
            f"User {request.user.username} removed character {character_name} from sync"
        )

        return JsonResponse(
            {"success": True, "message": f"{character_name} removed from sync"}
        )

    except Exception as e:
        logger.exception(f"Error removing character from sync: {e}")
        return JsonResponse(
            {"success": False, "error": "An unexpected error occurred."}, status=500
        )


# ============================================================================
# Approver API Endpoints
# ============================================================================


@login_required
@permission_required("standingsmanager.approve_standings")
@require_http_methods(["POST"])
def api_approve_request(request, request_pk):
    """
    API endpoint to approve a standing request.

    Args:
        request_pk: StandingRequest primary key

    Returns:
        JSON response with success/error status
    """
    try:
        # Get request
        standing_request = get_object_or_404(StandingRequest, pk=request_pk)

        # Check if still pending
        if standing_request.state != StandingRequest.RequestState.PENDING:
            return JsonResponse(
                {"success": False, "error": "Request is not pending."}, status=400
            )

        # Approve request
        standing_request.approve(request.user)

        # Trigger sync for all synced characters
        tasks.trigger_sync_after_approval.delay()

        logger.info(
            f"User {request.user.username} approved standing request for {standing_request.eve_entity.name}"
        )

        return JsonResponse(
            {
                "success": True,
                "message": f"Standing request for {standing_request.eve_entity.name} approved",
            }
        )

    except Exception as e:
        logger.exception(f"Error approving standing request: {e}")
        return JsonResponse(
            {"success": False, "error": "An unexpected error occurred."}, status=500
        )


@login_required
@permission_required("standingsmanager.approve_standings")
@require_http_methods(["POST"])
def api_reject_request(request, request_pk):
    """
    API endpoint to reject a standing request.

    Args:
        request_pk: StandingRequest primary key

    Returns:
        JSON response with success/error status
    """
    try:
        # Get request
        standing_request = get_object_or_404(StandingRequest, pk=request_pk)

        # Check if still pending
        if standing_request.state != StandingRequest.RequestState.PENDING:
            return JsonResponse(
                {"success": False, "error": "Request is not pending."}, status=400
            )

        entity_name = standing_request.eve_entity.name

        # Reject request
        standing_request.reject(request.user)

        logger.info(
            f"User {request.user.username} rejected standing request for {entity_name}"
        )

        return JsonResponse(
            {"success": True, "message": f"Standing request for {entity_name} rejected"}
        )

    except Exception as e:
        logger.exception(f"Error rejecting standing request: {e}")
        return JsonResponse(
            {"success": False, "error": "An unexpected error occurred."}, status=500
        )


@login_required
@permission_required("standingsmanager.approve_standings")
@require_http_methods(["POST"])
def api_approve_revocation(request, revocation_pk):
    """
    API endpoint to approve a standing revocation.

    Args:
        revocation_pk: StandingRevocation primary key

    Returns:
        JSON response with success/error status
    """
    try:
        # Get revocation
        revocation = get_object_or_404(StandingRevocation, pk=revocation_pk)

        # Check if still pending
        if revocation.state != StandingRevocation.RevocationState.PENDING:
            return JsonResponse(
                {"success": False, "error": "Revocation is not pending."}, status=400
            )

        # Approve revocation
        revocation.approve(request.user)

        # Trigger sync for all synced characters
        tasks.trigger_sync_after_revocation.delay()

        logger.info(
            f"User {request.user.username} approved standing revocation for {revocation.eve_entity.name}"
        )

        return JsonResponse(
            {
                "success": True,
                "message": f"Standing revocation for {revocation.eve_entity.name} approved",
            }
        )

    except Exception as e:
        logger.exception(f"Error approving standing revocation: {e}")
        return JsonResponse(
            {"success": False, "error": "An unexpected error occurred."}, status=500
        )


@login_required
@permission_required("standingsmanager.approve_standings")
@require_http_methods(["POST"])
def api_reject_revocation(request, revocation_pk):
    """
    API endpoint to reject a standing revocation.

    Args:
        revocation_pk: StandingRevocation primary key

    Returns:
        JSON response with success/error status
    """
    try:
        # Get revocation
        revocation = get_object_or_404(StandingRevocation, pk=revocation_pk)

        # Check if still pending
        if revocation.state != StandingRevocation.RevocationState.PENDING:
            return JsonResponse(
                {"success": False, "error": "Revocation is not pending."}, status=400
            )

        entity_name = revocation.eve_entity.name

        # Reject revocation
        revocation.reject(request.user)

        logger.info(
            f"User {request.user.username} rejected standing revocation for {entity_name}"
        )

        return JsonResponse(
            {
                "success": True,
                "message": f"Standing revocation for {entity_name} rejected",
            }
        )

    except Exception as e:
        logger.exception(f"Error rejecting standing revocation: {e}")
        return JsonResponse(
            {"success": False, "error": "An unexpected error occurred."}, status=500
        )
