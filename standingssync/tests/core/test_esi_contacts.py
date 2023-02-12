from unittest.mock import patch

from app_utils.testing import NoSocketsTestCase

from standingssync.core.esi_contacts import (
    EsiContact,
    EsiContactLabel,
    EsiContactsContainer,
)

from ..factories import EsiContactFactory, EsiContactLabelFactory, EveContactFactory

MODULE_PATH = "standingssync.core.esi_contacts"


class TestEsiContact(NoSocketsTestCase):
    def test_should_create_new_1(self):
        # when
        obj = EsiContact(1001, EsiContact.ContactType.CHARACTER, 5.0)
        # then
        self.assertEqual(obj.contact_id, 1001)
        self.assertEqual(obj.contact_type, EsiContact.ContactType.CHARACTER)
        self.assertEqual(obj.standing, 5.0)

    def test_should_create_new_2(self):
        # when
        obj = EsiContact(1001, "character", 5.0)
        # then
        self.assertEqual(obj.contact_id, 1001)
        self.assertEqual(obj.contact_type, EsiContact.ContactType.CHARACTER)
        self.assertEqual(obj.standing, 5.0)

    def test_should_create_new_3(self):
        # when/then
        with self.assertRaises(ValueError):
            EsiContact(1001, "xyz", 5.0)

    def test_should_clone_contact_1(self):
        # given
        a = EsiContact(1, "character", 5.0, [1, 2])
        # when
        b = a.clone()
        # then
        self.assertEqual(a, b)

    def test_should_clone_contact_2(self):
        # given
        a = EsiContact(1, "character", 5.0, [1, 2])
        # when
        b = a.clone(standing=-10)
        # then
        self.assertEqual(b.contact_id, a.contact_id)
        self.assertEqual(b.contact_type, a.contact_type)
        self.assertEqual(b.label_ids, a.label_ids)
        self.assertEqual(b.standing, -10)

    def test_should_create_from_dict_1(self):
        # given
        esi_dict = {"contact_id": 1, "contact_type": "character", "standing": 5.0}
        # when
        obj = EsiContact.from_esi_dict(esi_dict)
        # then
        self.assertEqual(obj, EsiContact(1, "character", 5.0))

    def test_should_create_from_dict_2(self):
        # given
        esi_dict = {"contact_id": 1, "contact_type": "corporation", "standing": 5.0}
        # when
        obj = EsiContact.from_esi_dict(esi_dict)
        # then
        self.assertEqual(obj, EsiContact(1, "corporation", 5.0))

    def test_should_create_from_dict_3(self):
        # given
        esi_dict = {"contact_id": 1, "contact_type": "alliance", "standing": 5.0}
        # when
        obj = EsiContact.from_esi_dict(esi_dict)
        # then
        self.assertEqual(obj, EsiContact(1, "alliance", 5.0))

    def test_should_create_from_dict_4(self):
        # given
        esi_dict = {
            "contact_id": 1,
            "contact_type": "alliance",
            "standing": 5.0,
            "label_ids": None,
        }
        # when
        obj = EsiContact.from_esi_dict(esi_dict)
        # then
        self.assertEqual(obj, EsiContact(1, "alliance", 5.0))


class TestEsiContactLabel(NoSocketsTestCase):
    def test_should_create_from_esi_dict(self):
        # given
        esi_dict = {"label_id": 42, "label_name": "alpha"}
        # when
        result = EsiContactLabel.from_esi_dict(esi_dict)
        # then
        self.assertEqual(result.id, 42)
        self.assertEqual(result.name, "alpha")

    def test_should_convert_to_dict(self):
        # given
        obj = EsiContactLabel(42, "alpha")
        # when
        result = obj.to_dict()
        # then
        expected = {42: "alpha"}
        self.assertDictEqual(expected, result)

    def test_should_convert_to_esi_dict(self):
        # given
        obj = EsiContactLabel(42, "alpha")
        # when
        result = obj.to_esi_dict()
        # then
        expected = {"label_id": 42, "label_name": "alpha"}
        self.assertDictEqual(expected, result)


