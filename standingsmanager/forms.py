"""Forms for standingsmanager admin."""

from django import forms

from .models import StandingsEntry


class StandingsEntryAdminForm(forms.ModelForm):
    """Custom form for StandingsEntry admin with entity type filtering."""

    class Meta:
        model = StandingsEntry
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add data attribute to eve_entity field for filtering
        if "eve_entity" in self.fields:
            # Get all entities and add data-category attribute
            self.fields["eve_entity"].widget.attrs.update(
                {
                    "id": "id_eve_entity",
                    "class": "admin-autocomplete",
                }
            )

        # Add change event to entity_type field
        if "entity_type" in self.fields:
            self.fields["entity_type"].widget.attrs.update(
                {
                    "id": "id_entity_type",
                }
            )

    class Media:
        js = ("standingsmanager/js/admin_entity_filter.js",)
