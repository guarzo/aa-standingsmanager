"""Business logic tests for AA Standings Manager - Sprint 2.

Tests for:
- Permission helper functions
- Scope validation
- Corporation token validation
- Request creation logic
- Validation workflows
"""

from unittest.mock import Mock, patch

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo
from app_utils.testdata_factories import UserMainFactory

from ..models import StandingRequest, StandingRevocation, StandingsEntry
from ..permissions import (
    user_can_approve_standings,
    user_can_manage_standings,
    user_can_request_standings,
    user_can_view_audit_log,
)
from ..validators import (
    can_user_request_character_standing,
    character_has_required_scopes,
    get_required_scopes_for_user,
    validate_corporation_request,
    validate_corporation_token_coverage,
)
from .factories import EveEntityCharacterFactory, EveEntityCorporationFactory


class PermissionHelperTestCase(TestCase):
    """Test permission helper functions."""

    @classmethod
    def setUpTestData(cls):
        """Create permissions for all tests."""
        from django.contrib.contenttypes.models import ContentType
        from ..models import StandingsEntry, StandingRequest, AuditLog

        # Create custom permissions if they don't exist
        content_type = ContentType.objects.get_for_model(StandingRequest)
        Permission.objects.get_or_create(
            codename="approve_standings",
            content_type=content_type,
            defaults={"name": "Can approve standing requests"}
        )

        content_type = ContentType.objects.get_for_model(StandingsEntry)
        Permission.objects.get_or_create(
            codename="manage_standings",
            content_type=content_type,
            defaults={"name": "Can manage standings database"}
        )

    def setUp(self):
        super().setUp()
        self.user = UserMainFactory()

    def test_user_can_request_standings_without_permission(self):
        """Test user cannot request standings without permission."""
        self.assertFalse(user_can_request_standings(self.user))

    def test_user_can_request_standings_with_permission(self):
        """Test user can request standings with permission."""
        permission = Permission.objects.get(
            codename="add_syncedcharacter",
            content_type__app_label="standingsmanager"
        )
        self.user.user_permissions.add(permission)

        self.assertTrue(user_can_request_standings(self.user))

    def test_user_can_approve_standings_without_permission(self):
        """Test user cannot approve standings without permission."""
        self.assertFalse(user_can_approve_standings(self.user))

    def test_user_can_approve_standings_with_permission(self):
        """Test user can approve standings with permission."""
        permission = Permission.objects.get(
            codename="approve_standings",
            content_type__app_label="standingsmanager"
        )
        self.user.user_permissions.add(permission)

        self.assertTrue(user_can_approve_standings(self.user))

    def test_user_can_manage_standings_without_permission(self):
        """Test user cannot manage standings without permission."""
        self.assertFalse(user_can_manage_standings(self.user))

    def test_user_can_manage_standings_with_permission(self):
        """Test user can manage standings with permission."""
        permission = Permission.objects.get(codename="manage_standings")
        self.user.user_permissions.add(permission)

        self.assertTrue(user_can_manage_standings(self.user))

    def test_user_can_view_audit_log_without_permission(self):
        """Test user cannot view audit log without permission."""
        self.assertFalse(user_can_view_audit_log(self.user))

    def test_user_can_view_audit_log_with_permission(self):
        """Test user can view audit log with permission."""
        permission = Permission.objects.get(
            codename="view_auditlog",
            content_type__app_label="standingsmanager"
        )
        self.user.user_permissions.add(permission)

        self.assertTrue(user_can_view_audit_log(self.user))


