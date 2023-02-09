from dataclasses import dataclass
from unittest.mock import patch

from app_utils.esi_testing import BravadoOperationStub, EsiClientStub, EsiEndpoint
from app_utils.testing import NoSocketsTestCase

from standingssync.core import esi_api
from standingssync.core.esi_contacts import EsiContact

from ..factories import EsiContactLabelFactory, EveEntityCharacterFactory
from ..utils import EsiCharacterContactsStub

MODULE_PATH = "standingssync.core.esi_api"


@dataclass
class MockToken:
    character_id: int
    character_name: str

    def valid_access_token(self):
        return "DUMMY-TOKEN"


@patch(MODULE_PATH + ".esi")
class TestEsiContactsApi(NoSocketsTestCase):
    def test_should_return_alliance_contacts(self, mock_esi):
        # given
        endpoints = [
            EsiEndpoint(
                "Contacts",
                "get_alliances_alliance_id_contacts",
                "alliance_id",
                needs_token=True,
                data={
                    "3001": [
                        {
                            "contact_id": 1001,
                            "contact_type": "character",
                            "standing": 9.9,
                        }
                    ]
                },
            ),
        ]
        mock_esi.client = EsiClientStub.create_from_endpoints(endpoints)
        mock_token = MockToken(1001, "Bruce Wayne")
        # when
        result = esi_api.fetch_alliance_contacts(alliance_id=3001, token=mock_token)
        # then
        expected = {
            EsiContact(1001, EsiContact.ContactType.CHARACTER, 9.9),
            EsiContact(3001, EsiContact.ContactType.ALLIANCE, 10),
        }
        self.assertSetEqual(expected, result)

    def test_should_return_character_contacts(self, mock_esi):
        # given
        endpoints = [
            EsiEndpoint(
                "Contacts",
                "get_characters_character_id_contacts",
                "character_id",
                needs_token=True,
                data={
                    "1001": [
                        {
                            "contact_id": 2001,
                            "contact_type": "corporation",
                            "standing": 9.9,
                        }
                    ]
                },
            ),
        ]
        mock_esi.client = EsiClientStub.create_from_endpoints(endpoints)
        mock_token = MockToken(1001, "Bruce Wayne")
        # when
        result = esi_api.fetch_character_contacts(token=mock_token)
        # then
        expected = {EsiContact(2001, EsiContact.ContactType.CORPORATION, 9.9)}
        self.assertSetEqual(expected, result)

    def test_should_return_contact_labels(self, mock_esi):
        # given
        label_1 = EsiContactLabelFactory()
        label_2 = EsiContactLabelFactory()
        endpoints = [
            EsiEndpoint(
                "Contacts",
                "get_characters_character_id_contacts_labels",
                "character_id",
                needs_token=True,
                data={"1001": [label_1.to_esi_dict(), label_2.to_esi_dict()]},
            ),
        ]
        mock_esi.client = EsiClientStub.create_from_endpoints(endpoints)
        mock_token = MockToken(1001, "Bruce Wayne")
        # when
        result = esi_api.fetch_character_contact_labels(token=mock_token)
        # then
        expected = {label_1, label_2}
        self.assertSetEqual(result, expected)

    def test_should_delete_contacts(self, mock_esi):
        # given
        mock_token = MockToken(1001, "Bruce Wayne")
        contact_1002 = EsiContact(1002, EsiContact.ContactType.CHARACTER, 5)
        contact_1003 = EsiContact(1003, EsiContact.ContactType.CHARACTER, 5)
        esi_stub = EsiCharacterContactsStub()
        esi_stub.setup_contacts(1001, [contact_1002, contact_1003])
        esi_stub.setup_esi_mock(mock_esi)
        # when
        esi_api.delete_character_contacts(mock_token, [contact_1003])
        # then
        self.assertSetEqual(set(esi_stub.contacts(1001)), {contact_1002})

    def test_should_add_contact(self, mock_esi):
        # given
        mock_token = MockToken(1001, "Bruce Wayne")
        contact = EsiContact.from_eve_entity(EveEntityCharacterFactory(), standing=5.0)
        esi_stub = EsiCharacterContactsStub()
        esi_stub.setup_contacts(1001, [])
        esi_stub.setup_esi_mock(mock_esi)
        # when
        result = esi_api.add_character_contacts(
            mock_token, {contact.standing: [contact.contact_id]}
        )
        # then
        self.assertTrue(result)
        self.assertSetEqual(set(esi_stub.contacts(1001)), {contact})

    def test_should_update_contact(self, mock_esi):
        # given
        mock_token = MockToken(1001, "Bruce Wayne")
        contact = EsiContact.from_eve_entity(EveEntityCharacterFactory(), standing=-5)
        old_esi_contact = EsiContact(
            contact_id=contact.contact_id,
            contact_type=contact.contact_type,
            standing=10,
        )
        esi_stub = EsiCharacterContactsStub()
        esi_stub.setup_contacts(1001, [old_esi_contact])
        esi_stub.setup_esi_mock(mock_esi)
        # when
        result = esi_api.update_character_contacts(
            mock_token, {contact.standing: [contact.contact_id]}
        )
        # then
        self.assertTrue(result)
        self.assertSetEqual(set(esi_stub.contacts(1001)), {contact})


class TestEsiWarsApi(NoSocketsTestCase):
    @patch(MODULE_PATH + ".STANDINGSSYNC_MINIMUM_UNFINISHED_WAR_ID", 4)
    @patch(MODULE_PATH + ".STANDINGSSYNC_SPECIAL_WAR_IDS", [1, 2])
    @patch(MODULE_PATH + ".esi")
    def test_should_fetch_war_ids_with_paging(self, mock_esi):
        def esi_get_wars(max_war_id=None):
            if max_war_id:
                war_ids = [war_id for war_id in esi_war_ids if war_id < max_war_id]
            else:
                war_ids = esi_war_ids
            return BravadoOperationStub(sorted(war_ids, reverse=True)[:page_size])

        # given
        esi_war_ids = [1, 2, 3, 4, 5, 6, 7, 8]
        page_size = 3
        mock_esi.client.Wars.get_wars.side_effect = esi_get_wars
        # when
        with patch(MODULE_PATH + ".FETCH_WARS_MAX_ITEMS", 3):
            result = esi_api.fetch_war_ids()
        # then
        self.assertSetEqual(result, {1, 2, 4, 5, 6, 7, 8})
