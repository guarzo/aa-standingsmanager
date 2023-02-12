from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse
from esi.models import Token

from allianceauth.authentication.models import CharacterOwnership
from app_utils.testing import NoSocketsTestCase, create_user_from_evecharacter

from .. import views
from ..models import EveEntity, SyncedCharacter, SyncManager
from .factories import EveContactFactory, SyncedCharacterFactory, SyncManagerFactory
from .utils import ALLIANCE_CONTACTS, LoadTestDataMixin

MODULE_PATH = "standingssync.views"


class TestMainScreen(LoadTestDataMixin, TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # user 1 is the manager
        cls.user_1, _ = create_user_from_evecharacter(cls.character_1.character_id)
        # sync manager with contacts
        cls.sync_manager = SyncManagerFactory(user=cls.user_1, version_hash="new")
        for contact in ALLIANCE_CONTACTS:
            EveContactFactory(
                manager=cls.sync_manager,
                eve_entity=EveEntity.objects.get(id=contact["contact_id"]),
                standing=contact["standing"],
            )

        # user 2 is a normal user and has two alts and permission
        cls.user_2, _ = create_user_from_evecharacter(
            cls.character_2.character_id,
            permissions=["standingssync.add_syncedcharacter"],
        )
        cls.alt_ownership_1 = CharacterOwnership.objects.create(
            character=cls.character_4, owner_hash="x4", user=cls.user_2
        )
        cls.user_2 = User.objects.get(pk=cls.user_2.pk)
        cls.sync_char = SyncedCharacterFactory(
            manager=cls.sync_manager, character_ownership=cls.alt_ownership_1
        )

        # user 3 has no permission
        cls.user_3, _ = create_user_from_evecharacter(cls.character_3.character_id)
        cls.factory = RequestFactory()

    def test_user_with_permission_can_open_app(self):
        request = self.factory.get(reverse("standingssync:index"))
        request.user = self.user_2
        response = views.index(request)
        self.assertEqual(response.status_code, 200)

    def test_user_wo_permission_can_not_open_app(self):
        request = self.factory.get(reverse("standingssync:index"))
        request.user = self.user_3
        response = views.index(request)
        self.assertEqual(response.status_code, 302)

    @patch(MODULE_PATH + ".messages")
    def test_user_can_remove_sync_char(self, mock_messages):
        request = self.factory.get(
            reverse("standingssync:remove_character", args=(self.sync_char.pk,))
        )
        request.user = self.user_2
        response = views.remove_character(request, self.sync_char.pk)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(mock_messages.success.called)
        self.assertFalse(SyncedCharacter.objects.filter(pk=self.sync_char.pk).exists())

    def test_user_with_permission_can_set_alliance_char(self):
        pass

    def test_user_wo_permission_can_not_set_alliance_char(self):
        pass


@patch(MODULE_PATH + ".tasks.run_character_sync")
@patch(MODULE_PATH + ".messages")
class TestAddSyncChar(LoadTestDataMixin, NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # user 1 is the manager
        cls.user_1, _ = create_user_from_evecharacter(
            cls.character_1.character_id, permissions=["standingssync.add_syncmanager"]
        )
        # sync manager with contacts
        cls.sync_manager = SyncManagerFactory(user=cls.user_1, version_hash="new")
        for contact in ALLIANCE_CONTACTS:
            EveContactFactory(
                manager=cls.sync_manager,
                eve_entity=EveEntity.objects.get(id=contact["contact_id"]),
                standing=contact["standing"],
            )

        # user 2 is a normal user and has three alts
        cls.user_2, _ = create_user_from_evecharacter(
            cls.character_2.character_id,
            permissions=["standingssync.add_syncedcharacter"],
        )
        cls.alt_ownership_1 = CharacterOwnership.objects.create(
            character=cls.character_4, owner_hash="x4", user=cls.user_2
        )
        cls.alt_ownership_2 = CharacterOwnership.objects.create(
            character=cls.character_5, owner_hash="x5", user=cls.user_2
        )
        CharacterOwnership.objects.create(
            character=cls.character_6, owner_hash="x6", user=cls.user_2
        )
        cls.factory = RequestFactory()

    def make_request(self, user, character):
        token = Mock(spec=Token)
        token.character_id = character.character_id
        request = self.factory.get(reverse("standingssync:add_character"))
        request.user = user
        request.token = token
        middleware = SessionMiddleware(Mock())
        middleware.process_request(request)
        orig_view = views.add_character.__wrapped__.__wrapped__.__wrapped__
        return orig_view(request, token)

    def test_users_can_not_add_alliance_members(
        self, mock_messages, mock_run_character_sync
    ):
        response = self.make_request(self.user_2, self.character_2)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingssync:index"))
        self.assertTrue(mock_messages.warning.called)
        self.assertFalse(mock_run_character_sync.delay.called)

    def test_user_can_add_blue_alt(self, mock_messages, mock_run_character_sync):
        response = self.make_request(self.user_2, self.character_4)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingssync:index"))
        self.assertTrue(mock_messages.success.called)
        self.assertTrue(mock_run_character_sync.delay.called)
        self.assertTrue(
            SyncedCharacter.objects.filter(manager=self.sync_manager)
            .filter(character_ownership__character=self.character_4)
            .exists()
        )

    @patch(MODULE_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0)
    def test_user_can_add_neutral_alt(self, mock_messages, mock_run_character_sync):
        response = self.make_request(self.user_2, self.character_6)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingssync:index"))
        self.assertTrue(mock_messages.success.called)
        self.assertTrue(mock_run_character_sync.delay.called)
        self.assertTrue(
            SyncedCharacter.objects.filter(manager=self.sync_manager)
            .filter(character_ownership__character=self.character_6)
            .exists()
        )

    def test_user_can_not_add_non_blue_alt(
        self, mock_messages, mock_run_character_sync
    ):
        response = self.make_request(self.user_2, self.character_5)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingssync:index"))
        self.assertTrue(mock_messages.warning.called)
        self.assertFalse(mock_run_character_sync.delay.called)
        self.assertFalse(
            SyncedCharacter.objects.filter(manager=self.sync_manager)
            .filter(character_ownership__character=self.character_5)
            .exists()
        )


@patch(MODULE_PATH + ".tasks")
@patch(MODULE_PATH + ".messages")
class TestAddAllianceManager(LoadTestDataMixin, NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # user 1 is the manager
        cls.user_1, _ = create_user_from_evecharacter(
            cls.character_1.character_id,
            permissions=[
                "standingssync.add_syncmanager",
                "standingssync.add_syncedcharacter",
            ],
        )
        # sync manager with contacts
        cls.sync_manager = SyncManagerFactory(user=cls.user_1, version_hash="new")
        for contact in ALLIANCE_CONTACTS:
            EveContactFactory(
                manager=cls.sync_manager,
                eve_entity=EveEntity.objects.get(id=contact["contact_id"]),
                standing=contact["standing"],
            )

        # user 2 is a normal user and has two alts
        cls.user_2, _ = create_user_from_evecharacter(
            cls.character_2.character_id,
            permissions=["standingssync.add_syncedcharacter"],
        )
        cls.alt_ownership_1 = CharacterOwnership.objects.create(
            character=cls.character_4, owner_hash="x4", user=cls.user_2
        )
        cls.alt_ownership_2 = CharacterOwnership.objects.create(
            character=cls.character_5, owner_hash="x5", user=cls.user_2
        )
        cls.factory = RequestFactory()

    def make_request(self, user, character):
        token = Mock(spec=Token)
        token.character_id = character.character_id
        request = self.factory.get(reverse("standingssync:add_alliance_manager"))
        request.user = user
        request.token = token
        middleware = SessionMiddleware(Mock())
        middleware.process_request(request)
        orig_view = views.add_alliance_manager.__wrapped__.__wrapped__.__wrapped__
        return orig_view(request, token)

    def test_user_with_permission_can_add_alliance_manager(
        self, mock_messages, mock_tasks
    ):
        response = self.make_request(self.user_1, self.character_1)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingssync:index"))
        self.assertTrue(mock_messages.success.called)
        self.assertTrue(mock_tasks.run_manager_sync.delay.called)
        self.assertTrue(mock_tasks.sync_all_wars.delay.called)
        self.assertTrue(
            SyncManager.objects.filter(alliance=self.alliance_1)
            .filter(character_ownership__character=self.character_1)
            .exists()
        )

    def test_should_sync_wars_when_adding_alliance_char_and_feature_enabled(
        self, mock_messages, mock_tasks
    ):
        with patch(MODULE_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True):
            self.make_request(self.user_1, self.character_1)
        self.assertTrue(mock_tasks.sync_all_wars.delay.called)

    def test_should_not_sync_wars_when_adding_alliance_char_and_feature_disabled(
        self, mock_messages, mock_tasks
    ):
        with patch(MODULE_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", False):
            self.make_request(self.user_1, self.character_1)
        self.assertFalse(mock_tasks.sync_all_wars.delay.called)

    """
    def test_user_wo_permission_can_not_add_alliance_manager(
        self, mock_messages, mock_tasks
    ):
        response = self.make_request(self.user_2, self.character_2)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('standingssync:index'))
        self.assertFalse(mock_tasks.delay.called)
        self.assertFalse(
            SyncManager.objects
            .filter(alliance=self.alliance_1)
            .filter(character_ownership__character=self.character_2)
            .exists()
        )
    """

    def test_character_for_manager_must_be_alliance_member(
        self, mock_messages, mock_tasks
    ):
        response = self.make_request(self.user_1, self.character_5)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("standingssync:index"))
        self.assertTrue(mock_messages.warning.called)
        self.assertFalse(mock_tasks.run_manager_sync.delay.called)
        self.assertFalse(
            SyncManager.objects.filter(alliance=self.alliance_1)
            .filter(character_ownership__character=self.character_5)
            .exists()
        )
