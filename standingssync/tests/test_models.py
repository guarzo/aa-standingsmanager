import datetime as dt
from unittest.mock import patch

from django.utils.timezone import now
from esi.errors import TokenExpiredError, TokenInvalidError
from eveuniverse.models import EveEntity

from allianceauth.eveonline.models import EveCharacter
from app_utils.esi_testing import BravadoOperationStub
from app_utils.testing import (
    NoSocketsTestCase,
    add_character_to_user,
    create_user_from_evecharacter,
)

from ..models import EveContact, EveWar, SyncedCharacter, SyncManager
from .factories import (
    EveContactFactory,
    EveContactWarTargetFactory,
    EveEntityAllianceFactory,
    EveWarFactory,
    SyncedCharacterFactory,
    SyncManagerFactory,
    UserMainSyncerFactory,
)
from .utils import (
    ALLIANCE_CONTACTS,
    EsiCharacterContactsStub,
    EsiContact,
    EsiContactLabel,
    LoadTestDataMixin,
)

ESI_CONTACTS_PATH = "standingssync.core.esi_contacts"
MODELS_PATH = "standingssync.models"


class TestGetEffectiveStanding(LoadTestDataMixin, NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        user, _ = create_user_from_evecharacter(
            cls.character_1.character_id, permissions=["standingssync.add_syncmanager"]
        )
        cls.sync_manager = SyncManagerFactory(user=user)
        contacts = [
            {"contact_id": 1001, "contact_type": "character", "standing": -10},
            {"contact_id": 2001, "contact_type": "corporation", "standing": 10},
            {"contact_id": 3001, "contact_type": "alliance", "standing": 5},
        ]
        for contact in contacts:
            EveContactFactory(
                manager=cls.sync_manager,
                eve_entity=EveEntity.objects.get(id=contact["contact_id"]),
                standing=contact["standing"],
            )

    def test_char_with_character_standing(self):
        c1 = EveCharacter(
            character_id=1001,
            character_name="Char 1",
            corporation_id=201,
            corporation_name="Corporation 1",
            corporation_ticker="C1",
        )
        self.assertEqual(self.sync_manager.get_effective_standing(c1), -10)

    def test_char_with_corporation_standing(self):
        c2 = EveCharacter(
            character_id=1002,
            character_name="Char 2",
            corporation_id=2001,
            corporation_name="Corporation 1",
            corporation_ticker="C1",
        )
        self.assertEqual(self.sync_manager.get_effective_standing(c2), 10)

    def test_char_with_alliance_standing(self):
        c3 = EveCharacter(
            character_id=1003,
            character_name="Char 3",
            corporation_id=2003,
            corporation_name="Corporation 3",
            corporation_ticker="C2",
            alliance_id=3001,
            alliance_name="Alliance 1",
            alliance_ticker="A1",
        )
        self.assertEqual(self.sync_manager.get_effective_standing(c3), 5)

    def test_char_without_standing_and_has_alliance(self):
        c4 = EveCharacter(
            character_id=1003,
            character_name="Char 3",
            corporation_id=2003,
            corporation_name="Corporation 3",
            corporation_ticker="C2",
            alliance_id=3002,
            alliance_name="Alliance 2",
            alliance_ticker="A2",
        )
        self.assertEqual(self.sync_manager.get_effective_standing(c4), 0.0)

    def test_char_without_standing_and_without_alliance_1(self):
        c4 = EveCharacter(
            character_id=1003,
            character_name="Char 3",
            corporation_id=2003,
            corporation_name="Corporation 3",
            corporation_ticker="C2",
            alliance_id=None,
            alliance_name=None,
            alliance_ticker=None,
        )
        self.assertEqual(self.sync_manager.get_effective_standing(c4), 0.0)

    def test_char_without_standing_and_without_alliance_2(self):
        c4 = EveCharacter(
            character_id=1003,
            character_name="Char 3",
            corporation_id=2003,
            corporation_name="Corporation 3",
            corporation_ticker="C2",
        )
        self.assertEqual(self.sync_manager.get_effective_standing(c4), 0.0)


@patch(ESI_CONTACTS_PATH + ".esi")
class TestSyncManagerEsi(LoadTestDataMixin, NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user, _ = create_user_from_evecharacter(
            cls.character_1.character_id, permissions=["standingssync.add_syncmanager"]
        )
        add_character_to_user(
            cls.user, cls.character_1, scopes=SyncManager.get_esi_scopes()
        )

    def test_should_sync_contacts(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.side_effect = (
            lambda *args, **kwargs: BravadoOperationStub(ALLIANCE_CONTACTS)
        )
        sync_manager = SyncManagerFactory(user=self.user)
        # when
        with patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", False):
            result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)
        sync_manager.refresh_from_db()
        expected_contact_ids = {x["contact_id"] for x in ALLIANCE_CONTACTS}
        expected_contact_ids.add(self.character_1.alliance_id)
        result_contact_ids = set(
            sync_manager.contacts.values_list("eve_entity_id", flat=True)
        )
        self.assertSetEqual(expected_contact_ids, result_contact_ids)
        contact = sync_manager.contacts.get(eve_entity_id=3015)
        self.assertEqual(contact.standing, 10.0)
        self.assertFalse(contact.is_war_target)

    def test_should_sync_contacts_and_war_targets(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.side_effect = (
            lambda *args, **kwargs: BravadoOperationStub(ALLIANCE_CONTACTS)
        )
        sync_manager = SyncManagerFactory(user=self.user)
        EveWar.objects.create(
            id=8,
            aggressor=EveEntity.objects.get(id=3015),
            defender=EveEntity.objects.get(id=3001),
            declared=now() - dt.timedelta(days=3),
            started=now() - dt.timedelta(days=2),
            is_mutual=False,
            is_open_for_allies=False,
        )
        # when
        with patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True):
            result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)
        sync_manager.refresh_from_db()
        expected_contact_ids = {x["contact_id"] for x in ALLIANCE_CONTACTS}
        expected_contact_ids.add(self.character_1.alliance_id)
        result_contact_ids = set(
            sync_manager.contacts.values_list("eve_entity_id", flat=True)
        )
        self.assertSetEqual(expected_contact_ids, result_contact_ids)
        contact = sync_manager.contacts.get(eve_entity_id=3015)
        self.assertEqual(contact.standing, -10.0)
        self.assertTrue(contact.is_war_target)


class TestSyncManagerErrorCases(LoadTestDataMixin, NoSocketsTestCase):
    def test_should_abort_when_no_char(self):
        # given
        sync_manager = SyncManagerFactory(
            alliance=self.alliance_1, character_ownership=None
        )
        # when/then
        with self.assertRaises(RuntimeError):
            sync_manager.update_from_esi()

    def test_should_abort_when_insufficient_permission(self):
        # given
        user, _ = create_user_from_evecharacter(self.character_1.character_id)
        add_character_to_user(
            user, self.character_1, scopes=SyncManager.get_esi_scopes()
        )
        sync_manager = SyncManagerFactory(user=user)
        # when/then
        with self.assertRaises(RuntimeError):
            sync_manager.update_from_esi()

    def test_should_report_error_when_character_has_no_valid_token(self):
        # given
        user, _ = create_user_from_evecharacter(
            self.character_1.character_id, permissions=["standingssync.add_syncmanager"]
        )
        add_character_to_user(
            user, self.character_1  # Token without valid scope will not be found
        )
        sync_manager = SyncManagerFactory(user=user)
        # when/then
        with self.assertRaises(RuntimeError):
            sync_manager.update_from_esi()


@patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
@patch(ESI_CONTACTS_PATH + ".esi")
class TestSyncManager2(NoSocketsTestCase):
    @staticmethod
    def _fetch_war_targets():
        return set(
            EveContact.objects.filter(is_war_target=True).values_list(
                "eve_entity_id", flat=True
            )
        )

    def test_should_report_sync_as_ok(self, dummy):
        # given
        my_dt = now()
        sync_manager = SyncManagerFactory(
            last_update_at=my_dt - dt.timedelta(minutes=1)
        )
        # when/then
        with patch(MODELS_PATH + ".STANDINGSSYNC_TIMEOUT_MANAGER_SYNC", 60):
            self.assertTrue(sync_manager.is_sync_fresh)

    def test_should_report_sync_as_not_ok(self, dummy):
        # given
        my_dt = now()
        sync_manager = SyncManagerFactory(
            last_update_at=my_dt - dt.timedelta(minutes=61)
        )
        # when/then
        with patch(MODELS_PATH + ".STANDINGSSYNC_TIMEOUT_MANAGER_SYNC", 60):
            self.assertFalse(sync_manager.is_sync_fresh)

    def test_should_add_war_target_contact_as_aggressor_1(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub([])
        )
        sync_manager = SyncManagerFactory()
        war = EveWarFactory(
            aggressor=EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id)
        )
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)
        sync_manager.refresh_from_db()
        self.assertSetEqual(self._fetch_war_targets(), {war.defender.id})

    def test_should_add_war_target_contact_as_aggressor_2(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub([])
        )
        sync_manager = SyncManagerFactory()
        ally = EveEntityAllianceFactory()
        war = EveWarFactory(
            aggressor=EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id),
            allies=[ally],
        )
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)
        sync_manager.refresh_from_db()
        self.assertSetEqual(self._fetch_war_targets(), {war.defender.id, ally.id})

    def test_should_add_war_target_contact_as_defender(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub([])
        )
        sync_manager = SyncManagerFactory()
        war = EveWarFactory(
            defender=EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id)
        )
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)
        sync_manager.refresh_from_db()
        self.assertSetEqual(self._fetch_war_targets(), {war.aggressor.id})

    def test_should_add_war_target_contact_as_ally(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub([])
        )
        sync_manager = SyncManagerFactory()
        war = EveWarFactory(
            allies=[EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id)]
        )
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)
        sync_manager.refresh_from_db()
        self.assertSetEqual(self._fetch_war_targets(), {war.aggressor.id})

    def test_should_not_add_war_target_contact_from_unrelated_war(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub([])
        )
        sync_manager = SyncManagerFactory()
        EveWarFactory()
        EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id)
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)
        sync_manager.refresh_from_db()
        self.assertSetEqual(self._fetch_war_targets(), set())

    def test_remove_outdated_war_target_contacts(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub([])
        )
        sync_manager = SyncManagerFactory()
        war = EveWarFactory(
            defender=EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id),
            finished=now(),
        )
        EveContactWarTargetFactory(manager=sync_manager, eve_entity=war.aggressor)
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)
        sync_manager.refresh_from_db()
        self.assertSetEqual(self._fetch_war_targets(), set())

    def test_do_nothing_when_contacts_are_unchanged(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub([])
        )
        my_version_hash = SyncManager._calculate_version_hash({})
        sync_manager = SyncManagerFactory(version_hash=my_version_hash)
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)


