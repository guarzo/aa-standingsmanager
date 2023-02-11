from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect, render
from esi.decorators import token_required

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveAllianceInfo, EveCharacter
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag
from app_utils.views import bootstrap_icon_plus_name_html

from . import __title__, tasks
from .app_settings import (
    STANDINGSSYNC_ADD_WAR_TARGETS,
    STANDINGSSYNC_CHAR_MIN_STANDING,
    STANDINGSSYNC_REPLACE_CONTACTS,
    STANDINGSSYNC_WAR_TARGETS_LABEL_NAME,
)
from .models import EveWar, SyncedCharacter, SyncManager

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


@login_required
@permission_required("standingssync.add_syncedcharacter")
def index(request):
    """main page"""
    sync_manager = SyncManager.objects.fetch_for_user(request.user)
    synced_characters = list()
    qs = sync_manager.synced_characters_for_user(request.user).select_related(
        "character_ownership", "character_ownership__character"
    )
    for synced_character in qs:
        character = synced_character.character
        name_html = bootstrap_icon_plus_name_html(
            character.portrait_url(), character.character_name, avatar=True
        )
        organization = character.corporation_name
        if character.alliance_ticker:
            organization += f" [{character.alliance_ticker}]"

        errors = []
        if not synced_character.is_sync_fresh:
            errors.append("Sync is outdated.")
        if (
            STANDINGSSYNC_ADD_WAR_TARGETS
            and synced_character.has_war_targets_label is False
        ):
            errors.append(
                f"Please create a contact label with the name: "
                f"{STANDINGSSYNC_WAR_TARGETS_LABEL_NAME}"
            )
        synced_characters.append(
            {
                "name": character.character_name,
                "name_html": name_html,
                "organization": organization,
                "errors": errors,
                "pk": synced_character.pk,
            }
        )

    context = {
        "app_title": __title__,
        "synced_characters": synced_characters,
        "has_synced_chars": len(synced_characters) > 0,
    }
    if sync_manager:
        context["alliance"] = sync_manager.alliance
        if STANDINGSSYNC_REPLACE_CONTACTS:
            alliance_contacts_count = sync_manager.contacts.filter(
                is_war_target=False
            ).count()
        else:
            alliance_contacts_count = None
        if STANDINGSSYNC_ADD_WAR_TARGETS:
            alliance_war_targets_count = sync_manager.contacts.filter(
                is_war_target=True
            ).count()
        else:
            alliance_war_targets_count = None
    else:
        context["alliance"] = None
        alliance_contacts_count = None
        alliance_war_targets_count = None

    context["alliance_contacts_count"] = alliance_contacts_count
    context["alliance_war_targets_count"] = alliance_war_targets_count
    context["war_targets_label_name"] = STANDINGSSYNC_WAR_TARGETS_LABEL_NAME

    return render(request, "standingssync/index.html", context)


@login_required
@permission_required("standingssync.add_syncmanager")
@token_required(SyncManager.get_esi_scopes())
def add_alliance_manager(request, token):
    """Add or update sync manager for an alliance."""
    token_char = get_object_or_404(EveCharacter, character_id=token.character_id)
    if not token_char.alliance_id:
        messages.warning(
            request,
            f"Can not add {token_char}, because it is not a member of any alliance.",
        )
    else:
        character_ownership = get_object_or_404(
            CharacterOwnership, user=request.user, character=token_char
        )
        try:
            alliance = EveAllianceInfo.objects.get(alliance_id=token_char.alliance_id)
        except EveAllianceInfo.DoesNotExist:
            alliance = EveAllianceInfo.objects.create_alliance(token_char.alliance_id)
            alliance.save()
        sync_manager, _ = SyncManager.objects.update_or_create(
            alliance=alliance, defaults={"character_ownership": character_ownership}
        )
        tasks.run_manager_sync.delay(sync_manager.pk)
        messages.success(
            request,
            f"{sync_manager.character_ownership.character.character_name} "
            f"set as alliance character for {alliance.alliance_name}. "
            "Started syncing of alliance contacts. ",
        )
    return redirect("standingssync:index")


@login_required
@permission_required("standingssync.add_syncedcharacter")
@token_required(scopes=SyncedCharacter.get_esi_scopes())
def add_character(request, token):
    """add character to receive alliance contacts"""
    alliance = get_object_or_404(
        EveAllianceInfo, alliance_id=request.user.profile.main_character.alliance_id
    )
    sync_manager = get_object_or_404(SyncManager, alliance=alliance)
    token_char = get_object_or_404(EveCharacter, character_id=token.character_id)
    if token_char.alliance_id == sync_manager.character_ownership.character.alliance_id:
        messages.warning(
            request,
            "Adding alliance members does not make much sense, "
            "since they already have access to alliance contacts.",
        )

    else:
        character_ownership = get_object_or_404(
            CharacterOwnership, user=request.user, character=token_char
        )
        eff_standing = sync_manager.effective_standing_with_character(
            character_ownership.character
        )
        if eff_standing < STANDINGSSYNC_CHAR_MIN_STANDING:
            messages.warning(
                request,
                "Can not activate sync for your "
                f"character {token_char.character_name}, "
                "because it does not have blue standing "
                "with the alliance. "
                f"The standing value is: {eff_standing:.1f}. "
                "Please first obtain blue "
                "standing for your character and then try again.",
            )
        else:
            sync_character, _ = SyncedCharacter.objects.update_or_create(
                character_ownership=character_ownership,
                defaults={"manager": sync_manager},
            )
            tasks.run_character_sync.delay(sync_character.pk)
            messages.success(
                request, "Sync activated for {}!".format(token_char.character_name)
            )
    return redirect("standingssync:index")


@login_required
@permission_required("standingssync.add_syncedcharacter")
def remove_character(request, alt_pk):
    """remove character from receiving alliance contacts"""
    alt = get_object_or_404(SyncedCharacter, pk=alt_pk)
    alt_name = alt.character_ownership.character.character_name
    alt.delete()
    messages.success(request, "Sync deactivated for {}".format(alt_name))
    return redirect("standingssync:index")


@login_required
@staff_member_required
def admin_update_wars(request):
    """Start updating eve wars."""
    wars_count = EveWar.objects.count()
    tasks.sync_all_wars.delay()
    messages.info(
        request,
        (
            f"Started updating approx. {wars_count:,} wars from ESI in the background. "
            "This can take a minute."
        ),
    )
    return redirect("admin:standingssync_evewar_changelist")
