from dataclasses import dataclass
from unittest.mock import patch

from app_utils.esi_testing import EsiClientStub, EsiEndpoint
from app_utils.testing import NoSocketsTestCase

from standingssync.core import esi_wrapper

from ..factories import EsiLabelDictFactory, EveEntityCharacterFactory
from ..utils import EsiCharacterContactsStub, EsiContact

MODULE_PATH = "standingssync.core.esi_wrapper"


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
        result = esi_wrapper.fetch_alliance_contacts(alliance_id=3001, token=mock_token)
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
        result = esi_wrapper.fetch_character_contacts(token=mock_token)
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
        result = esi_wrapper.fetch_character_contact_labels(token=mock_token)
        # then
        self.assertListEqual(result, esi_labels)

    def test_should_delete_contacts(self, mock_esi):
        # given
        mock_token = MockToken(1001, "Bruce Wayne")
        contact_1002 = EsiContact(1002, EsiContact.ContactType.CHARACTER, 5)
        contact_1003 = EsiContact(1003, EsiContact.ContactType.CHARACTER, 5)
        esi_stub = EsiCharacterContactsStub()
        esi_stub.setup_contacts(1001, [contact_1002, contact_1003])
        esi_stub.setup_esi_mock(mock_esi)
        # when
        esi_wrapper.delete_character_contacts(mock_token, [1003])
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
        result = esi_wrapper.add_character_contacts(
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
        result = esi_wrapper.update_character_contacts(
            mock_token, {contact.standing: [contact.contact_id]}
        )
        # then
        self.assertTrue(result)
        self.assertSetEqual(set(esi_stub.contacts(1001)), {contact})