class ScopeValidationTestCase(TestCase):
    """Test scope validation logic."""

    def setUp(self):
        super().setUp()
        self.user = UserMainFactory()

    def test_get_required_scopes_for_user(self):
        """Test getting required scopes for a user."""
        scopes = get_required_scopes_for_user(self.user)

        # Should include base scopes at minimum
        self.assertIn("esi-characters.read_contacts.v1", scopes)
        self.assertIn("esi-characters.write_contacts.v1", scopes)

    @patch("standingsmanager.validators.Token.objects.filter")
    def test_character_has_required_scopes_with_valid_token(self, mock_token_filter):
        """Test character with valid token and all scopes."""
        character = EveCharacter.objects.create(
            character_id=12345,
            character_name="Test Character",
            corporation_id=1000,
            corporation_name="Test Corp",
        )

        # Mock token with all required scopes
        mock_scope1 = Mock()
        mock_scope1.name = "esi-characters.read_contacts.v1"
        mock_scope2 = Mock()
        mock_scope2.name = "esi-characters.write_contacts.v1"

        mock_token = Mock()
        mock_token.scopes.values_list.return_value = [
            "esi-characters.read_contacts.v1",
            "esi-characters.write_contacts.v1",
        ]

        mock_token_qs = Mock()
        mock_token_qs.require_valid.return_value.first.return_value = mock_token
        mock_token_filter.return_value = mock_token_qs

        has_scopes, missing = character_has_required_scopes(character, self.user)

        self.assertTrue(has_scopes)
        self.assertEqual(missing, [])

    @patch("standingsmanager.validators.Token.objects.filter")
    def test_character_has_required_scopes_missing_scopes(self, mock_token_filter):
        """Test character missing required scopes."""
        character = EveCharacter.objects.create(
            character_id=12345,
            character_name="Test Character",
            corporation_id=1000,
            corporation_name="Test Corp",
        )

        # Mock token with only one scope
        mock_token = Mock()
        mock_token.scopes.values_list.return_value = [
            "esi-characters.read_contacts.v1",
        ]

        mock_token_qs = Mock()
        mock_token_qs.require_valid.return_value.first.return_value = mock_token
        mock_token_filter.return_value = mock_token_qs

        has_scopes, missing = character_has_required_scopes(character, self.user)

        self.assertFalse(has_scopes)
        self.assertIn("esi-characters.write_contacts.v1", missing)

    @patch("standingsmanager.validators.Token.objects.filter")
    def test_character_has_required_scopes_no_token(self, mock_token_filter):
        """Test character without any token."""
        character = EveCharacter.objects.create(
            character_id=12345,
            character_name="Test Character",
            corporation_id=1000,
            corporation_name="Test Corp",
        )

        # Mock no token
        mock_token_qs = Mock()
        mock_token_qs.require_valid.return_value.first.return_value = None
        mock_token_filter.return_value = mock_token_qs

        has_scopes, missing = character_has_required_scopes(character, self.user)

        self.assertFalse(has_scopes)
        self.assertTrue(len(missing) > 0)