@patch(ESI_CONTACTS_PATH + ".STANDINGSSYNC_WAR_TARGETS_LABEL_NAME", "WAR TARGETS")
@patch(ESI_CONTACTS_PATH + ".esi")
class TestSyncCharacterEsi(LoadTestDataMixin, NoSocketsTestCase):
    CHARACTER_CONTACTS = [
        EsiContact(1014, EsiContact.ContactType.CHARACTER, standing=10.0),
        EsiContact(2011, EsiContact.ContactType.CORPORATION, standing=5.0),
        EsiContact(3011, EsiContact.ContactType.ALLIANCE, standing=-10.0),
    ]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # 1 user with 1 alt character
        cls.user_1, _ = create_user_from_evecharacter(
            cls.character_1.character_id,
            permissions=["standingssync.add_syncedcharacter"],
        )
        cls.alt_ownership_2 = add_character_to_user(
            cls.user_1,
            character=cls.character_2,
            scopes=SyncedCharacter.get_esi_scopes(),
        )
        cls.sync_manager = SyncManagerFactory(user=cls.user_1, version_hash="new")
        # add contacts to sync manager
        for contact in ALLIANCE_CONTACTS:
            EveContactFactory(
                manager=cls.sync_manager,
                eve_entity=EveEntity.objects.get(id=contact["contact_id"]),
                standing=contact["standing"],
            )
        # set to contacts as war targets
        cls.sync_manager.contacts.filter(eve_entity_id__in=[1014, 3013]).update(
            is_war_target=True, standing=-10.0
        )
        cls.alliance_contacts = [
            cls.eve_contact_2_esi_contact(obj)
            for obj in cls.sync_manager.contacts.all()
        ]

    @staticmethod
    def eve_contact_2_esi_contact(eve_contact):
        map_category_2_type = {
            EveEntity.CATEGORY_CHARACTER: EsiContact.ContactType.CHARACTER,
            EveEntity.CATEGORY_CORPORATION: EsiContact.ContactType.CORPORATION,
            EveEntity.CATEGORY_ALLIANCE: EsiContact.ContactType.ALLIANCE,
        }
        return EsiContact(
            contact_id=eve_contact.eve_entity_id,
            contact_type=map_category_2_type[eve_contact.eve_entity.category],
            standing=eve_contact.standing,
        )

    def setUp(self) -> None:
        self.maxDiff = None
        self.synced_character_2 = SyncedCharacterFactory(
            character_ownership=self.alt_ownership_2, manager=self.sync_manager
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    def test_should_do_nothing_if_no_update_needed(self, mock_esi):
        # given
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(
            self.synced_character_2.character_ownership.character.character_id,
            self.CHARACTER_CONTACTS,
        )
        esi_character_contacts.setup_esi_mock(mock_esi)
        self.synced_character_2.version_hash = self.sync_manager.version_hash
        self.synced_character_2.save()
        # when
        result = self.synced_character_2.update()
        # then
        self.synced_character_2.refresh_from_db()
        self.assertIsNone(result)
        self.assertIsNotNone(self.synced_character_2.last_update_at)

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    def test_should_replace_all_contacts_1(self, mock_esi):
        """run normal sync for a character which has blue standing"""
        # given
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(
            self.synced_character_2.character_id, self.CHARACTER_CONTACTS
        )
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        result = self.synced_character_2.update()
        # then
        self.synced_character_2.refresh_from_db()
        self.assertTrue(result)
        self.assertIsNotNone(self.synced_character_2.last_update_at)
        alliance_contacts_2 = {
            obj
            for obj in self.alliance_contacts
            if obj.contact_id != self.synced_character_2.character_id
        }
        self.assertSetEqual(
            set(esi_character_contacts.contacts(self.synced_character_2.character_id)),
            alliance_contacts_2,
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.0)
    def test_should_replace_all_contacts_2(self, mock_esi):
        """run normal sync for a character which has no standing and allow neutrals"""
        # given
        alt_ownership_3 = add_character_to_user(
            self.user_1,
            character=self.character_3,
            scopes=SyncedCharacter.get_esi_scopes(),
        )
        synced_character = SyncedCharacterFactory(
            character_ownership=alt_ownership_3, manager=self.sync_manager
        )
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(
            synced_character.character_id, self.CHARACTER_CONTACTS
        )
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        result = synced_character.update()
        # then
        synced_character.refresh_from_db()
        self.assertTrue(result)
        self.assertSetEqual(
            set(esi_character_contacts.contacts(synced_character.character_id)),
            set(self.alliance_contacts),
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    def test_should_replace_all_contacts_and_add_war_targets(self, mock_esi):
        # given
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_labels(
            self.synced_character_2.character_id, [EsiContactLabel(1, "war targets")]
        )
        esi_character_contacts.setup_contacts(
            self.synced_character_2.character_id, self.CHARACTER_CONTACTS
        )
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        result = self.synced_character_2.update()
        # then
        self.synced_character_2.refresh_from_db()
        self.assertTrue(result)
        result = set(
            esi_character_contacts.contacts(self.synced_character_2.character_id)
        )
        expected = {
            EsiContact(
                1014,
                EsiContact.ContactType.CHARACTER,
                standing=-10.0,
                label_ids=[1],
            ),
            EsiContact(3011, EsiContact.ContactType.ALLIANCE, standing=-10.0),
            EsiContact(
                3013, EsiContact.ContactType.ALLIANCE, standing=-10.0, label_ids=[1]
            ),
            EsiContact(1016, EsiContact.ContactType.CHARACTER, standing=10.0),
            EsiContact(2013, EsiContact.ContactType.CORPORATION, standing=5.0),
            EsiContact(2012, EsiContact.ContactType.CORPORATION, standing=-5.0),
            EsiContact(1005, EsiContact.ContactType.CHARACTER, standing=-10.0),
            EsiContact(1013, EsiContact.ContactType.CHARACTER, standing=-5.0),
            EsiContact(3014, EsiContact.ContactType.ALLIANCE, standing=5.0),
            EsiContact(2015, EsiContact.ContactType.CORPORATION, standing=10.0),
            EsiContact(2011, EsiContact.ContactType.CORPORATION, standing=-10.0),
            EsiContact(2014, EsiContact.ContactType.CORPORATION, standing=0.0),
            EsiContact(3015, EsiContact.ContactType.ALLIANCE, standing=10.0),
            EsiContact(1012, EsiContact.ContactType.CHARACTER, standing=-10.0),
            EsiContact(1015, EsiContact.ContactType.CHARACTER, standing=5.0),
            EsiContact(1004, EsiContact.ContactType.CHARACTER, standing=10.0),
            EsiContact(3012, EsiContact.ContactType.ALLIANCE, standing=-5.0),
        }
        self.assertSetEqual(result, expected)

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    def test_should_update_war_targets_only_1(self, mock_esi):
        # given
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(
            self.synced_character_2.character_id, self.CHARACTER_CONTACTS
        )
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        result = self.synced_character_2.update()
        # then
        self.synced_character_2.refresh_from_db()
        self.assertTrue(result)
        expected = {
            EsiContact(1014, EsiContact.ContactType.CHARACTER, standing=-10.0),
            EsiContact(2011, EsiContact.ContactType.CORPORATION, standing=5.0),
            EsiContact(3011, EsiContact.ContactType.ALLIANCE, standing=-10.0),
            EsiContact(3013, EsiContact.ContactType.ALLIANCE, standing=-10.0),
        }
        self.assertSetEqual(
            set(esi_character_contacts.contacts(self.synced_character_2.character_id)),
            expected,
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    def test_should_update_war_targets_only_2(self, mock_esi):
        # given
        esi_character_contacts = EsiCharacterContactsStub()
        war_target_label = EsiContactLabel(99, "war targets")
        esi_character_contacts.setup_labels(
            self.synced_character_2.character_id,
            [war_target_label, EsiContactLabel(1, "other")],
        )
        esi_character_contacts.setup_contacts(
            self.synced_character_2.character_id, self.CHARACTER_CONTACTS
        )
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        result = self.synced_character_2.update()
        # then
        self.synced_character_2.refresh_from_db()
        self.assertTrue(result)
        expected = {
            EsiContact(
                1014,
                EsiContact.ContactType.CHARACTER,
                standing=-10.0,
                label_ids=[war_target_label.id],
            ),
            EsiContact(2011, EsiContact.ContactType.CORPORATION, standing=5.0),
            EsiContact(3011, EsiContact.ContactType.ALLIANCE, standing=-10.0),
            EsiContact(
                3013,
                EsiContact.ContactType.ALLIANCE,
                standing=-10.0,
                label_ids=[war_target_label.id],
            ),
        }
        self.assertSetEqual(
            set(esi_character_contacts.contacts(self.synced_character_2.character_id)),
            expected,
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    def test_should_remove_outdated_war_targets_with_label(self, mock_esi):
        # given
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_labels(
            self.synced_character_2.character_id, [EsiContactLabel(1, "war targets")]
        )
        esi_character_contacts.setup_contacts(
            self.synced_character_2.character_id,
            [
                EsiContact(
                    1011,
                    EsiContact.ContactType.CHARACTER,
                    standing=-10.0,
                    label_ids=[1],
                ),
                EsiContact(1014, EsiContact.ContactType.CHARACTER, standing=10.0),
                EsiContact(2011, EsiContact.ContactType.CORPORATION, standing=5.0),
                EsiContact(3011, EsiContact.ContactType.ALLIANCE, standing=-10.0),
            ],
        )
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        result = self.synced_character_2.update()
        # then
        self.synced_character_2.refresh_from_db()
        self.assertTrue(result)
        expected = {
            EsiContact(
                1014,
                EsiContact.ContactType.CHARACTER,
                standing=-10.0,
                label_ids=[1],
            ),
            EsiContact(2011, EsiContact.ContactType.CORPORATION, standing=5.0),
            EsiContact(3011, EsiContact.ContactType.ALLIANCE, standing=-10.0),
            EsiContact(
                3013, EsiContact.ContactType.ALLIANCE, standing=-10.0, label_ids=[1]
            ),
        }
        self.assertSetEqual(
            set(esi_character_contacts.contacts(self.synced_character_2.character_id)),
            expected,
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    def test_should_record_if_character_has_wt_label(self, mock_esi):
        # given
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_labels(
            self.synced_character_2.character_id, [EsiContactLabel(1, "war targets")]
        )
        esi_character_contacts.setup_contacts(
            self.synced_character_2.character_id, self.CHARACTER_CONTACTS
        )
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        result = self.synced_character_2.update()
        # then
        self.synced_character_2.refresh_from_db()
        self.assertTrue(result)
        self.assertTrue(self.synced_character_2.has_war_targets_label)

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    def test_should_record_if_character_does_not_have_wt_label(self, mock_esi):
        # given
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(
            self.synced_character_2.character_id, self.CHARACTER_CONTACTS
        )
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        result = self.synced_character_2.update()
        # then
        self.synced_character_2.refresh_from_db()
        self.assertTrue(result)
        self.assertFalse(self.synced_character_2.has_war_targets_label)


class TestSyncCharacterErrorCases(LoadTestDataMixin, NoSocketsTestCase):
    def test_should_delete_when_insufficient_permission(self):
        # given
        user, _ = create_user_from_evecharacter(self.character_1.character_id)
        alt_ownership = add_character_to_user(
            user, character=self.character_2, scopes=SyncedCharacter.get_esi_scopes()
        )
        sync_manager = SyncManagerFactory(user=user, version_hash="new")
        synced_character = SyncedCharacterFactory(
            character_ownership=alt_ownership, manager=sync_manager
        )
        # when
        result = synced_character.update()
        # then
        self.assertFalse(result)
        self.assertFalse(
            SyncedCharacter.objects.filter(pk=synced_character.pk).exists()
        )

    def test_should_delete_when_no_valid_token_found(self):
        # given
        user, _ = create_user_from_evecharacter(
            self.character_1.character_id,
            permissions=["standingssync.add_syncedcharacter"],
        )
        alt_ownership = add_character_to_user(
            user, character=self.character_2
        )  # token has wrong scope and will therefore not be found
        sync_manager = SyncManagerFactory(user=user, version_hash="new")
        synced_character = SyncedCharacterFactory(
            character_ownership=alt_ownership, manager=sync_manager
        )
        # when
        result = synced_character.update()
        # then
        self.assertFalse(result)
        self.assertFalse(
            SyncedCharacter.objects.filter(pk=synced_character.pk).exists()
        )

    @patch(MODELS_PATH + ".Token")
    def test_should_delete_when_token_is_invalid(self, mock_Token):
        # given
        mock_Token.objects.filter.side_effect = TokenInvalidError()
        user, _ = create_user_from_evecharacter(
            self.character_1.character_id,
            permissions=["standingssync.add_syncedcharacter"],
        )
        alt_ownership = add_character_to_user(
            user, character=self.character_2, scopes=SyncedCharacter.get_esi_scopes()
        )
        sync_manager = SyncManagerFactory(user=user, version_hash="new")
        synced_character = SyncedCharacterFactory(
            character_ownership=alt_ownership, manager=sync_manager
        )
        # when
        result = synced_character.update()
        # then
        self.assertFalse(result)
        self.assertFalse(
            SyncedCharacter.objects.filter(pk=synced_character.pk).exists()
        )

    @patch(MODELS_PATH + ".Token")
    def test_should_delete_when_token_is_expired(self, mock_Token):
        # given
        mock_Token.objects.filter.side_effect = TokenExpiredError()
        user, _ = create_user_from_evecharacter(
            self.character_1.character_id,
            permissions=["standingssync.add_syncedcharacter"],
        )
        alt_ownership = add_character_to_user(
            user, character=self.character_2, scopes=SyncedCharacter.get_esi_scopes()
        )
        sync_manager = SyncManagerFactory(user=user, version_hash="new")
        synced_character = SyncedCharacterFactory(
            character_ownership=alt_ownership, manager=sync_manager
        )
        # when
        result = synced_character.update()
        # then
        self.assertFalse(result)
        self.assertFalse(
            SyncedCharacter.objects.filter(pk=synced_character.pk).exists()
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.1)
    def test_should_delete_when_character_has_no_standing(self):
        # given
        user, _ = create_user_from_evecharacter(
            self.character_1.character_id,
            permissions=["standingssync.add_syncedcharacter"],
        )
        alt_ownership = add_character_to_user(
            user, character=self.character_2, scopes=SyncedCharacter.get_esi_scopes()
        )
        sync_manager = SyncManagerFactory(user=user, version_hash="new")
        synced_character = SyncedCharacterFactory(
            character_ownership=alt_ownership, manager=sync_manager
        )
        EveContactFactory(
            manager=sync_manager,
            eve_entity=EveEntity.objects.get(id=synced_character.character_id),
            standing=-10,
        )
        # when
        result = synced_character.update()
        # then
        self.assertFalse(result)
        self.assertFalse(
            SyncedCharacter.objects.filter(pk=synced_character.pk).exists()
        )


class TestSyncCharacter2(NoSocketsTestCase):
    def test_should_report_sync_as_ok(self):
        # given
        my_dt = now()
        obj = SyncedCharacterFactory(last_update_at=my_dt - dt.timedelta(minutes=1))
        # when/then
        with patch(MODELS_PATH + ".STANDINGSSYNC_TIMEOUT_CHARACTER_SYNC", 60):
            self.assertTrue(obj.is_sync_fresh)

    def test_should_report_sync_as_not_ok(self):
        # given
        my_dt = now()
        obj = SyncedCharacterFactory(last_update_at=my_dt - dt.timedelta(minutes=61))
        # when/then
        with patch(MODELS_PATH + ".STANDINGSSYNC_TIMEOUT_CHARACTER_SYNC", 60):
            self.assertFalse(obj.is_sync_fresh)

    def test_should_not_sync_when_no_contacts(self):
        # given
        manager = SyncManagerFactory(version_hash="abc")
        character = SyncedCharacterFactory(manager=manager)
        # when
        result = character.update()
        # then
        self.assertTrue(result)

    def test_should_abort_sync_when_insufficient_permissions(self):
        # given
        manager = SyncManagerFactory(version_hash="abc")
        user = UserMainSyncerFactory(permissions__=[])
        character = SyncedCharacterFactory(manager=manager, user=user)
        # when
        result = character.update()
        # then
        self.assertFalse(result)


class TestEveWar(NoSocketsTestCase):
    def test_str(self):
        # given
        aggressor = EveEntityAllianceFactory(name="Alpha")
        defender = EveEntityAllianceFactory(name="Bravo")
        war = EveWarFactory(aggressor=aggressor, defender=defender)
        # when/then
        self.assertEqual(str(war), "Alpha vs. Bravo")
