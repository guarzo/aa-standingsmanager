from django import template
from eveuniverse.models import EveEntity

register = template.Library()


@register.inclusion_tag("standingssync/partial/war_participant.html")
def war_participant(obj: EveEntity) -> str:
    return {"obj": obj}