class CorporationTokenValidationTestCase(TestCase):
    """Test corporation token validation logic."""

    def setUp(self):
        """Create test user and corporation."""
        self.user = UserMainFactory()
        self.corporation, _ = EveCorporationInfo.objects.get_or_create(
            corporation_id=98000001,
            defaults={
                "corporation_name": "Test Corporation",
                "member_count": 100,
            }
        )

    def test_validate_corporation_token_coverage_no_characters(self):
        """Test validation fails when user has no characters in corp."""
        # Use a unique corporation that no other test uses
        test_corp, _ = EveCorporationInfo.objects.get_or_create(
            corporation_id=98000004,
            defaults={
                "corporation_name": "Test Corporation 4",
                "member_count": 100,
            }
        )

        with self.assertRaises(ValidationError) as context:
            validate_corporation_token_coverage(test_corp, self.user)

        self.assertIn("no characters", str(context.exception).lower())

    @patch("standingsmanager.validators.character_has_required_scopes")
    def test_validate_corporation_token_coverage_all_tokens_valid(
        self, mock_has_scopes
    ):
        """Test validation passes when all characters have valid tokens."""
        # Use a different corporation for this test to avoid conflicts
        test_corp, _ = EveCorporationInfo.objects.get_or_create(
            corporation_id=98000002,
            defaults={
                "corporation_name": "Test Corporation 2",
                "member_count": 100,
            }
        )

        # Create characters in corp
        char1 = EveCharacter.objects.create(
            character_id=12345,
            character_name="Test Char 1",
            corporation_id=test_corp.corporation_id,
            corporation_name=test_corp.corporation_name,
        )
        char2 = EveCharacter.objects.create(
            character_id=12346,
            character_name="Test Char 2",
            corporation_id=test_corp.corporation_id,
            corporation_name=test_corp.corporation_name,
        )

        # Create ownership
        CharacterOwnership.objects.create(
            user=self.user, character=char1, owner_hash="hash1"
        )
        CharacterOwnership.objects.create(
            user=self.user, character=char2, owner_hash="hash2"
        )

        # Mock all characters have scopes
        mock_has_scopes.return_value = (True, [])

        has_coverage, missing_chars = validate_corporation_token_coverage(
            test_corp, self.user
        )

        self.assertTrue(has_coverage)
        self.assertEqual(missing_chars, [])

    @patch("standingsmanager.validators.character_has_required_scopes")
    def test_validate_corporation_token_coverage_missing_tokens(self, mock_has_scopes):
        """Test validation fails when some characters lack tokens."""
        # Use a different corporation for this test to avoid conflicts
        test_corp, _ = EveCorporationInfo.objects.get_or_create(
            corporation_id=98000003,
            defaults={
                "corporation_name": "Test Corporation 3",
                "member_count": 100,
            }
        )

        # Create characters in corp with unique IDs
        char1 = EveCharacter.objects.create(
            character_id=12347,
            character_name="Test Char 3",
            corporation_id=test_corp.corporation_id,
            corporation_name=test_corp.corporation_name,
        )
        char2 = EveCharacter.objects.create(
            character_id=12348,
            character_name="Test Char 4",
            corporation_id=test_corp.corporation_id,
            corporation_name=test_corp.corporation_name,
        )

        # Create ownership
        CharacterOwnership.objects.create(
            user=self.user, character=char1, owner_hash="hash1"
        )
        CharacterOwnership.objects.create(
            user=self.user, character=char2, owner_hash="hash2"
        )

        # Mock one character missing scopes
        def mock_scopes_side_effect(char, user):
            if char.character_id == 12347:
                return (True, [])
            else:
                return (False, ["esi-characters.write_contacts.v1"])

        mock_has_scopes.side_effect = mock_scopes_side_effect

        has_coverage, missing_chars = validate_corporation_token_coverage(
            test_corp, self.user
        )

        self.assertFalse(has_coverage)
        self.assertIn("Test Char 4", missing_chars)
        self.assertEqual(len(missing_chars), 1)

    @patch("standingsmanager.validators.validate_corporation_token_coverage")
    def test_validate_corporation_request_success(self, mock_validate_coverage):
        """Test corporation request validation passes with full coverage."""
        mock_validate_coverage.return_value = (True, [])

        # Should not raise
        try:
            validate_corporation_request(self.corporation, self.user)
        except ValidationError:
            self.fail(
                "validate_corporation_request raised ValidationError unexpectedly"
            )

    @patch("standingsmanager.validators.validate_corporation_token_coverage")
    def test_validate_corporation_request_failure(self, mock_validate_coverage):
        """Test corporation request validation fails without full coverage."""
        mock_validate_coverage.return_value = (
            False,
            ["Test Char 1", "Test Char 2"],
        )

        with self.assertRaises(ValidationError) as context:
            validate_corporation_request(self.corporation, self.user)

        self.assertIn("valid tokens", str(context.exception).lower())


