import datetime as dt
from typing import Set
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

from standingssync.core.esi_contacts import EsiContact, EsiContactLabel

from ..models import EveContact, EveWar, SyncedCharacter, SyncManager
from .factories import (
    EveContactFactory,
    EveContactWarTargetFactory,
    EveEntityAllianceFactory,
    EveEntityCharacterFactory,
    EveWarFactory,
    SyncedCharacterFactory,
    SyncManagerFactory,
)
from .utils import ALLIANCE_CONTACTS, EsiCharacterContactsStub, LoadTestDataMixin

ESI_CONTACTS_PATH = "standingssync.core.esi_contacts"
ESI_API_PATH = "standingssync.core.esi_api"
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
        self.assertEqual(self.sync_manager.effective_standing_with_character(c1), -10)

    def test_char_with_corporation_standing(self):
        c2 = EveCharacter(
            character_id=1002,
            character_name="Char 2",
            corporation_id=2001,
            corporation_name="Corporation 1",
            corporation_ticker="C1",
        )
        self.assertEqual(self.sync_manager.effective_standing_with_character(c2), 10)

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
        self.assertEqual(self.sync_manager.effective_standing_with_character(c3), 5)

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
        self.assertEqual(self.sync_manager.effective_standing_with_character(c4), 0.0)

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
        self.assertEqual(self.sync_manager.effective_standing_with_character(c4), 0.0)

    def test_char_without_standing_and_without_alliance_2(self):
        c4 = EveCharacter(
            character_id=1003,
            character_name="Char 3",
            corporation_id=2003,
            corporation_name="Corporation 3",
            corporation_ticker="C2",
        )
        self.assertEqual(self.sync_manager.effective_standing_with_character(c4), 0.0)


@patch(ESI_API_PATH + ".esi")
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
            sync_manager.run_sync()
        # then
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
            sync_manager.run_sync()
        # then
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
            sync_manager.run_sync()

    def test_should_abort_when_insufficient_permission(self):
        # given
        user, _ = create_user_from_evecharacter(self.character_1.character_id)
        add_character_to_user(
            user, self.character_1, scopes=SyncManager.get_esi_scopes()
        )
        sync_manager = SyncManagerFactory(user=user)
        # when/then
        with self.assertRaises(RuntimeError):
            sync_manager.run_sync()

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
            sync_manager.run_sync()


@patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
@patch(ESI_API_PATH + ".esi")
class TestSyncManager2(NoSocketsTestCase):
    @staticmethod
    def _war_target_contact_ids() -> Set[int]:
        return set(
            EveContact.objects.filter(is_war_target=True).values_list(
                "eve_entity_id", flat=True
            )
        )

    def test_should_report_sync_as_ok(self, dummy):
        # given
        my_dt = now()
        sync_manager = SyncManagerFactory(last_sync_at=my_dt - dt.timedelta(minutes=1))
        # when/then
        with patch(MODELS_PATH + ".STANDINGSSYNC_SYNC_TIMEOUT", 60):
            self.assertTrue(sync_manager.is_sync_fresh)

    def test_should_report_sync_as_not_ok(self, dummy):
        # given
        my_dt = now()
        sync_manager = SyncManagerFactory(last_sync_at=my_dt - dt.timedelta(minutes=61))
        # when/then
        with patch(MODELS_PATH + ".STANDINGSSYNC_SYNC_TIMEOUT", 60):
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
        sync_manager.run_sync()
        # then
        self.assertSetEqual(self._war_target_contact_ids(), {war.defender.id})

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
        sync_manager.run_sync()
        # then
        self.assertSetEqual(self._war_target_contact_ids(), {war.defender.id, ally.id})

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
        sync_manager.run_sync()
        # then
        self.assertSetEqual(self._war_target_contact_ids(), {war.aggressor.id})

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
        sync_manager.run_sync()
        # then
        self.assertSetEqual(self._war_target_contact_ids(), {war.aggressor.id})

    def test_should_not_add_war_target_contact_from_unrelated_war(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub([])
        )
        sync_manager = SyncManagerFactory()
        EveWarFactory()
        EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id)
        # when
        sync_manager.run_sync()
        # then
        self.assertSetEqual(self._war_target_contact_ids(), set())

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
        sync_manager.run_sync()
        # then
        self.assertSetEqual(self._war_target_contact_ids(), set())

    def test_do_not_store_contacts_when_unchanged(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub(ALLIANCE_CONTACTS)
        )
        sync_manager = SyncManagerFactory(
            version_hash="33f9b95322860e4d6d2914117bff4929"
        )
        # when
        sync_manager.run_sync()
        # then
        self.assertEqual(sync_manager.contacts.count(), 0)


