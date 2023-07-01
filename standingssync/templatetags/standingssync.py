"""Template tags for standingssync."""

from django import template
from eveuniverse.core import zkillboard
from eveuniverse.models import EveEntity

register = template.Library()


@register.inclusion_tag("standingssync/partial/war_participant.html")
def war_participant(obj: EveEntity, icon_size=None) -> str:
    """Render war participant with icon, name and link to ZKB."""
    context = {"has_data": False, "icon_size": icon_size or 20}
    try:
        category = obj.category
    except AttributeError:
        return context
    if category:
        if obj.is_alliance:
            profile_url = zkillboard.alliance_url(obj.id)
        elif obj.is_corporation:
            profile_url = zkillboard.corporation_url(obj.id)
        else:
            profile_url = ""
        context.update(
            {
                "has_data": True,
                "name": obj.name,
                "profile_url": profile_url,
                "icon_url": obj.icon_url(32),
            }
        )
    return context
