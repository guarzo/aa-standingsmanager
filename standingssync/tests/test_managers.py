import datetime as dt
from unittest.mock import patch

from django.utils.timezone import now
from eveuniverse.models import EveEntity

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveAllianceInfo
from app_utils.esi_testing import BravadoOperationStub
from app_utils.testdata_factories import UserFactory
from app_utils.testing import NoSocketsTestCase, create_user_from_evecharacter

from ..models import EveWar, SyncManager
from .factories import (
    EveContactFactory,
    EveEntityAllianceFactory,
    EveWarFactory,
    SyncedCharacterFactory,
    SyncManagerFactory,
    UserMainSyncerFactory,
)
from .utils import ALLIANCE_CONTACTS, LoadTestDataMixin

ESI_WARS_PATH = "standingssync.core.esi_api"
MANAGERS_PATH = "standingssync.managers"
MODELS_PATH = "standingssync.models"


class TestEveContactManager(LoadTestDataMixin, NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # 1 user with 1 alt character
        cls.user_1, _ = create_user_from_evecharacter(cls.character_1.character_id)
        cls.alt_ownership = CharacterOwnership.objects.create(
            character=cls.character_2, owner_hash="x2", user=cls.user_1
        )

        # sync manager with contacts
        cls.sync_manager = SyncManagerFactory(user=cls.user_1, version_hash="new")
        for contact in ALLIANCE_CONTACTS:
            EveContactFactory(
                manager=cls.sync_manager,
                eve_entity=EveEntity.objects.get(id=contact["contact_id"]),
                standing=contact["standing"],
            )

        # sync char
        cls.synced_character = SyncedCharacterFactory(
            character_ownership=cls.alt_ownership, manager=cls.sync_manager
        )

    def test_grouped_by_standing(self):
        c = {int(x.eve_entity_id): x for x in self.sync_manager.contacts.all()}
        expected = {
            -10.0: {c[1005], c[1012], c[3011], c[2011]},
            -5.0: {c[1013], c[3012], c[2012]},
            0.0: {c[1014], c[3013], c[2014]},
            5.0: {c[1015], c[3014], c[2013]},
            10.0: {c[1002], c[1004], c[1016], c[3015], c[2015]},
        }
        result = self.sync_manager.contacts.grouped_by_standing()
        self.maxDiff = None
        self.assertDictEqual(result, expected)
        self.assertListEqual(list(result.keys()), list(expected.keys()))


class TestEveWarManager(LoadTestDataMixin, NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # given
        cls.war_declared = now() - dt.timedelta(days=3)
        cls.war_started = now() - dt.timedelta(days=2)
        EveWarFactory(
            id=8,
            aggressor=EveEntity.objects.get(id=3011),
            defender=EveEntity.objects.get(id=3001),
            declared=cls.war_declared,
            started=cls.war_started,
            allies=[EveEntity.objects.get(id=3012)],
        )
        EveEntityAllianceFactory(id=3002)
        EveEntityAllianceFactory(id=3003)

    def test_should_return_defender_and_allies_for_aggressor(self):
        # when
        result = EveWar.objects.war_targets(3011)
        # then
        self.assertSetEqual({obj.id for obj in result}, {3001, 3012})

    def test_should_return_aggressor_for_defender(self):
        # when
        result = EveWar.objects.war_targets(3001)
        # then
        self.assertSetEqual({obj.id for obj in result}, {3011})

    def test_should_return_aggressor_for_ally(self):
        # when
        result = EveWar.objects.war_targets(3012)
        # then
        self.assertSetEqual({obj.id for obj in result}, {3011})

    def test_should_return_finished_wars(self):
        # given
        EveWarFactory(
            id=2,  # finished in the past
            aggressor=EveEntity.objects.get(id=3011),
            defender=EveEntity.objects.get(id=3001),
            declared=now() - dt.timedelta(days=5),
            started=now() - dt.timedelta(days=4),
            finished=now() - dt.timedelta(days=2),
        )
        EveWarFactory(
            id=3,  # about to finish
            aggressor=EveEntity.objects.get(id=3011),
            defender=EveEntity.objects.get(id=3001),
            declared=now() - dt.timedelta(days=5),
            started=now() - dt.timedelta(days=4),
            finished=now() + dt.timedelta(days=1),
        )
        EveWarFactory(
            id=4,  # not yet started
            aggressor=EveEntity.objects.get(id=3011),
            defender=EveEntity.objects.get(id=3001),
            declared=now() - dt.timedelta(days=1),
            started=now() + dt.timedelta(days=1),
        )
        # when
        result = EveWar.objects.finished_wars()
        # then
        self.assertSetEqual({obj.id for obj in result}, {2})

    @patch(ESI_WARS_PATH + ".esi")
    def test_should_create_full_war_object_from_esi_1(self, mock_esi):
        # given
        declared = now() - dt.timedelta(days=5)
        started = now() - dt.timedelta(days=4)
        finished = now() + dt.timedelta(days=1)
        retracted = now()
        esi_data = {
            "aggressor": {
                "alliance_id": 3001,
                "isk_destroyed": 0,
                "ships_killed": 0,
            },
            "allies": [{"alliance_id": 3003}, {"corporation_id": 2003}],
            "declared": declared,
            "defender": {
                "alliance_id": 3002,
                "isk_destroyed": 0,
                "ships_killed": 0,
            },
            "finished": finished,
            "id": 1,
            "mutual": False,
            "open_for_allies": True,
            "retracted": retracted,
            "started": started,
        }
        mock_esi.client.Wars.get_wars_war_id.return_value = BravadoOperationStub(
            esi_data
        )
        # when
        war, created = EveWar.objects.update_or_create_from_esi(id=1)
        # then
        self.assertTrue(created)
        self.assertEqual(war.aggressor.id, 3001)
        self.assertEqual(set(war.allies.values_list("id", flat=True)), {2003, 3003})
        self.assertEqual(war.declared, declared)
        self.assertEqual(war.defender.id, 3002)
        self.assertEqual(war.finished, finished)
        self.assertFalse(war.is_mutual)
        self.assertTrue(war.is_open_for_allies)
        self.assertEqual(war.retracted, retracted)
        self.assertEqual(war.started, started)

    @patch(ESI_WARS_PATH + ".esi")
    def test_should_create_full_war_object_from_esi_2(self, mock_esi):
        # given
        declared = now() - dt.timedelta(days=5)
        started = now() - dt.timedelta(days=4)
        esi_data = {
            "aggressor": {
                "alliance_id": 3001,
                "isk_destroyed": 0,
                "ships_killed": 0,
            },
            "allies": None,
            "declared": declared,
            "defender": {
                "alliance_id": 3002,
                "isk_destroyed": 0,
                "ships_killed": 0,
            },
            "finished": None,
            "id": 1,
            "mutual": False,
            "open_for_allies": True,
            "retracted": None,
            "started": started,
        }
        mock_esi.client.Wars.get_wars_war_id.return_value = BravadoOperationStub(
            esi_data
        )
        # when
        war, created = EveWar.objects.update_or_create_from_esi(id=1)
        # then
        self.assertTrue(created)
        self.assertEqual(war.aggressor.id, 3001)
        self.assertEqual(war.allies.count(), 0)
        self.assertEqual(war.declared, declared)
        self.assertEqual(war.defender.id, 3002)
        self.assertIsNone(war.finished)
        self.assertFalse(war.is_mutual)
        self.assertTrue(war.is_open_for_allies)
        self.assertIsNone(war.retracted)
        self.assertEqual(war.started, started)

    # @patch(ESI_WARS_PATH + ".esi")
    # def test_should_not_create_object_from_esi_for_finished_war(self, mock_esi):
    #     # given
    #     declared = now() - dt.timedelta(days=5)
    #     started = now() - dt.timedelta(days=4)
    #     finished = now() - dt.timedelta(days=1)
    #     esi_data = {
    #         "aggressor": {
    #             "alliance_id": 3001,
    #             "isk_destroyed": 0,
    #             "ships_killed": 0,
    #         },
    #         "allies": [{"alliance_id": 3003}, {"corporation_id": 2003}],
    #         "declared": declared,
    #         "defender": {
    #             "alliance_id": 3002,
    #             "isk_destroyed": 0,
    #             "ships_killed": 0,
    #         },
    #         "finished": finished,
    #         "id": 1,
    #         "mutual": False,
    #         "open_for_allies": True,
    #         "retracted": None,
    #         "started": started,
    #     }
    #     mock_esi.client.Wars.get_wars_war_id.return_value = BravadoOperationStub(
    #         esi_data
    #     )
    #     # when
    #     EveWar.objects.update_or_create_from_esi(id=1)
    #     # then
    #     self.assertFalse(EveWar.objects.filter(id=1).exists())

    @patch(ESI_WARS_PATH + ".esi")
    def test_should_update_existing_war_from_esi(self, mock_esi):
        # given
        finished = now() + dt.timedelta(days=1)
        retracted = now()
        esi_data = {
            "aggressor": {
                "alliance_id": 3011,
                "isk_destroyed": 0,
                "ships_killed": 0,
            },
            "allies": [{"alliance_id": 3003}, {"corporation_id": 2003}],
            "declared": self.war_declared,
            "defender": {
                "alliance_id": 3001,
                "isk_destroyed": 0,
                "ships_killed": 0,
            },
            "finished": finished,
            "id": 8,
            "mutual": True,
            "open_for_allies": True,
            "retracted": retracted,
            "started": self.war_started,
        }
        mock_esi.client.Wars.get_wars_war_id.return_value = BravadoOperationStub(
            esi_data
        )
        # when
        war, created = EveWar.objects.update_or_create_from_esi(id=8)
        # then
        self.assertFalse(created)
        self.assertEqual(war.aggressor.id, 3011)
        self.assertEqual(set(war.allies.values_list("id", flat=True)), {2003, 3003})
        self.assertEqual(war.declared, self.war_declared)
        self.assertEqual(war.defender.id, 3001)
        self.assertEqual(war.finished, finished)
        self.assertTrue(war.is_mutual)
        self.assertTrue(war.is_open_for_allies)
        self.assertEqual(war.retracted, retracted)
        self.assertEqual(war.started, self.war_started)


@patch(MANAGERS_PATH + ".esi_api.fetch_war_ids")
class TestEveWarManager2(NoSocketsTestCase):
    def test_should_return_unfinished_war_ids(self, mock_fetch_war_ids_from_esi):
        # given
        mock_fetch_war_ids_from_esi.return_value = {1, 2, 42}
        EveWarFactory(id=42, finished=now() - dt.timedelta(days=1))
        # when
        result = EveWar.objects.fetch_active_war_ids_esi()
        # then
        self.assertSetEqual(result, {1, 2})


class TestEveWarManagerActiveWars(NoSocketsTestCase):
    def test_should_return_started_war_as_defender(self):
        # given
        sync_manager = SyncManagerFactory()
        war = EveWarFactory(
            defender=EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id),
            declared=now() - dt.timedelta(days=2),
        )
        # when
        result = EveWar.objects.active_wars()
        # then
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first(), war)

    def test_should_return_started_war_as_attacker(self):
        # given
        sync_manager = SyncManagerFactory()
        war = EveWarFactory(
            aggressor=EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id),
            declared=now() - dt.timedelta(days=2),
        )
        # when
        result = EveWar.objects.active_wars()
        # then
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first(), war)

    def test_should_return_started_war_as_ally(self):
        # given
        sync_manager = SyncManagerFactory()
        war = EveWarFactory(
            allies=[EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id)],
            declared=now() - dt.timedelta(days=2),
        )
        # when
        result = EveWar.objects.active_wars()
        # then
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first(), war)

    def test_should_return_war_about_to_finish(self):
        # given
        sync_manager = SyncManagerFactory()
        war = EveWarFactory(
            defender=EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id),
            declared=now() - dt.timedelta(days=2),
            finished=now() + dt.timedelta(days=1),
        )
        # when
        result = EveWar.objects.active_wars()
        # then
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first(), war)

    def test_should_not_return_finished_war(self):
        # given
        sync_manager = SyncManagerFactory()
        EveWarFactory(
            defender=EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id),
            declared=now() - dt.timedelta(days=2),
            finished=now() - dt.timedelta(days=1),
        )
        # when
        result = EveWar.objects.active_wars()
        # then
        self.assertEqual(result.count(), 0)

    def test_should_not_return_war_not_yet_started(self):
        # given
        sync_manager = SyncManagerFactory()
        EveWarFactory(
            defender=EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id),
            declared=now() - dt.timedelta(days=1),
            started=now() + dt.timedelta(hours=4),
        )
        # when
        result = EveWar.objects.active_wars()
        # then
        self.assertEqual(result.count(), 0)


class TestSyncManagerManager(NoSocketsTestCase):
    def test_should_return_matching_sync_manager(self):
        # given
        user = UserMainSyncerFactory()
        alliance = EveAllianceInfo.objects.get(
            alliance_id=user.profile.main_character.alliance_id
        )
        sync_manager = SyncManagerFactory(alliance=alliance)
        # when
        result = SyncManager.objects.fetch_for_user(user)
        # then
        self.assertEqual(result, sync_manager)

    def test_should_return_none_when_no_match(self):
        # given
        user = UserMainSyncerFactory()
        SyncManagerFactory()
        # when
        result = SyncManager.objects.fetch_for_user(user)
        # then
        self.assertIsNone(result)

    def test_should_return_none_when_user_has_no_main(self):
        # given
        user = UserFactory()
        # when
        result = SyncManager.objects.fetch_for_user(user)
        # then
        self.assertIsNone(result)
