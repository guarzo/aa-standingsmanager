from django.apps import AppConfig

from . import __version__


class StandingsManagerConfig(AppConfig):
    name = "standingsmanager"
    label = "standingsmanager"
    verbose_name = f"Standings Manager v{__version__}"
