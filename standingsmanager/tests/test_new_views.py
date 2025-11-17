"""Tests for refactored Sprint 4 views."""

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse
from eveuniverse.models import EveEntity

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter
from allianceauth.tests.auth_utils import AuthUtils

from ..models import StandingRequest, StandingsEntry


class ViewTestCase(TestCase):
    """Base test case for views."""

    def setUp(self):
        """Set up test data for each test."""
        # Create users
        self.user = AuthUtils.create_user("test_user")
        self.approver = AuthUtils.create_user("approver_user")

        # Create custom permissions if they don't exist
        standing_request_ct = ContentType.objects.get_for_model(StandingRequest)
        approve_perm, _ = Permission.objects.get_or_create(
            codename="approve_standings",
            content_type=standing_request_ct,
            defaults={"name": "Can approve standing requests"},
        )

        # Get permissions
        add_synced_char_perm = Permission.objects.get(
            content_type__app_label="standingsmanager",
            codename="add_syncedcharacter",
        )

        # Add permissions
        self.user.user_permissions.add(add_synced_char_perm)
        self.approver.user_permissions.add(add_synced_char_perm)
        self.approver.user_permissions.add(approve_perm)

        # Create test character
        self.character = EveCharacter.objects.create(
            character_id=1001,
            character_name="Test Character",
            corporation_id=2001,
            corporation_name="Test Corp",
            corporation_ticker="TEST",
        )

        self.character_ownership = CharacterOwnership.objects.create(
            character=self.character, owner_hash="hash1", user=self.user
        )

        self.client = Client()

    def _create_character_standing(self, character=None, standing=5.0, added_by=None):
        """Helper to create a standing for a character."""
        if character is None:
            character = self.character
        if added_by is None:
            added_by = self.user

        entity, _ = EveEntity.objects.get_or_create(
            id=character.character_id,
            defaults={
                "name": character.character_name,
                "category": EveEntity.CATEGORY_CHARACTER,
            },
        )
        return StandingsEntry.objects.create(
            eve_entity=entity,
            entity_type=StandingsEntry.EntityType.CHARACTER,
            standing=standing,
            added_by=added_by,
        )


class TestRequestStandingsView(ViewTestCase):
    """Tests for request_standings view."""

    def test_view_requires_login(self):
        """Test that view requires login."""
        response = self.client.get(reverse("standingsmanager:request_standings"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_view_requires_permission(self):
        """Test that view requires permission."""
        user_no_perms = AuthUtils.create_user("no_perms_user")
        self.client.force_login(user_no_perms)
        response = self.client.get(reverse("standingsmanager:request_standings"))
        self.assertEqual(response.status_code, 302)  # Redirect due to no permission


class TestMySyncedCharactersView(ViewTestCase):
    """Tests for my_synced_characters view."""

    def test_view_requires_login(self):
        """Test that view requires login."""
        response = self.client.get(reverse("standingsmanager:my_synced_characters"))
        self.assertEqual(response.status_code, 302)

    def test_view_requires_permission(self):
        """Test that view requires permission."""
        user_no_perms = AuthUtils.create_user("no_perms_user2")
        self.client.force_login(user_no_perms)
        response = self.client.get(reverse("standingsmanager:my_synced_characters"))
        self.assertEqual(response.status_code, 302)


class TestManageRequestsView(ViewTestCase):
    """Tests for manage_requests view."""

    def test_view_requires_login(self):
        """Test that view requires login."""
        response = self.client.get(reverse("standingsmanager:manage_requests"))
        self.assertEqual(response.status_code, 302)

    def test_view_requires_permission(self):
        """Test that view requires approver permission."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("standingsmanager:manage_requests"))
        self.assertEqual(response.status_code, 302)


class TestManageRevocationsView(ViewTestCase):
    """Tests for manage_revocations view."""

    def test_view_requires_login(self):
        """Test that view requires login."""
        response = self.client.get(reverse("standingsmanager:manage_revocations"))
        self.assertEqual(response.status_code, 302)

    def test_view_requires_permission(self):
        """Test that view requires approver permission."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("standingsmanager:manage_revocations"))
        self.assertEqual(response.status_code, 302)


class TestViewStandingsView(ViewTestCase):
    """Tests for view_standings view."""

    def test_view_requires_login(self):
        """Test that view requires login."""
        response = self.client.get(reverse("standingsmanager:view_standings"))
        self.assertEqual(response.status_code, 302)

    def test_view_requires_permission(self):
        """Test that view requires approver permission."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("standingsmanager:view_standings"))
        self.assertEqual(response.status_code, 302)


class TestAPIEndpoints(ViewTestCase):
    """Tests for API endpoints."""


class TestCSVExport(ViewTestCase):
    """Tests for CSV export."""

    def test_export_requires_login(self):
        """Test that CSV export requires login."""
        response = self.client.get(reverse("standingsmanager:export_standings_csv"))
        self.assertEqual(response.status_code, 302)

    def test_export_requires_permission(self):
        """Test that CSV export requires permission."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("standingsmanager:export_standings_csv"))
        self.assertEqual(response.status_code, 302)
