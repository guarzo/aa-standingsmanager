from unittest.mock import patch

from app_utils.testing import NoSocketsTestCase

from standingssync.core.esi_contacts import EsiContact, EsiContactsClone

from ..factories import EsiContactFactory, EsiContactLabelFactory, EveContactFactory

MODULE_PATH = "standingssync.core.esi_contacts"


class TestEsiContactsClone(NoSocketsTestCase):
    def test_should_create_empty(self):
        # when
        obj = EsiContactsClone(1001)
        # then
        self.assertEqual(obj.character_id, 1001)

    def test_should_create_from_contacts_dict(self):
        # given
        contact_1 = EsiContactFactory()
        contact_2 = EsiContactFactory()
        esi_contacts = [contact_1.to_esi_dict(), contact_2.to_esi_dict()]
        # when
        obj = EsiContactsClone.from_esi_dicts(1001, esi_contacts)
        # then
        self.assertEqual(obj.character_id, 1001)
        expected = {contact_1, contact_2}
        self.assertSetEqual(obj.contacts(), expected)

    def test_should_create_from_contacts_dict_w_labels(self):
        # given
        label_1 = EsiContactLabelFactory()
        contact_1 = EsiContactFactory(label_ids=[label_1.id])
        label_2 = EsiContactLabelFactory()
        contact_2 = EsiContactFactory(label_ids=[label_1.id, label_2.id])
        esi_contacts = [contact_1.to_esi_dict(), contact_2.to_esi_dict()]
        esi_labels = [label_1.to_esi_dict(), label_2.to_esi_dict()]
        # when
        obj = EsiContactsClone.from_esi_dicts(1001, esi_contacts, esi_labels)
        # then
        self.assertEqual(obj.character_id, 1001)
        expected = {contact_1, contact_2}
        self.assertSetEqual(obj.contacts(), expected)

    def test_should_abort_when_encountering_invalid_label(self):
        # given
        label_1 = EsiContactLabelFactory()
        label_2 = EsiContactLabelFactory()
        esi_labels = [label_1.to_esi_dict()]
        obj = EsiContactsClone.from_esi_dicts(1001, labels=esi_labels)
        contact = EsiContactFactory(label_ids=[label_2.id])
        # when/then
        with self.assertRaises(ValueError):
            obj.add_contact(contact)

    def test_should_remove_contact(self):
        # given
        contact_1 = EsiContactFactory()
        contact_2 = EsiContactFactory()
        esi_contacts = [contact_1.to_esi_dict(), contact_2.to_esi_dict()]
        obj = EsiContactsClone.from_esi_dicts(1001, esi_contacts)
        # when
        obj.remove_contact(contact_2.contact_id)
        # then
        self.assertEqual(obj.character_id, 1001)
        expected = {contact_1}
        self.assertSetEqual(obj.contacts(), expected)

    def test_should_convert_to_esi_dict(self):
        # given
        label_1 = EsiContactLabelFactory(id=1)
        contact_1 = EsiContactFactory(contact_id=11, label_ids=[label_1.id])
        label_2 = EsiContactLabelFactory(id=2)
        contact_2 = EsiContactFactory(contact_id=12, label_ids=[label_1.id, label_2.id])
        esi_contacts = [contact_1.to_esi_dict(), contact_2.to_esi_dict()]
        esi_labels = [label_1.to_esi_dict(), label_2.to_esi_dict()]
        obj = EsiContactsClone.from_esi_dicts(1001, esi_contacts, esi_labels)
        # when/then
        self.assertListEqual(obj.contacts_to_esi_dicts(), esi_contacts)
        self.assertListEqual(obj.labels_to_esi_dicts(), esi_labels)

    def test_should_generate_version_hash(self):
        # given
        label_1 = EsiContactLabelFactory()
        contact_1 = EsiContactFactory(label_ids=[label_1.id])
        label_2 = EsiContactLabelFactory()
        contact_2 = EsiContactFactory(label_ids=[label_1.id, label_2.id])
        esi_contacts = [contact_1.to_esi_dict(), contact_2.to_esi_dict()]
        esi_labels = [label_1.to_esi_dict(), label_2.to_esi_dict()]
        obj_1 = EsiContactsClone.from_esi_dicts(1001, esi_contacts, esi_labels)
        obj_2 = EsiContactsClone.from_esi_dicts(1001, esi_contacts, esi_labels)
        # when/then
        self.assertEqual(obj_1.version_hash(), obj_2.version_hash())

    @patch(MODULE_PATH + ".STANDINGSSYNC_WAR_TARGETS_LABEL_NAME", "WAR TARGET")
    def test_should_find_war_target_id(self):
        # given
        label_1 = EsiContactLabelFactory(name="war target")
        label_2 = EsiContactLabelFactory()
        esi_labels = [label_1.to_esi_dict(), label_2.to_esi_dict()]
        obj = EsiContactsClone.from_esi_dicts(1001, labels=esi_labels)
        # when
        result = obj.war_target_label_id()
        # then
        self.assertEqual(result, label_1.id)

    @patch(MODULE_PATH + ".STANDINGSSYNC_WAR_TARGETS_LABEL_NAME", "WAR TARGET")
    def test_should_not_find_war_target_id(self):
        # given
        label_1 = EsiContactLabelFactory()
        label_2 = EsiContactLabelFactory()
        esi_labels = [label_1.to_esi_dict(), label_2.to_esi_dict()]
        obj = EsiContactsClone.from_esi_dicts(1001, labels=esi_labels)
        # when
        result = obj.war_target_label_id()
        # then
        self.assertIsNone(result)

    def test_should_add_eve_contacts(self):
        # given
        obj = EsiContactsClone(1001)
        contact_1 = EveContactFactory()
        contact_2 = EveContactFactory()
        # when
        obj.add_eve_contacts([contact_1, contact_2])
        # then
        expected = {
            EsiContact.from_eve_contact(contact_1),
            EsiContact.from_eve_contact(contact_2),
        }
        self.assertSetEqual(obj.contacts(), expected)

    def test_should_add_eve_contacts_w_labels(self):
        # given
        label = EsiContactLabelFactory()
        obj = EsiContactsClone(1001)
        obj.add_label(label)
        label_ids = [label.id]
        contact_1 = EveContactFactory()
        contact_2 = EveContactFactory()
        # when
        obj.add_eve_contacts([contact_1, contact_2], label_ids=label_ids)
        # then
        expected = {
            EsiContact.from_eve_contact(contact_1, label_ids=label_ids),
            EsiContact.from_eve_contact(contact_2, label_ids),
        }
        self.assertSetEqual(obj.contacts(), expected)

    def test_should_convert_contacts_for_esi_update(self):
        # given
        label_1 = EsiContactLabelFactory(id=1)
        contact_1 = EsiContactFactory(contact_id=11, label_ids=[label_1.id])
        label_2 = EsiContactLabelFactory(id=2)
        contact_2 = EsiContactFactory(contact_id=12, label_ids=[label_1.id, label_2.id])
        contact_3 = EsiContactFactory(contact_id=13, standing=2.0)
        contact_4 = EsiContactFactory(contact_id=14, standing=2.0)
        esi_contacts = [
            contact_1.to_esi_dict(),
            contact_2.to_esi_dict(),
            contact_3.to_esi_dict(),
            contact_4.to_esi_dict(),
        ]
        esi_labels = [label_1.to_esi_dict(), label_2.to_esi_dict()]
        obj = EsiContactsClone.from_esi_dicts(1001, esi_contacts, esi_labels)
        # when
        result = obj.contacts_for_esi_update()
        self.maxDiff = None
        # then
        expected = {
            frozenset({1}): {contact_1.standing: {contact_1.contact_id}},
            frozenset({1, 2}): {contact_2.standing: {contact_2.contact_id}},
            frozenset(): {2.0: {contact_3.contact_id, contact_4.contact_id}},
        }
        self.assertEqual(expected, result)
