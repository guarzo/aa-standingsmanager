from dataclasses import dataclass
from unittest.mock import patch

from app_utils.esi_testing import EsiClientStub, EsiEndpoint
from app_utils.testing import NoSocketsTestCase

from standingsmanager.core import esi_api
from standingsmanager.core.esi_contacts import EsiContact
from standingsmanager.tests.factories import (
    EsiContactFactory,
    EsiContactLabelFactory,
    EveEntityCharacterFactory,
)
from standingsmanager.tests.utils import EsiCharacterContactsStub

MODULE_PATH = "standingsmanager.core.esi_api"


@dataclass
class MockToken:
    character_id: int
    character_name: str

    def valid_access_token(self):
        return "DUMMY-TOKEN"


@patch(MODULE_PATH + ".esi")
class TestEsiContactsApi(NoSocketsTestCase):
    # Alliance contacts test removed - functionality deprecated in refactor

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
        esi_stub = EsiCharacterContactsStub.create(
            1001, mock_esi, contacts=[contact_1002, contact_1003]
        )
        # when
        esi_api.delete_character_contacts(mock_token, [contact_1003])
        # then
        self.assertSetEqual(esi_stub.contacts(), {contact_1002})

    def test_should_add_contacts(self, mock_esi):
        # given
        mock_token = MockToken(1001, "Bruce Wayne")
        contact = EsiContact.from_eve_entity(EveEntityCharacterFactory(), standing=5.0)
        esi_stub = EsiCharacterContactsStub.create(1001, mock_esi)
        # when
        esi_api.add_character_contacts(mock_token, {contact})
        # then
        self.assertSetEqual(esi_stub.contacts(), {contact})

    def test_should_update_contact(self, mock_esi):
        # given
        mock_token = MockToken(1001, "Bruce Wayne")
        contact = EsiContact.from_eve_entity(EveEntityCharacterFactory(), standing=-5)
        old_esi_contact = EsiContact(
            contact_id=contact.contact_id,
            contact_type=contact.contact_type,
            standing=10,
        )
        esi_stub = EsiCharacterContactsStub.create(
            1001, mock_esi, contacts=[old_esi_contact]
        )
        # when
        esi_api.update_character_contacts(mock_token, {contact})
        # then
        self.assertSetEqual(esi_stub.contacts(), {contact})


class TestEsiContactsHelpers(NoSocketsTestCase):
    def test_should_group_contacts_for_esi_update(self):
        # given
        label_1 = EsiContactLabelFactory(id=1)
        contact_1 = EsiContactFactory(contact_id=11, label_ids=[label_1.id])
        label_2 = EsiContactLabelFactory(id=2)
        contact_2 = EsiContactFactory(contact_id=12, label_ids=[label_1.id, label_2.id])
        contact_3 = EsiContactFactory(contact_id=13, standing=2.0)
        contact_4 = EsiContactFactory(contact_id=14, standing=2.0)
        esi_contacts = [contact_1, contact_2, contact_3, contact_4]
        # when
        result = esi_api._group_for_esi_update(esi_contacts)
        self.maxDiff = None
        # then
        expected = {
            frozenset({1}): {contact_1.standing: {contact_1.contact_id}},
            frozenset({1, 2}): {contact_2.standing: {contact_2.contact_id}},
            frozenset(): {2.0: {contact_3.contact_id, contact_4.contact_id}},
        }
        self.assertEqual(expected, result)


class TestEsiRetryLogic(NoSocketsTestCase):
    """Tests for retry logic added in Phase 3."""

    @patch(MODULE_PATH + ".time.sleep")
    @patch(MODULE_PATH + ".esi")
    def test_retry_on_rate_limit(self, mock_esi, mock_sleep):
        # given
        from unittest.mock import Mock

        from requests.exceptions import HTTPError

        mock_response = Mock()
        mock_response.status_code = 429
        http_error = HTTPError(response=mock_response)

        mock_token = MockToken(1001, "Bruce Wayne")

        # Mock the entire call chain to fail first then succeed
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise http_error
            return [
                {
                    "contact_id": 2001,
                    "contact_type": "corporation",
                    "standing": 9.9,
                }
            ]

        # Mock the results method to track calls
        mock_results = Mock(side_effect=side_effect)
        mock_esi.client.Contacts.get_characters_character_id_contacts.return_value.results = (
            mock_results
        )

        # when
        result = esi_api.fetch_character_contacts(token=mock_token)

        # then
        self.assertEqual(len(result), 1)
        self.assertEqual(call_count[0], 2)  # Should have been called twice
        mock_sleep.assert_called_once()  # Should have slept once for retry

    @patch(MODULE_PATH + ".time.sleep")
    @patch(MODULE_PATH + ".esi")
    def test_retry_gives_up_after_max_retries(self, mock_esi, mock_sleep):
        # given
        from unittest.mock import Mock

        from requests.exceptions import HTTPError

        mock_response = Mock()
        mock_response.status_code = 503  # Server error
        http_error = HTTPError(response=mock_response)

        mock_esi.client.Contacts.get_characters_character_id_contacts.return_value.results.side_effect = (
            http_error
        )
        mock_token = MockToken(1001, "Bruce Wayne")

        # when/then
        with self.assertRaises(HTTPError):
            esi_api.fetch_character_contacts(token=mock_token)

        # Should have slept MAX_RETRIES - 1 times (first failure, then retries)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch(MODULE_PATH + ".esi")
    def test_no_retry_on_client_error(self, mock_esi):
        # given
        from unittest.mock import Mock

        from requests.exceptions import HTTPError

        mock_response = Mock()
        mock_response.status_code = 404  # Not found
        http_error = HTTPError(response=mock_response)

        mock_esi.client.Contacts.get_characters_character_id_contacts.return_value.results.side_effect = (
            http_error
        )
        mock_token = MockToken(1001, "Bruce Wayne")

        # when/then - Should fail immediately without retry
        with self.assertRaises(HTTPError):
            esi_api.fetch_character_contacts(token=mock_token)


# War API tests removed - war functionality deprecated in AA Standings Manager refactor
# War targets are no longer supported in the new implementation
