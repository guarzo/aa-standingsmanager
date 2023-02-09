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


@patch(MODULE_PATH + ".STANDINGSSYNC_WAR_TARGETS_LABEL_NAME", "WAR TARGET")
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

    def test_should_return_labels(self):
        # given
        labels = {EsiContactLabelFactory(), EsiContactLabelFactory()}
        obj = EsiContactsClone.from_esi_contacts(labels=labels)
        # when/then
        self.assertSetEqual(labels, obj.labels())

    def test_should_return_contacts(self):
        # given
        contacts = {EsiContactFactory(), EsiContactFactory()}
        obj = EsiContactsClone.from_esi_contacts(contacts)
        # when/then
        self.assertSetEqual(contacts, obj.contacts())

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

    def test_should_find_war_target_id(self):
        # given
        label_1 = EsiContactLabelFactory(name="war target")
        label_2 = EsiContactLabelFactory()
        obj = EsiContactsClone.from_esi_contacts(labels=[label_1, label_2])
        # when
        result = obj.war_target_label_id()
        # then
        self.assertEqual(result, label_1.id)

    def test_should_not_find_war_target_id(self):
        # given
        label_1 = EsiContactLabelFactory(name="alpha")
        label_2 = EsiContactLabelFactory(name="bravo")
        obj = EsiContactsClone.from_esi_contacts(labels=[label_1, label_2])
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
        obj = EsiContactsClone.from_esi_contacts(
            contacts=[other_contact, war_target], labels=[wt_label, other_label]
        )
        # when
        result = obj.war_targets()
        # then
        self.assertSetEqual(result, {war_target})

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
        c4a = c4.clone(standing=-10)
        a = EsiContactsClone.from_esi_contacts([c1, c2, c4])
        b = EsiContactsClone.from_esi_contacts([c1, c3, c4a])
        # when
        added, removed, changed = a.contacts_difference(b)
        # then
        self.assertSetEqual(added, {c3})
        self.assertSetEqual(removed, {c2})
        self.assertSetEqual(changed, {c4a})
