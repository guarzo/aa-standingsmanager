"""Routes for standingsmanager."""

from django.urls import path

from . import views

app_name = "standingsmanager"

urlpatterns = [
    # Main pages
    path("", views.index, name="index"),
    path("request/", views.request_standings, name="request_standings"),
    path("add-scopes/", views.add_scopes, name="add_scopes"),
    path("sync/", views.my_synced_characters, name="my_synced_characters"),
    path("manage/", views.manage_requests, name="manage_requests"),
    path("manage/revocations/", views.manage_revocations, name="manage_revocations"),
    path("view/", views.view_standings, name="view_standings"),
    # User API endpoints
    path(
        "api/request-character/<int:character_id>/",
        views.api_request_character_standing,
        name="api_request_character_standing",
    ),
    path(
        "api/request-corporation/<int:corporation_id>/",
        views.api_request_corporation_standing,
        name="api_request_corporation_standing",
    ),
    path(
        "api/remove-standing/<int:entity_id>/",
        views.api_remove_standing,
        name="api_remove_standing",
    ),
    path(
        "api/add-sync/<int:character_id>/",
        views.api_add_character_to_sync,
        name="api_add_sync",
    ),
    path(
        "api/remove-sync/<int:synced_char_pk>/",
        views.api_remove_character_from_sync,
        name="api_remove_sync",
    ),
    # Approver API endpoints
    path(
        "api/approve-request/<int:request_pk>/",
        views.api_approve_request,
        name="api_approve_request",
    ),
    path(
        "api/reject-request/<int:request_pk>/",
        views.api_reject_request,
        name="api_reject_request",
    ),
    path(
        "api/approve-revocation/<int:revocation_pk>/",
        views.api_approve_revocation,
        name="api_approve_revocation",
    ),
    path(
        "api/reject-revocation/<int:revocation_pk>/",
        views.api_reject_revocation,
        name="api_reject_revocation",
    ),
    # CSV export
    path("export/csv/", views.export_standings_csv, name="export_standings_csv"),
]
