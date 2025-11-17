"""Tests for refactored Sprint 4 views."""

from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter
from allianceauth.tests.auth_utils import AuthUtils

from ..models import (
    EveEntity,
    StandingRequest,
    StandingRevocation,
    StandingsEntry,
    SyncedCharacter,
)


class ViewTestCase(TestCase):
    """Base test case for views."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = AuthUtils.create_user("test_user")
        cls.approver = AuthUtils.create_user("approver_user")

        # Add permissions
        cls.user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="standingsmanager",
                codename="add_syncedcharacter",
            )
        )
        cls.approver.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="standingsmanager",
                codename="add_syncedcharacter",
            )
        )
        cls.approver.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="standingsmanager",
                codename="approve_standings",
            )
        )

        # Create test character
        cls.character = EveCharacter.objects.create(
            character_id=1001,
            character_name="Test Character",
            corporation_id=2001,
            corporation_name="Test Corp",
            corporation_ticker="TEST",
        )

        cls.character_ownership = CharacterOwnership.objects.create(
            character=cls.character, owner_hash="hash1", user=cls.user
        )

    def setUp(self):
        self.client = Client()


class TestRequestStandingsView(ViewTestCase):
    """Tests for request_standings view."""

    def test_view_requires_login(self):
        """Test that view requires login."""
        response = self.client.get(reverse("standingssync:request_standings"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_view_requires_permission(self):
        """Test that view requires permission."""
        user_no_perms = AuthUtils.create_user("no_perms_user")
        self.client.force_login(user_no_perms)
        response = self.client.get(reverse("standingssync:request_standings"))
        self.assertEqual(response.status_code, 302)  # Redirect due to no permission

    def test_view_loads_with_permission(self):
        """Test that view loads with correct permission."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("standingssync:request_standings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Request Standings")

    def test_view_shows_characters(self):
        """Test that view shows user's characters."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("standingssync:request_standings"))
        self.assertContains(response, "Test Character")


class TestMySyncedCharactersView(ViewTestCase):
    """Tests for my_synced_characters view."""

    def test_view_requires_login(self):
        """Test that view requires login."""
        response = self.client.get(reverse("standingssync:my_synced_characters"))
        self.assertEqual(response.status_code, 302)

    def test_view_requires_permission(self):
        """Test that view requires permission."""
        user_no_perms = AuthUtils.create_user("no_perms_user2")
        self.client.force_login(user_no_perms)
        response = self.client.get(reverse("standingssync:my_synced_characters"))
        self.assertEqual(response.status_code, 302)

    def test_view_loads_with_permission(self):
        """Test that view loads with correct permission."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("standingssync:my_synced_characters"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Synced Characters")

    def test_view_shows_synced_character(self):
        """Test that view shows synced characters."""
        # Create entity and standing
        entity = EveEntity.objects.create(
            eve_id=self.character.character_id,
            name=self.character.character_name,
            entity_type=EveEntity.EntityType.CHARACTER,
        )
        StandingsEntry.objects.create(
            eve_entity=entity, standing=5.0, added_by=self.user
        )

        # Create synced character
        SyncedCharacter.objects.create(character_ownership=self.character_ownership)

        self.client.force_login(self.user)
        response = self.client.get(reverse("standingssync:my_synced_characters"))
        self.assertContains(response, "Test Character")