@patch(ESI_CONTACTS_PATH + ".STANDINGSSYNC_WAR_TARGETS_LABEL_NAME", "WAR TARGETS")
@patch(ESI_API_PATH + ".esi")
class TestSyncCharacterEsi(NoSocketsTestCase):
    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    def test_should_replace_contacts_no_wt(self, mock_esi):
        # given
        synced_character = SyncedCharacterFactory()
        sync_manager = synced_character.manager
        EveContactFactory(
            manager=sync_manager,
            eve_entity=EveEntityCharacterFactory(id=synced_character.character_id),
            standing=10,
        )
        alliance_contact_1 = EveContactFactory(manager=sync_manager)
        alliance_contact_2 = EveContactFactory(manager=sync_manager, standing=10)
        character_contact_1 = EsiContact.from_eve_entity(
            EveEntityCharacterFactory(), -5
        )
        EveContactFactory(
            manager=sync_manager, standing=-10, is_war_target=True
        )  # alliance_wt_contact
        character_contact_2 = EsiContact.from_eve_contact(alliance_contact_2).clone(
            standing=-5
        )
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(
            synced_character.character_id, [character_contact_1, character_contact_2]
        )
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        result = synced_character.run_sync()
        # then
        self.assertTrue(result)
        synced_character.refresh_from_db()
        self.assertIsNotNone(synced_character.last_sync_at)
        expected = {
            EsiContact.from_eve_contact(alliance_contact_1),
            EsiContact.from_eve_contact(alliance_contact_2),
        }
        self.assertSetEqual(
            esi_character_contacts.contacts(synced_character.character_id), expected
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0)
    def test_should_replace_contacts_no_wt_no_standing(self, mock_esi):
        # given
        synced_character = SyncedCharacterFactory()
        sync_manager = synced_character.manager
        EveContactFactory(
            manager=sync_manager,
            eve_entity=EveEntityCharacterFactory(id=synced_character.character_id),
            standing=0,
        )
        alliance_contact_1 = EveContactFactory(manager=sync_manager)
        alliance_contact_2 = EveContactFactory(manager=sync_manager, standing=10)
        character_contact_1 = EsiContact.from_eve_entity(
            EveEntityCharacterFactory(), -5
        )
        EveContactFactory(
            manager=sync_manager, standing=-10, is_war_target=True
        )  # alliance_wt_contact
        character_contact_2 = EsiContact.from_eve_contact(alliance_contact_2).clone(
            standing=-5
        )
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(
            synced_character.character_id, [character_contact_1, character_contact_2]
        )
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        result = synced_character.run_sync()
        # then
        self.assertTrue(result)
        synced_character.refresh_from_db()
        self.assertIsNotNone(synced_character.last_sync_at)
        expected = {
            EsiContact.from_eve_contact(alliance_contact_1),
            EsiContact.from_eve_contact(alliance_contact_2),
        }
        self.assertSetEqual(
            esi_character_contacts.contacts(synced_character.character_id), expected
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    def test_should_replace_contacts_incl_wt(self, mock_esi):
        # given
        synced_character = SyncedCharacterFactory()
        sync_manager = synced_character.manager
        EveContactFactory(
            manager=sync_manager,
            eve_entity=EveEntityCharacterFactory(id=synced_character.character_id),
            standing=10,
        )
        alliance_contact_1 = EveContactFactory(manager=sync_manager)
        alliance_contact_2 = EveContactFactory(manager=sync_manager, standing=10)
        alliance_wt_contact = EveContactFactory(
            manager=sync_manager, standing=-10, is_war_target=True
        )
        character_contact_1 = EsiContact.from_eve_entity(
            EveEntityCharacterFactory(), -5
        )
        character_contact_2 = EsiContact.from_eve_contact(alliance_contact_2).clone(
            standing=-5
        )
        wt_label = EsiContactLabel(1, "WAR TARGETS")
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(
            synced_character.character_id, [character_contact_1, character_contact_2]
        )
        esi_character_contacts.setup_labels(synced_character.character_id, [wt_label])
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        result = synced_character.run_sync()
        # then
        self.assertTrue(result)
        synced_character.refresh_from_db()
        self.assertIsNotNone(synced_character.last_sync_at)
        expected = {
            EsiContact.from_eve_contact(alliance_contact_1),
            EsiContact.from_eve_contact(alliance_contact_2),
            EsiContact.from_eve_contact(alliance_wt_contact, label_ids=[wt_label.id]),
        }
        self.assertSetEqual(
            esi_character_contacts.contacts(synced_character.character_id), expected
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    def test_should_not_update_anything(self, mock_esi):
        # given
        synced_character = SyncedCharacterFactory()
        sync_manager = synced_character.manager
        EveContactFactory(
            manager=sync_manager,
            eve_entity=EveEntityCharacterFactory(id=synced_character.character_id),
            standing=10,
        )
        EveContactFactory(manager=sync_manager)  # alliance_contact_1
        alliance_contact_2 = EveContactFactory(manager=sync_manager, standing=10)
        character_contact_1 = EsiContact.from_eve_entity(
            EveEntityCharacterFactory(), -5
        )
        EveContactFactory(
            manager=sync_manager, standing=-10, is_war_target=True
        )  # alliance_wt_contact
        character_contact_2 = EsiContact.from_eve_contact(alliance_contact_2).clone(
            standing=-5
        )
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(
            synced_character.character_id, [character_contact_1, character_contact_2]
        )
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        result = synced_character.run_sync()
        # then
        self.assertTrue(result)
        synced_character.refresh_from_db()
        self.assertIsNotNone(synced_character.last_sync_at)
        expected = {character_contact_1, character_contact_2}
        self.assertSetEqual(
            esi_character_contacts.contacts(synced_character.character_id), expected
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    def test_should_sync_war_targets_but_not_alliance_contacts(self, mock_esi):
        # given
        synced_character = SyncedCharacterFactory()
        sync_manager = synced_character.manager
        wt_label = EsiContactLabel(1, "WAR TARGETS")
        EveContactFactory(manager=sync_manager)  # should not sync this alliance contact
        EveContactFactory(
            manager=sync_manager,
            eve_entity=EveEntityCharacterFactory(id=synced_character.character_id),
            standing=10,
        )  # sync char must have standing with alliance
        alliance_wt_contact_1 = EveContactFactory(
            manager=sync_manager, standing=-10, is_war_target=True
        )  # new war target
        alliance_wt_contact_2 = EveContactFactory(
            manager=sync_manager, standing=-10, is_war_target=True
        )  # new war target
        character_contact_1 = EsiContact.from_eve_entity(
            EveEntityCharacterFactory(), -5
        )  # character contact must be kept in place
        character_old_wt_contact = EsiContact.from_eve_entity(
            EveEntityCharacterFactory(), -10, [wt_label.id]
        )  # should remove this old WT contact
        character_contact_2 = EsiContact.from_eve_contact(alliance_wt_contact_2).clone(
            standing=10
        )  # should replace this existing character contact with a WT
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_labels(synced_character.character_id, [wt_label])
        esi_character_contacts.setup_contacts(
            synced_character.character_id,
            [character_contact_1, character_old_wt_contact, character_contact_2],
        )
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        result = synced_character.run_sync()
        # then
        self.assertTrue(result)
        synced_character.refresh_from_db()
        self.assertIsNotNone(synced_character.last_sync_at)
        expected = {
            character_contact_1,
            EsiContact.from_eve_contact(alliance_wt_contact_1, label_ids=[wt_label.id]),
            EsiContact.from_eve_contact(alliance_wt_contact_2, label_ids=[wt_label.id]),
        }
        self.assertSetEqual(
            esi_character_contacts.contacts(synced_character.character_id), expected
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    def test_should_add_wt_label_info(self, mock_esi):
        # given
        synced_character = SyncedCharacterFactory()
        sync_manager = synced_character.manager
        EveContactFactory(
            manager=sync_manager,
            eve_entity=EveEntityCharacterFactory(id=synced_character.character_id),
            standing=10,
        )
        EveContactFactory(manager=sync_manager)  # alliance_contact
        wt_label = EsiContactLabel(1, "WAR TARGETS")
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(synced_character.character_id, [])
        esi_character_contacts.setup_labels(synced_character.character_id, [wt_label])
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        synced_character.run_sync()
        # then
        synced_character.refresh_from_db()
        self.assertTrue(synced_character.has_war_targets_label)

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    def test_should_remove_wt_label_info(self, mock_esi):
        # given
        synced_character = SyncedCharacterFactory(has_war_targets_label=True)
        sync_manager = synced_character.manager
        EveContactFactory(
            manager=sync_manager,
            eve_entity=EveEntityCharacterFactory(id=synced_character.character_id),
            standing=10,
        )
        EveContactFactory(manager=sync_manager)  # alliance_contact
        other_label = EsiContactLabel(1, "ABC")
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(synced_character.character_id, [])
        esi_character_contacts.setup_labels(
            synced_character.character_id, [other_label]
        )
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        synced_character.run_sync()
        # then
        synced_character.refresh_from_db()
        self.assertFalse(synced_character.has_war_targets_label)

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    def test_should_not_sync_when_no_contacts(self, mock_esi):
        # given
        synced_character = SyncedCharacterFactory()
        sync_manager = synced_character.manager
        EveContactFactory(
            manager=sync_manager,
            eve_entity=EveEntityCharacterFactory(id=synced_character.character_id),
            standing=10,
        )
        character_contact_1 = EsiContact.from_eve_entity(
            EveEntityCharacterFactory(), -5
        )
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(
            synced_character.character_id, [character_contact_1]
        )
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        result = synced_character.run_sync()
        # then
        self.assertIsNone(result)


class TestSyncCharacterErrorCases(LoadTestDataMixin, NoSocketsTestCase):
    def test_should_delete_when_insufficient_permission(self):
        # given
        user, _ = create_user_from_evecharacter(self.character_1.character_id)
        alt_ownership = add_character_to_user(
            user, character=self.character_2, scopes=SyncedCharacter.get_esi_scopes()
        )
        sync_manager = SyncManagerFactory(user=user, version_hash="new")
        sync_character = SyncedCharacterFactory(
            character_ownership=alt_ownership, manager=sync_manager
        )
        # when
        result = sync_character.run_sync()
        # then
        self.assertFalse(result)
        self.assertFalse(SyncedCharacter.objects.filter(pk=sync_character.pk).exists())

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
        sync_character = SyncedCharacterFactory(
            character_ownership=alt_ownership, manager=sync_manager
        )
        # when
        result = sync_character.run_sync()
        # then
        self.assertFalse(result)
        self.assertFalse(SyncedCharacter.objects.filter(pk=sync_character.pk).exists())

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
        sync_character = SyncedCharacterFactory(
            character_ownership=alt_ownership, manager=sync_manager
        )
        # when
        result = sync_character.run_sync()
        # then
        self.assertFalse(result)
        self.assertFalse(SyncedCharacter.objects.filter(pk=sync_character.pk).exists())

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
        sync_character = SyncedCharacterFactory(
            character_ownership=alt_ownership, manager=sync_manager
        )
        # when
        result = sync_character.run_sync()
        # then
        self.assertFalse(result)
        self.assertFalse(SyncedCharacter.objects.filter(pk=sync_character.pk).exists())

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
        sync_character = SyncedCharacterFactory(
            character_ownership=alt_ownership, manager=sync_manager
        )
        EveContactFactory(
            manager=sync_manager,
            eve_entity=EveEntity.objects.get(id=sync_character.character_id),
            standing=-10,
        )
        # when
        result = sync_character.run_sync()
        # then
        self.assertFalse(result)
        self.assertFalse(SyncedCharacter.objects.filter(pk=sync_character.pk).exists())


class TestSyncCharacter2(NoSocketsTestCase):
    def test_should_report_sync_as_ok(self):
        # given
        my_dt = now()
        obj = SyncedCharacterFactory(last_sync_at=my_dt - dt.timedelta(minutes=1))
        # when/then
        with patch(MODELS_PATH + ".STANDINGSSYNC_SYNC_TIMEOUT", 60):
            self.assertTrue(obj.is_sync_fresh)

    def test_should_report_sync_as_not_ok(self):
        # given
        my_dt = now()
        obj = SyncedCharacterFactory(last_sync_at=my_dt - dt.timedelta(minutes=61))
        # when/then
        with patch(MODELS_PATH + ".STANDINGSSYNC_SYNC_TIMEOUT", 60):
            self.assertFalse(obj.is_sync_fresh)


class TestEveWar(NoSocketsTestCase):
    def test_str(self):
        # given
        aggressor = EveEntityAllianceFactory(name="Alpha")
        defender = EveEntityAllianceFactory(name="Bravo")
        war = EveWarFactory(aggressor=aggressor, defender=defender)
        # when/then
        self.assertEqual(str(war), "Alpha vs. Bravo")