class RequestCreationLogicTestCase(TestCase):
    """Test request creation and eligibility logic."""

    def setUp(self):
        """Set up for each test."""
        self.user = UserMainFactory()
        self.character_entity = EveEntityCharacterFactory()
        self.corporation_entity = EveEntityCorporationFactory()

        self.character, _ = EveCharacter.objects.get_or_create(
            character_id=self.character_entity.id,
            defaults={
                "character_name": self.character_entity.name,
                "corporation_id": 1000,
                "corporation_name": "Test Corp",
            }
        )
        self.ownership, _ = CharacterOwnership.objects.get_or_create(
            user=self.user,
            character=self.character,
            defaults={"owner_hash": "test_hash"}
        )

    def test_can_user_request_character_standing_without_permission(self):
        """Test user cannot request without permission."""
        can_request, error = can_user_request_character_standing(
            self.character, self.user
        )

        self.assertFalse(can_request)
        self.assertIn("permission", error.lower())

    @patch("standingsmanager.validators.character_has_required_scopes")
    def test_can_user_request_character_standing_without_scopes(self, mock_has_scopes):
        """Test user cannot request without required scopes."""
        # Grant permission
        permission = Permission.objects.get(codename="add_syncedcharacter")
        self.user.user_permissions.add(permission)

        # Mock missing scopes
        mock_has_scopes.return_value = (
            False,
            ["esi-characters.write_contacts.v1"],
        )

        can_request, error = can_user_request_character_standing(
            self.character, self.user
        )

        self.assertFalse(can_request)
        self.assertIn("missing required scopes", error.lower())

    @patch("standingsmanager.validators.character_has_required_scopes")
    def test_can_user_request_character_standing_already_exists(self, mock_has_scopes):
        """Test user cannot request if standing already exists."""
        # Grant permission
        permission = Permission.objects.get(codename="add_syncedcharacter")
        self.user.user_permissions.add(permission)

        # Mock has scopes
        mock_has_scopes.return_value = (True, [])

        # Create existing standing
        StandingsEntry.objects.create(
            eve_entity=self.character_entity,
            entity_type=StandingsEntry.EntityType.CHARACTER,
            standing=5.0,
            added_by=self.user,
        )

        can_request, error = can_user_request_character_standing(
            self.character, self.user
        )

        self.assertFalse(can_request)
        self.assertIn("already has a standing", error.lower())

    @patch("standingsmanager.validators.character_has_required_scopes")
    def test_can_user_request_character_standing_pending_request_exists(
        self, mock_has_scopes
    ):
        """Test user cannot request if pending request exists."""
        # Grant permission
        permission = Permission.objects.get(codename="add_syncedcharacter")
        self.user.user_permissions.add(permission)

        # Mock has scopes
        mock_has_scopes.return_value = (True, [])

        # Create pending request
        StandingRequest.objects.create(
            eve_entity=self.character_entity,
            entity_type=StandingRequest.EntityType.CHARACTER,
            requested_by=self.user,
            state=StandingRequest.State.PENDING,
        )

        can_request, error = can_user_request_character_standing(
            self.character, self.user
        )

        self.assertFalse(can_request)
        self.assertIn("pending request already exists", error.lower())

    @patch("standingsmanager.validators.character_has_required_scopes")
    def test_can_user_request_character_standing_success(self, mock_has_scopes):
        """Test user can request when all conditions are met."""
        # Grant permission
        permission = Permission.objects.get(codename="add_syncedcharacter")
        self.user.user_permissions.add(permission)

        # Mock has scopes
        mock_has_scopes.return_value = (True, [])

        can_request, error = can_user_request_character_standing(
            self.character, self.user
        )

        self.assertTrue(can_request)
        self.assertIsNone(error)

    def test_can_user_request_character_standing_not_owned(self):
        """Test user cannot request for character they don't own."""
        # Grant permission
        permission = Permission.objects.get(codename="add_syncedcharacter")
        self.user.user_permissions.add(permission)

        # Create character owned by someone else
        other_user = UserMainFactory()
        other_character = EveCharacter.objects.create(
            character_id=99999,
            character_name="Other Character",
            corporation_id=1000,
            corporation_name="Test Corp",
        )
        CharacterOwnership.objects.create(
            user=other_user,
            character=other_character,
            owner_hash="other_hash",
        )

        can_request, error = can_user_request_character_standing(
            other_character, self.user
        )

        self.assertFalse(can_request)
        self.assertIn("do not own", error.lower())


