# Migration to add missing custom permissions
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("standingsmanager", "0004_refactor_to_persistent_standings"),
    ]

    operations = [
        # Add custom permissions to StandingsEntry
        migrations.AlterModelOptions(
            name="standingsentry",
            options={
                "verbose_name": "Standing Entry",
                "verbose_name_plural": "Standing Entries",
                "ordering": ["entity_type", "eve_entity__name"],
                "permissions": [
                    ("manage_standings", "Can manage standings database"),
                ],
            },
        ),
        # Add custom permissions to StandingRequest
        migrations.AlterModelOptions(
            name="standingrequest",
            options={
                "verbose_name": "Standing Request",
                "verbose_name_plural": "Standing Requests",
                "ordering": ["-request_date"],
                "permissions": [
                    ("approve_standings", "Can approve standing requests"),
                ],
            },
        ),
        # Add verbose names to SyncedCharacter (ensures default permissions are created)
        migrations.AlterModelOptions(
            name="syncedcharacter",
            options={
                "verbose_name": "Synced Character",
                "verbose_name_plural": "Synced Characters",
                "ordering": ["character_ownership__character__character_name"],
            },
        ),
    ]
