"""Admin site for standingsmanager - Refactored for AA Standings Manager."""

# pylint: disable = missing-class-docstring, missing-function-docstring

from django.contrib import admin
from django.utils.html import format_html
from django.utils.timezone import now

from . import tasks
from .models import AuditLog, StandingRequest, StandingRevocation, StandingsEntry, SyncedCharacter


# ============================================================================
# Standings Entry Admin
# ============================================================================


@admin.register(StandingsEntry)
class StandingsEntryAdmin(admin.ModelAdmin):
    list_display = (
        "_entity_name",
        "_entity_type",
        "standing",
        "added_by",
        "added_date",
    )
    list_filter = ("entity_type", "added_date", "standing")
    search_fields = ("eve_entity__name",)
    readonly_fields = ("added_date",)
    fieldsets = (
        (
            "Entity Information",
            {
                "fields": ("eve_entity", "entity_type"),
            },
        ),
        (
            "Standing Information",
            {
                "fields": ("standing",),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("added_by", "added_date", "notes"),
            },
        ),
    )
    actions = ["delete_selected_standings"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("eve_entity", "added_by")

    def has_module_permission(self, request):
        return request.user.has_perm("standingsmanager.manage_standings")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("standingsmanager.manage_standings")

    def has_add_permission(self, request):
        return request.user.has_perm("standingsmanager.manage_standings")

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("standingsmanager.manage_standings")

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("standingsmanager.manage_standings")

    @admin.display(ordering="eve_entity__name", description="Entity Name")
    def _entity_name(self, obj):
        return obj.eve_entity.name

    @admin.display(ordering="entity_type", description="Entity Type")
    def _entity_type(self, obj):
        return obj.get_entity_type_display()

    @admin.display(description="Delete selected standings")
    def delete_selected_standings(self, request, queryset):
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f"Deleted {count} standing entries")


# ============================================================================
# Standing Request Admin
# ============================================================================


class StandingRequestStateFilter(admin.SimpleListFilter):
    title = "state"
    parameter_name = "state"

    def lookups(self, request, model_admin):
        return StandingRequest.State.choices

    def queryset(self, request, queryset):
        if value := self.value():
            return queryset.filter(state=value)
        return queryset


@admin.register(StandingRequest)
class StandingRequestAdmin(admin.ModelAdmin):
    list_display = (
        "_entity_name",
        "_entity_type",
        "requested_by",
        "_state",
        "request_date",
        "actioned_by",
        "action_date",
    )
    list_filter = (StandingRequestStateFilter, "entity_type", "request_date")
    search_fields = ("eve_entity__name", "requested_by__username")
    readonly_fields = (
        "eve_entity",
        "entity_type",
        "requested_by",
        "request_date",
        "state",
        "actioned_by",
        "action_date",
    )
    actions = ["approve_selected", "reject_selected"]
    list_select_related = ("eve_entity", "requested_by", "actioned_by")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("eve_entity", "requested_by", "actioned_by")

    def has_module_permission(self, request):
        return request.user.has_perm("standingsmanager.approve_standings")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("standingsmanager.approve_standings")

    def has_add_permission(self, request):
        return False  # Requests created by users, not admins

    def has_change_permission(self, request, obj=None):
        return False  # Read-only, use actions instead

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("standingsmanager.approve_standings")

    @admin.display(ordering="eve_entity__name", description="Entity Name")
    def _entity_name(self, obj):
        return obj.eve_entity.name

    @admin.display(ordering="entity_type", description="Entity Type")
    def _entity_type(self, obj):
        return obj.get_entity_type_display()

    @admin.display(ordering="state", description="State")
    def _state(self, obj):
        colors = {
            "pending": "#FFA500",  # Orange
            "approved": "#28a745",  # Green
            "rejected": "#dc3545",  # Red
        }
        color = colors.get(obj.state, "#6c757d")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_state_display(),
        )

    @admin.display(description="Approve selected pending requests")
    def approve_selected(self, request, queryset):
        queryset = queryset.filter(state=StandingRequest.State.PENDING)
        approved = []
        errors = []

        for obj in queryset:
            try:
                obj.approve(request.user)
                approved.append(str(obj.eve_entity.name))
            except Exception as ex:
                errors.append(f"{obj.eve_entity.name}: {ex}")

        if approved:
            # Trigger sync for all characters after approvals
            tasks.sync_all_characters.delay()
            self.message_user(request, f"Approved requests for: {', '.join(approved)}")

        if errors:
            self.message_user(
                request, f"Errors: {'; '.join(errors)}", level="error"
            )

    @admin.display(description="Reject selected pending requests")
    def reject_selected(self, request, queryset):
        queryset = queryset.filter(state=StandingRequest.State.PENDING)
        rejected = []
        errors = []

        for obj in queryset:
            try:
                obj.reject(request.user, reason="Rejected by admin")
                rejected.append(str(obj.eve_entity.name))
            except Exception as ex:
                errors.append(f"{obj.eve_entity.name}: {ex}")

        if rejected:
            self.message_user(request, f"Rejected requests for: {', '.join(rejected)}")

        if errors:
            self.message_user(
                request, f"Errors: {'; '.join(errors)}", level="error"
            )