@patch(MODULE_PATH + ".STANDINGSSYNC_WAR_TARGETS_LABEL_NAME", "WAR TARGET")
class TestEsiContactsClone(NoSocketsTestCase):
    def test_should_create_empty(self):
        # when
        obj = EsiContactsContainer()
        # then
        self.assertIsInstance(obj, EsiContactsContainer)

    def test_should_create_from_contacts_dict(self):
        # given
        contact_1 = EsiContactFactory()
        contact_2 = EsiContactFactory()
        esi_contacts = [contact_1.to_esi_dict(), contact_2.to_esi_dict()]
        # when
        obj = EsiContactsContainer.from_esi_dicts(esi_contacts)
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
        obj = EsiContactsContainer.from_esi_dicts(esi_contacts, esi_labels)
        # then
        expected = {contact_1, contact_2}
        self.assertSetEqual(obj.contacts(), expected)

    def test_should_create_from_esi_contacts(self):
        # given
        contact_1 = EsiContactFactory()
        contact_2 = EsiContactFactory()
        esi_contacts = [contact_1, contact_2]
        # when
        obj = EsiContactsContainer.from_esi_contacts(esi_contacts)
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
        obj = EsiContactsContainer.from_esi_contacts(esi_contacts, esi_labels)
        # then
        expected = {contact_1, contact_2}
        self.assertSetEqual(obj.contacts(), expected)

    def test_should_return_contacts_by_id(self):
        # given
        c1 = EsiContactFactory()
        c2 = EsiContactFactory()
        contacts = EsiContactsContainer.from_esi_contacts([c1, c2])
        # when
        result = contacts.contact_by_id(c1.contact_id)
        # then
        self.assertEqual(result, c1)

    def test_should_remove_unknown_label_ids(self):
        # given
        label_1 = EsiContactLabelFactory()
        label_2 = EsiContactLabelFactory()
        contacts = EsiContactsContainer.from_esi_contacts(labels=[label_1])
        contact_1 = EsiContactFactory(label_ids=[label_1.id, label_2.id])
        # when
        contacts.add_contact(contact_1)
        # then
        contact_1a = contacts.contact_by_id(contact_1.contact_id)
        self.assertEqual(contact_1a.label_ids, frozenset([label_1.id]))

    def test_should_return_labels(self):
        # given
        labels = {EsiContactLabelFactory(), EsiContactLabelFactory()}
        obj = EsiContactsContainer.from_esi_contacts(labels=labels)
        # when/then
        self.assertSetEqual(labels, obj.labels())

    def test_should_return_contacts(self):
        # given
        contacts = {EsiContactFactory(), EsiContactFactory()}
        obj = EsiContactsContainer.from_esi_contacts(contacts)
        # when/then
        self.assertSetEqual(contacts, obj.contacts())

    def test_should_remove_contact(self):
        # given
        contact_1 = EsiContactFactory()
        contact_2 = EsiContactFactory()
        esi_contacts = [contact_1.to_esi_dict(), contact_2.to_esi_dict()]
        obj = EsiContactsContainer.from_esi_dicts(esi_contacts)
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
        obj = EsiContactsContainer.from_esi_dicts(esi_contacts, esi_labels)
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
        obj_1 = EsiContactsContainer.from_esi_dicts(esi_contacts, esi_labels)
        obj_2 = EsiContactsContainer.from_esi_dicts(esi_contacts, esi_labels)
        # when/then
        self.assertEqual(obj_1.version_hash(), obj_2.version_hash())

    def test_should_find_war_target_id(self):
        # given
        label_1 = EsiContactLabelFactory(name="war target")
        label_2 = EsiContactLabelFactory()
        obj = EsiContactsContainer.from_esi_contacts(labels=[label_1, label_2])
        # when
        result = obj.war_target_label_id()
        # then
        self.assertEqual(result, label_1.id)

    def test_should_not_find_war_target_id(self):
        # given
        label_1 = EsiContactLabelFactory(name="alpha")
        label_2 = EsiContactLabelFactory(name="bravo")
        obj = EsiContactsContainer.from_esi_contacts(labels=[label_1, label_2])
        # when
        result = obj.war_target_label_id()
        # then
        self.assertIsNone(result)

    def test_should_return_war_targets(self):
        # given
        wt_label = EsiContactLabelFactory(name="war target")
        other_label = EsiContactLabelFactory()
        other_contact = EsiContactFactory(label_ids=[other_label.id])
        war_target = EsiContactFactory(label_ids=[wt_label.id, other_label.id])
        obj = EsiContactsContainer.from_esi_contacts(
            contacts=[other_contact, war_target], labels=[wt_label, other_label]
        )
        # when
        result = obj.war_targets()
        # then
        self.assertSetEqual(result, {war_target})

    def test_should_add_eve_contacts(self):
        # given
        obj = EsiContactsContainer()
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
        obj = EsiContactsContainer()
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
        c4a = c4.clone(standing=-10)
        a = EsiContactsContainer.from_esi_contacts([c1, c2, c4])
        b = EsiContactsContainer.from_esi_contacts([c1, c3, c4a])
        # when
        added, removed, changed = a.contacts_difference(b)
        # then
        self.assertSetEqual(added, {c3})
        self.assertSetEqual(removed, {c2})
        self.assertSetEqual(changed, {c4a})