class TestManageRequestsView(ViewTestCase):
    """Tests for manage_requests view."""

    def test_view_requires_login(self):
        """Test that view requires login."""
        response = self.client.get(reverse("standingssync:manage_requests"))
        self.assertEqual(response.status_code, 302)

    def test_view_requires_permission(self):
        """Test that view requires approver permission."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("standingssync:manage_requests"))
        self.assertEqual(response.status_code, 302)

    def test_view_loads_with_permission(self):
        """Test that view loads with approver permission."""
        self.client.force_login(self.approver)
        response = self.client.get(reverse("standingssync:manage_requests"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manage Standing Requests")

    def test_view_shows_pending_requests(self):
        """Test that view shows pending requests."""
        # Create entity and request
        entity = EveEntity.objects.create(
            eve_id=self.character.character_id,
            name=self.character.character_name,
            entity_type=EveEntity.EntityType.CHARACTER,
        )
        StandingRequest.objects.create(
            eve_entity=entity,
            requested_by=self.user,
            state=StandingRequest.RequestState.PENDING,
        )

        self.client.force_login(self.approver)
        response = self.client.get(reverse("standingssync:manage_requests"))
        self.assertContains(response, "Test Character")


class TestManageRevocationsView(ViewTestCase):
    """Tests for manage_revocations view."""

    def test_view_requires_login(self):
        """Test that view requires login."""
        response = self.client.get(reverse("standingssync:manage_revocations"))
        self.assertEqual(response.status_code, 302)

    def test_view_requires_permission(self):
        """Test that view requires approver permission."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("standingssync:manage_revocations"))
        self.assertEqual(response.status_code, 302)

    def test_view_loads_with_permission(self):
        """Test that view loads with approver permission."""
        self.client.force_login(self.approver)
        response = self.client.get(reverse("standingssync:manage_revocations"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manage Standing Revocations")


class TestViewStandingsView(ViewTestCase):
    """Tests for view_standings view."""

    def test_view_requires_login(self):
        """Test that view requires login."""
        response = self.client.get(reverse("standingssync:view_standings"))
        self.assertEqual(response.status_code, 302)

    def test_view_requires_permission(self):
        """Test that view requires approver permission."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("standingssync:view_standings"))
        self.assertEqual(response.status_code, 302)

    def test_view_loads_with_permission(self):
        """Test that view loads with approver permission."""
        self.client.force_login(self.approver)
        response = self.client.get(reverse("standingssync:view_standings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "View Standings")

    def test_view_shows_standings(self):
        """Test that view shows standings entries."""
        # Create entity and standing
        entity = EveEntity.objects.create(
            eve_id=self.character.character_id,
            name=self.character.character_name,
            entity_type=EveEntity.EntityType.CHARACTER,
        )
        StandingsEntry.objects.create(
            eve_entity=entity, standing=5.0, added_by=self.user
        )

        self.client.force_login(self.approver)
        response = self.client.get(reverse("standingssync:view_standings"))
        self.assertContains(response, "Test Character")


class TestAPIEndpoints(ViewTestCase):
    """Tests for API endpoints."""

    @patch("standingssync.validators.character_has_required_scopes")
    def test_api_request_character_standing(self, mock_scopes):
        """Test API endpoint for requesting character standing."""
        mock_scopes.return_value = (True, [])

        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "standingssync:api_request_character_standing",
                args=[self.character.character_id],
            )
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

    def test_api_request_character_standing_unauthorized(self):
        """Test API endpoint rejects unauthorized users."""
        # Create another user
        other_user = AuthUtils.create_user("other_user")
        other_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="standingsmanager",
                codename="add_syncedcharacter",
            )
        )

        self.client.force_login(other_user)
        response = self.client.post(
            reverse(
                "standingssync:api_request_character_standing",
                args=[self.character.character_id],
            )
        )
        self.assertEqual(response.status_code, 403)

    def test_api_add_character_to_sync(self):
        """Test API endpoint for adding character to sync."""
        # Create entity and standing first
        entity = EveEntity.objects.create(
            eve_id=self.character.character_id,
            name=self.character.character_name,
            entity_type=EveEntity.EntityType.CHARACTER,
        )
        StandingsEntry.objects.create(
            eve_entity=entity, standing=5.0, added_by=self.user
        )

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("standingssync:api_add_sync", args=[self.character.character_id])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        # Verify synced character was created
        self.assertTrue(
            SyncedCharacter.objects.filter(
                character_ownership=self.character_ownership
            ).exists()
        )

    def test_api_remove_character_from_sync(self):
        """Test API endpoint for removing character from sync."""
        # Create synced character
        synced_char = SyncedCharacter.objects.create(
            character_ownership=self.character_ownership
        )

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("standingssync:api_remove_sync", args=[synced_char.pk])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        # Verify synced character was deleted
        self.assertFalse(SyncedCharacter.objects.filter(pk=synced_char.pk).exists())

    def test_api_approve_request(self):
        """Test API endpoint for approving request."""
        # Create entity and request
        entity = EveEntity.objects.create(
            eve_id=self.character.character_id,
            name=self.character.character_name,
            entity_type=EveEntity.EntityType.CHARACTER,
        )
        request_obj = StandingRequest.objects.create(
            eve_entity=entity,
            requested_by=self.user,
            state=StandingRequest.RequestState.PENDING,
        )

        self.client.force_login(self.approver)
        response = self.client.post(
            reverse("standingssync:api_approve_request", args=[request_obj.pk])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        # Verify standing was created
        self.assertTrue(StandingsEntry.objects.filter(eve_entity=entity).exists())

    def test_api_reject_request(self):
        """Test API endpoint for rejecting request."""
        # Create entity and request
        entity = EveEntity.objects.create(
            eve_id=self.character.character_id,
            name=self.character.character_name,
            entity_type=EveEntity.EntityType.CHARACTER,
        )
        request_obj = StandingRequest.objects.create(
            eve_entity=entity,
            requested_by=self.user,
            state=StandingRequest.RequestState.PENDING,
        )

        self.client.force_login(self.approver)
        response = self.client.post(
            reverse("standingssync:api_reject_request", args=[request_obj.pk])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        # Verify request was deleted
        self.assertFalse(StandingRequest.objects.filter(pk=request_obj.pk).exists())


class TestCSVExport(ViewTestCase):
    """Tests for CSV export."""

    def test_export_requires_login(self):
        """Test that CSV export requires login."""
        response = self.client.get(reverse("standingssync:export_standings_csv"))
        self.assertEqual(response.status_code, 302)

    def test_export_requires_permission(self):
        """Test that CSV export requires permission."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("standingssync:export_standings_csv"))
        self.assertEqual(response.status_code, 302)

    def test_export_works_with_permission(self):
        """Test that CSV export works with permission."""
        # Create entity and standing
        entity = EveEntity.objects.create(
            eve_id=self.character.character_id,
            name=self.character.character_name,
            entity_type=EveEntity.EntityType.CHARACTER,
        )
        StandingsEntry.objects.create(
            eve_entity=entity, standing=5.0, added_by=self.user
        )

        self.client.force_login(self.approver)
        response = self.client.get(reverse("standingssync:export_standings_csv"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn(b"Test Character", response.content)