# ============================================================================
# Standing Revocation Admin
# ============================================================================


class StandingRevocationStateFilter(admin.SimpleListFilter):
    title = "state"
    parameter_name = "state"

    def lookups(self, request, model_admin):
        return StandingRevocation.State.choices

    def queryset(self, request, queryset):
        if value := self.value():
            return queryset.filter(state=value)
        return queryset


@admin.register(StandingRevocation)
class StandingRevocationAdmin(admin.ModelAdmin):
    list_display = (
        "_entity_name",
        "_entity_type",
        "requested_by",
        "_reason",
        "_state",
        "request_date",
        "actioned_by",
    )
    list_filter = (StandingRevocationStateFilter, "reason", "entity_type", "request_date")
    search_fields = ("eve_entity__name", "requested_by__username")
    readonly_fields = (
        "eve_entity",
        "entity_type",
        "requested_by",
        "request_date",
        "reason",
        "state",
        "actioned_by",
        "action_date",
    )
    actions = ["approve_selected", "reject_selected"]
    list_select_related = ("eve_entity", "requested_by", "actioned_by")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("eve_entity", "requested_by", "actioned_by")

    def has_module_permission(self, request):
        return request.user.has_perm("standingsmanager.approve_standings")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("standingsmanager.approve_standings")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("standingsmanager.approve_standings")

    @admin.display(ordering="eve_entity__name", description="Entity Name")
    def _entity_name(self, obj):
        return obj.eve_entity.name

    @admin.display(ordering="entity_type", description="Entity Type")
    def _entity_type(self, obj):
        return obj.get_entity_type_display()

    @admin.display(ordering="reason", description="Reason")
    def _reason(self, obj):
        return obj.get_reason_display()

    @admin.display(ordering="state", description="State")
    def _state(self, obj):
        colors = {
            "pending": "#FFA500",
            "approved": "#28a745",
            "rejected": "#dc3545",
        }
        color = colors.get(obj.state, "#6c757d")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_state_display(),
        )

    @admin.display(description="Approve selected pending revocations")
    def approve_selected(self, request, queryset):
        queryset = queryset.filter(state=StandingRevocation.State.PENDING)
        approved = []
        errors = []

        for obj in queryset:
            try:
                obj.approve(request.user)
                approved.append(str(obj.eve_entity.name))
            except Exception as ex:
                errors.append(f"{obj.eve_entity.name}: {ex}")

        if approved:
            # Trigger sync for all characters after revocations
            tasks.sync_all_characters.delay()
            self.message_user(
                request, f"Approved revocations for: {', '.join(approved)}"
            )

        if errors:
            self.message_user(
                request, f"Errors: {'; '.join(errors)}", level="error"
            )

    @admin.display(description="Reject selected pending revocations")
    def reject_selected(self, request, queryset):
        queryset = queryset.filter(state=StandingRevocation.State.PENDING)
        rejected = []
        errors = []

        for obj in queryset:
            try:
                obj.reject(request.user, reason="Rejected by admin")
                rejected.append(str(obj.eve_entity.name))
            except Exception as ex:
                errors.append(f"{obj.eve_entity.name}: {ex}")

        if rejected:
            self.message_user(
                request, f"Rejected revocations for: {', '.join(rejected)}"
            )

        if errors:
            self.message_user(
                request, f"Errors: {'; '.join(errors)}", level="error"
            )


