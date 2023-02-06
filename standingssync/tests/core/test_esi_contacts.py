from dataclasses import dataclass
from unittest.mock import patch

from app_utils.esi_testing import EsiClientStub, EsiEndpoint
from app_utils.testing import NoSocketsTestCase

from standingssync.core import esi_contacts

MODULE_PATH = "standingssync.core.esi_contacts"


@dataclass
class MockToken:
    character_id: int
    character_name: str

    def valid_access_token(self):
        return "DUMMY-TOKEN"


@patch(MODULE_PATH + ".esi")
class TestEsiContacts(NoSocketsTestCase):
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
        result = esi_contacts.fetch_alliance_contacts(
            alliance_id=3001, token=mock_token
        )
        # then
        expected = {
            1001: {
                "contact_id": 1001,
                "contact_type": "character",
                "standing": 9.9,
            },
            3001: {
                "contact_id": 3001,
                "contact_type": "alliance",
                "standing": 10,
            },
        }
        self.assertDictEqual(expected, result)

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
        result = esi_contacts.fetch_character_contacts(token=mock_token)
        # then
        expected = {
            2001: {
                "contact_id": 2001,
                "contact_type": "corporation",
                "standing": 9.9,
            },
        }
        self.assertDictEqual(expected, result)

    def test_should_return_wt_label_id(self, mock_esi):
        # given
        endpoints = [
            EsiEndpoint(
                "Contacts",
                "get_characters_character_id_contacts_labels",
                "character_id",
                needs_token=True,
                data={"1001": [{"label_id": 123, "label_name": "war target"}]},
            ),
        ]
        mock_esi.client = EsiClientStub.create_from_endpoints(endpoints)
        mock_token = MockToken(1001, "Bruce Wayne")
        # when
        with patch(MODULE_PATH + ".STANDINGSSYNC_WAR_TARGETS_LABEL_NAME", "WAR TARGET"):
            result = esi_contacts.determine_character_wt_label_id(token=mock_token)
        # then
        self.assertEqual(result, 123)

    def test_should_return_not_return_wt_label_id_1(self, mock_esi):
        # given
        endpoints = [
            EsiEndpoint(
                "Contacts",
                "get_characters_character_id_contacts_labels",
                "character_id",
                needs_token=True,
                data={"1001": [{"label_id": 123, "label_name": "xyz"}]},
            ),
        ]
        mock_esi.client = EsiClientStub.create_from_endpoints(endpoints)
        mock_token = MockToken(1001, "Bruce Wayne")
        # when
        with patch(MODULE_PATH + ".STANDINGSSYNC_WAR_TARGETS_LABEL_NAME", "WAR TARGET"):
            result = esi_contacts.determine_character_wt_label_id(token=mock_token)
        # then
        self.assertIsNone(result)

    def test_should_return_not_return_wt_label_id_2(self, mock_esi):
        # given
        endpoints = [
            EsiEndpoint(
                "Contacts",
                "get_characters_character_id_contacts_labels",
                "character_id",
                needs_token=True,
                data={"1001": []},
            ),
        ]
        mock_esi.client = EsiClientStub.create_from_endpoints(endpoints)
        mock_token = MockToken(1001, "Bruce Wayne")
        # when
        with patch(MODULE_PATH + ".STANDINGSSYNC_WAR_TARGETS_LABEL_NAME", "WAR TARGET"):
            result = esi_contacts.determine_character_wt_label_id(token=mock_token)
        # then
        self.assertIsNone(result)
