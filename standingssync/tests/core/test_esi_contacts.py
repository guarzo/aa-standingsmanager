from dataclasses import dataclass
from unittest.mock import patch

from app_utils.esi_testing import EsiClientStub, EsiEndpoint
from app_utils.testing import NoSocketsTestCase

from standingssync.core import esi_contacts

from ..factories import EsiLabelDictFactory, EveContactFactory
from ..utils import EsiCharacterContactsStub, EsiContact

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

    def test_should_return_contact_labels(self, mock_esi):
        # given
        esi_labels = [EsiLabelDictFactory(), EsiLabelDictFactory()]
        endpoints = [
            EsiEndpoint(
                "Contacts",
                "get_characters_character_id_contacts_labels",
                "character_id",
                needs_token=True,
                data={"1001": esi_labels},
            ),
        ]
        mock_esi.client = EsiClientStub.create_from_endpoints(endpoints)
        mock_token = MockToken(1001, "Bruce Wayne")
        # when
        result = esi_contacts.fetch_character_contact_labels(token=mock_token)
        # then
        self.assertListEqual(result, esi_labels)

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

    def test_should_delete_contacts(self, mock_esi):
        # given
        mock_token = MockToken(1001, "Bruce Wayne")
        contact_1002 = EsiContact(1002, EsiContact.ContactType.CHARACTER, 5)
        contact_1003 = EsiContact(1003, EsiContact.ContactType.CHARACTER, 5)
        esi_stub = EsiCharacterContactsStub()
        esi_stub.setup_contacts(1001, [contact_1002, contact_1003])
        esi_stub.setup_esi_mock(mock_esi)
        # when
        esi_contacts.delete_character_contacts(mock_token, [1003])
        # then
        self.assertSetEqual(set(esi_stub.contacts(1001)), {contact_1002})

    def test_should_add_contact(self, mock_esi):
        # given
        mock_token = MockToken(1001, "Bruce Wayne")
        contact = EveContactFactory()
        esi_stub = EsiCharacterContactsStub()
        esi_stub.setup_contacts(1001, [])
        esi_stub.setup_esi_mock(mock_esi)
        # when
        result = esi_contacts.add_character_contacts(
            mock_token, {contact.standing: [contact]}
        )
        # then
        self.assertTrue(result)
        self.assertSetEqual(
            set(esi_stub.contacts(1001)), {EsiContact.from_eve_contact(contact)}
        )

    def test_should_update_contact(self, mock_esi):
        # given
        mock_token = MockToken(1001, "Bruce Wayne")
        contact = EveContactFactory(standing=-5)
        old_esi_contact = EsiContact.from_eve_contact(contact)
        old_esi_contact.standing = 10
        esi_stub = EsiCharacterContactsStub()
        esi_stub.setup_contacts(1001, [old_esi_contact])
        esi_stub.setup_esi_mock(mock_esi)
        # when
        result = esi_contacts.update_character_contacts(
            mock_token, {contact.standing: [contact]}
        )
        # then
        self.assertTrue(result)
        self.assertSetEqual(
            set(esi_stub.contacts(1001)), {EsiContact.from_eve_contact(contact)}
        )