# ============================================================================
# Audit Log Admin
# ============================================================================


class AuditLogActionTypeFilter(admin.SimpleListFilter):
    title = "action type"
    parameter_name = "action_type"

    def lookups(self, request, model_admin):
        return AuditLog.ActionType.choices

    def queryset(self, request, queryset):
        if value := self.value():
            return queryset.filter(action_type=value)
        return queryset


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp",
        "_action_type",
        "_entity_name",
        "actioned_by",
        "requested_by",
    )
    list_filter = (AuditLogActionTypeFilter, "timestamp")
    search_fields = ("eve_entity__name", "actioned_by__username", "requested_by__username")
    readonly_fields = (
        "action_type",
        "eve_entity",
        "actioned_by",
        "requested_by",
        "timestamp",
    )
    list_select_related = ("eve_entity", "actioned_by", "requested_by")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("eve_entity", "actioned_by", "requested_by")

    def has_module_permission(self, request):
        return request.user.has_perm("standingsmanager.view_auditlog")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("standingsmanager.view_auditlog")

    def has_add_permission(self, request):
        return False  # Audit logs are created automatically

    def has_change_permission(self, request, obj=None):
        return False  # Audit logs are immutable

    def has_delete_permission(self, request, obj=None):
        return False  # Audit logs cannot be deleted

    @admin.display(ordering="action_type", description="Action Type")
    def _action_type(self, obj):
        return obj.get_action_type_display()

    @admin.display(ordering="eve_entity__name", description="Entity Name")
    def _entity_name(self, obj):
        return obj.eve_entity.name


# ============================================================================
# Synced Character Admin
# ============================================================================


@admin.register(SyncedCharacter)
class SyncedCharacterAdmin(admin.ModelAdmin):
    list_display = (
        "_user",
        "_character_name",
        "_has_label",
        "_is_fresh",
        "last_sync_at",
        "_last_error",
    )
    list_filter = (
        "has_label",
        "last_sync_at",
        ("character_ownership__user", admin.RelatedOnlyFieldListFilter),
    )
    actions = ["sync_characters", "force_sync_characters", "validate_eligibility"]
    list_display_links = None
    readonly_fields = ("last_sync_at", "last_error")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "character_ownership__character",
            "character_ownership__user",
        )

    def has_add_permission(self, request):
        return False

    @admin.display(ordering="character_ownership__user")
    def _user(self, obj):
        return obj.character_ownership.user

    @admin.display(ordering="character_ownership__character__character_name")
    def _character_name(self, obj):
        return str(obj)

    @admin.display(boolean=True, description="Has Label")
    def _has_label(self, obj):
        return obj.has_label

    @admin.display(boolean=True, description="Sync Fresh")
    def _is_fresh(self, obj):
        return obj.is_sync_fresh

    @admin.display(description="Last Error")
    def _last_error(self, obj):
        if obj.last_error:
            # Truncate long errors for display
            return obj.last_error[:50] + "..." if len(obj.last_error) > 50 else obj.last_error
        return "-"

    @admin.display(description="Sync selected characters (normal)")
    def sync_characters(self, request, queryset):
        names = []
        for obj in queryset:
            tasks.sync_character.delay(obj.pk)
            names.append(str(obj))
        names_text = ", ".join(names)
        self.message_user(request, f"Started syncing for: {names_text}")

    @admin.display(description="Force sync selected characters")
    def force_sync_characters(self, request, queryset):
        names = []
        for obj in queryset:
            tasks.sync_character.delay(obj.pk)
            names.append(str(obj))
        names_text = ", ".join(names)
        self.message_user(request, f"Started force sync for: {names_text}")

    @admin.display(description="Validate eligibility for selected characters")
    def validate_eligibility(self, request, queryset):
        valid = []
        invalid = []
        for obj in queryset:
            if obj.is_eligible():
                valid.append(str(obj))
            else:
                invalid.append(str(obj))

        if valid:
            self.message_user(request, f"Valid: {', '.join(valid)}")
        if invalid:
            self.message_user(
                request,
                f"Invalid (removed): {', '.join(invalid)}",
                level="warning",
            )