class ManagerMethodsTestCase(TestCase):
    """Test manager methods for request creation."""

    def setUp(self):
        super().setUp()
        self.user = UserMainFactory()

    def test_create_character_request_success(self):
        """Test creating character request through manager."""
        character = EveCharacter.objects.create(
            character_id=12345,
            character_name="Test Character",
            corporation_id=1000,
            corporation_name="Test Corp",
        )

        request = StandingRequest.objects.create_character_request(character, self.user)

        self.assertIsNotNone(request)
        self.assertEqual(request.entity_type, StandingRequest.EntityType.CHARACTER)
        self.assertEqual(request.requested_by, self.user)
        self.assertEqual(request.state, StandingRequest.State.PENDING)

    def test_create_character_request_duplicate(self):
        """Test creating duplicate character request fails."""
        character = EveCharacter.objects.create(
            character_id=12345,
            character_name="Test Character",
            corporation_id=1000,
            corporation_name="Test Corp",
        )

        # Create first request
        StandingRequest.objects.create_character_request(character, self.user)

        # Try to create duplicate
        with self.assertRaises(ValidationError) as context:
            StandingRequest.objects.create_character_request(character, self.user)

        self.assertIn("pending request already exists", str(context.exception).lower())

    def test_create_corporation_request_success(self):
        """Test creating corporation request through manager."""
        corporation, _ = EveCorporationInfo.objects.get_or_create(
            corporation_id=98000005,
            defaults={
                "corporation_name": "Test Corporation",
                "member_count": 100,
            }
        )

        request = StandingRequest.objects.create_corporation_request(
            corporation, self.user
        )

        self.assertIsNotNone(request)
        self.assertEqual(request.entity_type, StandingRequest.EntityType.CORPORATION)
        self.assertEqual(request.requested_by, self.user)
        self.assertEqual(request.state, StandingRequest.State.PENDING)


class RevocationLogicTestCase(TestCase):
    """Test revocation creation and management logic."""

    def setUp(self):
        """Create standing entry for each test."""
        self.user = UserMainFactory()
        self.character_entity = EveEntityCharacterFactory()

        self.standing = StandingsEntry.objects.create(
            eve_entity=self.character_entity,
            entity_type=StandingsEntry.EntityType.CHARACTER,
            standing=5.0,
            added_by=self.user,
        )

    def test_create_revocation_for_entity_success(self):
        """Test creating revocation through manager."""
        revocation = StandingRevocation.objects.create_for_entity(
            self.character_entity,
            reason=StandingRevocation.Reason.USER_REQUEST,
            user=self.user,
        )

        self.assertIsNotNone(revocation)
        self.assertEqual(revocation.requested_by, self.user)
        self.assertEqual(revocation.reason, StandingRevocation.Reason.USER_REQUEST)
        self.assertEqual(revocation.state, StandingRevocation.State.PENDING)

    def test_create_revocation_no_standing_exists(self):
        """Test creating revocation fails if no standing exists."""
        other_entity = EveEntityCharacterFactory()

        with self.assertRaises(ValidationError) as context:
            StandingRevocation.objects.create_for_entity(
                other_entity,
                reason=StandingRevocation.Reason.USER_REQUEST,
                user=self.user,
            )

        self.assertIn("no standing exists", str(context.exception).lower())

    def test_create_auto_revocation(self):
        """Test creating auto-revocation (system-initiated)."""
        revocation = StandingRevocation.objects.create_for_entity(
            self.character_entity,
            reason=StandingRevocation.Reason.LOST_PERMISSION,
            user=None,  # Auto-revocation has no user
        )

        self.assertIsNone(revocation.requested_by)
        self.assertEqual(revocation.reason, StandingRevocation.Reason.LOST_PERMISSION)

    def test_create_duplicate_revocation_fails(self):
        """Test creating duplicate revocation fails."""
        # Create first revocation
        StandingRevocation.objects.create_for_entity(
            self.character_entity,
            reason=StandingRevocation.Reason.USER_REQUEST,
            user=self.user,
        )

        # Try to create duplicate
        with self.assertRaises(ValidationError) as context:
            StandingRevocation.objects.create_for_entity(
                self.character_entity,
                reason=StandingRevocation.Reason.USER_REQUEST,
                user=self.user,
            )

        self.assertIn(
            "pending revocation already exists", str(context.exception).lower()
        )
