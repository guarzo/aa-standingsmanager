from copy import deepcopy
from unittest.mock import patch

from app_utils.testing import NoSocketsTestCase

from standingssync.core.esi_contacts import EsiContact, EsiContactsClone

from ..factories import EsiContactFactory, EsiContactLabelFactory, EveContactFactory

MODULE_PATH = "standingssync.core.esi_contacts"


class TestEsiContact(NoSocketsTestCase):
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
        result = EsiContact.group_for_esi_update(esi_contacts)
        self.maxDiff = None
        # then
        expected = {
            frozenset({1}): {contact_1.standing: {contact_1.contact_id}},
            frozenset({1, 2}): {contact_2.standing: {contact_2.contact_id}},
            frozenset(): {2.0: {contact_3.contact_id, contact_4.contact_id}},
        }
        self.assertEqual(expected, result)


class TestEsiContactsClone(NoSocketsTestCase):
    def test_should_create_empty(self):
        # when
        obj = EsiContactsClone()
        # then
        self.assertIsInstance(obj, EsiContactsClone)

    def test_should_create_from_contacts_dict(self):
        # given
        contact_1 = EsiContactFactory()
        contact_2 = EsiContactFactory()
        esi_contacts = [contact_1.to_esi_dict(), contact_2.to_esi_dict()]
        # when
        obj = EsiContactsClone.from_esi_dicts(esi_contacts)
        # then
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
        obj = EsiContactsClone.from_esi_dicts(esi_contacts, esi_labels)
        # then
        expected = {contact_1, contact_2}
        self.assertSetEqual(obj.contacts(), expected)

    def test_should_create_from_esi_contacts(self):
        # given
        contact_1 = EsiContactFactory()
        contact_2 = EsiContactFactory()
        esi_contacts = [contact_1, contact_2]
        # when
        obj = EsiContactsClone.from_esi_contacts(esi_contacts)
        # then
        expected = {contact_1, contact_2}
        self.assertSetEqual(obj.contacts(), expected)

    def test_should_create_from_esi_contacts_w_labels(self):
        # given
        label_1 = EsiContactLabelFactory()
        contact_1 = EsiContactFactory(label_ids=[label_1.id])
        label_2 = EsiContactLabelFactory()
        contact_2 = EsiContactFactory(label_ids=[label_1.id, label_2.id])
        esi_contacts = [contact_1, contact_2]
        esi_labels = [label_1, label_2]
        # when
        obj = EsiContactsClone.from_esi_contacts(esi_contacts, esi_labels)
        # then
        expected = {contact_1, contact_2}
        self.assertSetEqual(obj.contacts(), expected)

    def test_should_abort_when_encountering_invalid_label(self):
        # given
        label_1 = EsiContactLabelFactory()
        label_2 = EsiContactLabelFactory()
        esi_labels = [label_1.to_esi_dict()]
        obj = EsiContactsClone.from_esi_dicts(labels=esi_labels)
        contact = EsiContactFactory(label_ids=[label_2.id])
        # when/then
        with self.assertRaises(ValueError):
            obj.add_contact(contact)

    def test_should_remove_contact(self):
        # given
        contact_1 = EsiContactFactory()
        contact_2 = EsiContactFactory()
        esi_contacts = [contact_1.to_esi_dict(), contact_2.to_esi_dict()]
        obj = EsiContactsClone.from_esi_dicts(esi_contacts)
        # when
        obj.remove_contact(contact_2.contact_id)
        # then
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
        obj = EsiContactsClone.from_esi_dicts(esi_contacts, esi_labels)
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
        obj_1 = EsiContactsClone.from_esi_dicts(esi_contacts, esi_labels)
        obj_2 = EsiContactsClone.from_esi_dicts(esi_contacts, esi_labels)
        # when/then
        self.assertEqual(obj_1.version_hash(), obj_2.version_hash())

    @patch(MODULE_PATH + ".STANDINGSSYNC_WAR_TARGETS_LABEL_NAME", "WAR TARGET")
    def test_should_find_war_target_id(self):
        # given
        label_1 = EsiContactLabelFactory(name="war target")
        label_2 = EsiContactLabelFactory()
        esi_labels = [label_1.to_esi_dict(), label_2.to_esi_dict()]
        obj = EsiContactsClone.from_esi_dicts(labels=esi_labels)
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
        obj = EsiContactsClone.from_esi_dicts(labels=esi_labels)
        # when
        result = obj.war_target_label_id()
        # then
        self.assertIsNone(result)

    def test_should_add_eve_contacts(self):
        # given
        obj = EsiContactsClone()
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
        obj = EsiContactsClone()
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


class TestEsiContactsCloneComparisons(NoSocketsTestCase):
    def test_should_return_contacts_difference(self):
        # given
        c1 = EsiContactFactory()
        c2 = EsiContactFactory()
        c3 = EsiContactFactory()
        c4 = EsiContactFactory(standing=5)
        c4a = deepcopy(c4)
        c4a.standing = -10
        a = EsiContactsClone.from_esi_contacts([c1, c2, c4])
        b = EsiContactsClone.from_esi_contacts([c1, c3, c4a])
        # when
        added, removed, changed = a.contacts_difference(b)
        # then
        self.assertSetEqual(added, {c3})
        self.assertSetEqual(removed, {c2})
        self.assertSetEqual(changed, {c4})
