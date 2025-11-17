# Generated migration for alliance contacts label tracking

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("standingsmanager", "0002_improve_sync_logic"),
    ]

    operations = [
        migrations.AddField(
            model_name="syncedcharacter",
            name="has_alliance_contacts_label",
            field=models.BooleanField(
                default=None,
                help_text="Whether this character has the alliance contacts label.",
                null=True,
            ),
        ),
    ]
