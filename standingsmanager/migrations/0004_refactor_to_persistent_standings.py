# Migration for refactoring to persistent standings database
# This migration:
# 1. Removes old models (SyncManager, EveContact, EveWar)
# 2. Updates SyncedCharacter to new simplified structure
# 3. Adds new models (StandingsEntry, StandingRequest, StandingRevocation, AuditLog)

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("standingssync", "0003_add_alliance_contacts_label_field"),
        ("eveuniverse", "0007_evetype_description"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("authentication", "0019_merge_20211026_0919"),
    ]

    operations = [
        # Step 1: Remove old models (in reverse dependency order)
        migrations.DeleteModel(
            name="EveContact",
        ),
        migrations.DeleteModel(
            name="EveWar",
        ),
        # Step 2: Remove SyncedCharacter.manager field (FK to SyncManager)
        migrations.RemoveField(
            model_name="syncedcharacter",
            name="manager",
        ),
        # Step 3: Remove old SyncedCharacter fields
        migrations.RemoveField(
            model_name="syncedcharacter",
            name="version_hash",
        ),
        migrations.RemoveField(
            model_name="syncedcharacter",
            name="has_war_targets_label",
        ),
        migrations.RemoveField(
            model_name="syncedcharacter",
            name="has_alliance_contacts_label",
        ),
        # Step 4: Remove SyncManager model
        migrations.DeleteModel(
            name="SyncManager",
        ),
        # Step 5: Update SyncedCharacter to new structure
        migrations.AlterField(
            model_name="syncedcharacter",
            name="last_sync",
            field=models.DateTimeField(
                blank=True,
                default=None,
                help_text="Date and time of the last successful sync",
                null=True,
            ),
        ),
        migrations.RenameField(
            model_name="syncedcharacter",
            old_name="last_sync",
            new_name="last_sync_at",
        ),
        migrations.AlterField(
            model_name="syncedcharacter",
            name="last_error",
            field=models.TextField(
                blank=True,
                help_text="Last error encountered during sync (if any)",
            ),
        ),
        migrations.AddField(
            model_name="syncedcharacter",
            name="has_label",
            field=models.BooleanField(
                default=False,
                help_text="Whether this character has the configured label in-game",
            ),
        ),
        # Step 6: Create new StandingsEntry model
        migrations.CreateModel(
            name="StandingsEntry",
            fields=[
                (
                    "eve_entity",
                    models.OneToOneField(
                        help_text="The EVE entity (character/corporation/alliance) with standings",
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="standings_entry",
                        serialize=False,
                        to="eveuniverse.eveentity",
                    ),
                ),
                (
                    "standing",
                    models.FloatField(
                        help_text="Standing value (-10.0 to +10.0)",
                        validators=[
                            django.core.validators.MinValueValidator(-10.0),
                            django.core.validators.MaxValueValidator(10.0),
                        ],
                    ),
                ),
                (
                    "entity_type",
                    models.CharField(
                        choices=[
                            ("character", "Character"),
                            ("corporation", "Corporation"),
                            ("alliance", "Alliance"),
                        ],
                        help_text="Type of entity",
                        max_length=20,
                    ),
                ),
                (
                    "added_date",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="When this standing was added",
                    ),
                ),
                (
                    "notes",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Optional notes about this standing",
                    ),
                ),
                (
                    "added_by",
                    models.ForeignKey(
                        help_text="User who added this standing",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="standings_added",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Standing Entry",
                "verbose_name_plural": "Standing Entries",
                "ordering": ["entity_type", "eve_entity__name"],
            },
        ),
        # Step 7: Create new StandingRequest model
        migrations.CreateModel(
            name="StandingRequest",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "eve_entity",
                    models.ForeignKey(
                        help_text="The EVE entity being requested",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="standing_requests",
                        to="eveuniverse.eveentity",
                    ),
                ),
                (
                    "entity_type",
                    models.CharField(
                        choices=[
                            ("character", "Character"),
                            ("corporation", "Corporation"),
                            ("alliance", "Alliance"),
                        ],
                        help_text="Type of entity",
                        max_length=20,
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        help_text="User who requested this standing",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="standing_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "request_date",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="When this request was created",
                    ),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        default="pending",
                        help_text="Current state of the request",
                        max_length=20,
                    ),
                ),
                (
                    "actioned_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="User who approved/rejected this request",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="actioned_standing_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "action_date",
                    models.DateTimeField(
                        blank=True,
                        help_text="When this request was actioned",
                        null=True,
                    ),
                ),
            ],
            options={
                "verbose_name": "Standing Request",
                "verbose_name_plural": "Standing Requests",
                "ordering": ["-request_date"],
                "unique_together": [("eve_entity", "state")],
            },
        ),
        # Step 8: Create new StandingRevocation model
        migrations.CreateModel(
            name="StandingRevocation",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "eve_entity",
                    models.ForeignKey(
                        help_text="The EVE entity being revoked",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="standing_revocations",
                        to="eveuniverse.eveentity",
                    ),
                ),
                (
                    "entity_type",
                    models.CharField(
                        choices=[
                            ("character", "Character"),
                            ("corporation", "Corporation"),
                            ("alliance", "Alliance"),
                        ],
                        help_text="Type of entity",
                        max_length=20,
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="User who requested this revocation (null for auto-revocations)",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="standing_revocations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "request_date",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="When this revocation was created",
                    ),
                ),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("user_request", "User Request"),
                            ("lost_permission", "Lost Permission"),
                            ("missing_token", "Missing Token"),
                        ],
                        help_text="Reason for revocation",
                        max_length=30,
                    ),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        default="pending",
                        help_text="Current state of the revocation",
                        max_length=20,
                    ),
                ),
                (
                    "actioned_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="User who approved/rejected this revocation",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="actioned_standing_revocations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "action_date",
                    models.DateTimeField(
                        blank=True,
                        help_text="When this revocation was actioned",
                        null=True,
                    ),
                ),
            ],
            options={
                "verbose_name": "Standing Revocation",
                "verbose_name_plural": "Standing Revocations",
                "ordering": ["-request_date"],
            },
        ),
        # Step 9: Create new AuditLog model
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "action_type",
                    models.CharField(
                        choices=[
                            ("approve_request", "Approve Request"),
                            ("reject_request", "Reject Request"),
                            ("approve_revocation", "Approve Revocation"),
                            ("reject_revocation", "Reject Revocation"),
                        ],
                        help_text="Type of action performed",
                        max_length=30,
                    ),
                ),
                (
                    "eve_entity",
                    models.ForeignKey(
                        help_text="The EVE entity affected",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_logs",
                        to="eveuniverse.eveentity",
                    ),
                ),
                (
                    "actioned_by",
                    models.ForeignKey(
                        help_text="User who performed the action",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_logs_actioned",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        help_text="User who made the original request",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_logs_requested",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "timestamp",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="When this action was performed",
                    ),
                ),
            ],
            options={
                "verbose_name": "Audit Log Entry",
                "verbose_name_plural": "Audit Log Entries",
                "ordering": ["-timestamp"],
            },
        ),
    ]
