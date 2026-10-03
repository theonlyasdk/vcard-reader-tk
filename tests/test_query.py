"""Filter/sort logic tests (pure, no Tk needed)."""

import unittest

from core import filter_contacts, parse_vcards, sort_contacts


def make_contacts():
    return parse_vcards("\n".join([
        "BEGIN:VCARD", "VERSION:3.0", "FN:Zed Alpha", "ORG:Zeta",
        "EMAIL:zed@z.co", "TEL:111", "END:VCARD",
        "BEGIN:VCARD", "VERSION:3.0", "FN:Amy Beta", "ORG:Alpha",
        "EMAIL:amy@a.co", "END:VCARD",
        "BEGIN:VCARD", "VERSION:3.0", "FN:Max NoMail",
        "ADR:;;Street;City;R;1;C", "TEL:333", "END:VCARD",
    ]))


class TestFilter(unittest.TestCase):
    def setUp(self):
        self.contacts = make_contacts()

    def names(self, contacts):
        return [c.display_name for c in contacts]

    def test_empty_query_returns_all(self):
        self.assertEqual(len(filter_contacts(self.contacts, "")), 3)
        self.assertEqual(len(filter_contacts(self.contacts)), 3)

    def test_query_matches_name_case_insensitive(self):
        self.assertEqual(self.names(filter_contacts(self.contacts, "amy")),
                         ["Amy Beta"])
        self.assertEqual(self.names(filter_contacts(self.contacts, "AMY")),
                         ["Amy Beta"])

    def test_query_matches_phone_email_org(self):
        self.assertEqual(self.names(filter_contacts(self.contacts, "333")),
                         ["Max NoMail"])
        self.assertEqual(self.names(filter_contacts(self.contacts, "zed@z")),
                         ["Zed Alpha"])
        self.assertEqual(self.names(filter_contacts(self.contacts, "alpha")),
                         ["Zed Alpha", "Amy Beta"])

    def test_query_no_match(self):
        self.assertEqual(filter_contacts(self.contacts, "zzz-nope"), [])

    def test_kind_filters(self):
        self.assertEqual(self.names(filter_contacts(self.contacts, kind="Has phone")),
                         ["Zed Alpha", "Max NoMail"])
        self.assertEqual(self.names(filter_contacts(self.contacts, kind="Has email")),
                         ["Zed Alpha", "Amy Beta"])
        self.assertEqual(self.names(filter_contacts(self.contacts, kind="Has address")),
                         ["Max NoMail"])
        self.assertEqual(self.names(filter_contacts(self.contacts, kind="Has organisation")),
                         ["Zed Alpha", "Amy Beta"])
        self.assertEqual(len(filter_contacts(self.contacts, kind="All")), 3)

    def test_query_and_kind_combine(self):
        result = filter_contacts(self.contacts, "a", kind="Has phone")
        self.assertEqual(self.names(result), ["Zed Alpha", "Max NoMail"])

    def test_unknown_kind_ignored(self):
        self.assertEqual(len(filter_contacts(self.contacts, kind="Bogus")), 3)

    def test_input_not_mutated(self):
        before = list(self.contacts)
        filter_contacts(self.contacts, "amy", kind="Has email")
        self.assertEqual(self.contacts, before)


class TestSort(unittest.TestCase):
    def setUp(self):
        self.contacts = make_contacts()

    def names(self, contacts):
        return [c.display_name for c in contacts]

    def test_name_az(self):
        self.assertEqual(self.names(sort_contacts(self.contacts, "Name A–Z")),
                         ["Amy Beta", "Max NoMail", "Zed Alpha"])

    def test_name_za(self):
        self.assertEqual(self.names(sort_contacts(self.contacts, "Name Z–A")),
                         ["Zed Alpha", "Max NoMail", "Amy Beta"])

    def test_organisation(self):
        result = sort_contacts(self.contacts, "Organisation")
        self.assertEqual(self.names(result),
                         ["Max NoMail", "Amy Beta", "Zed Alpha"])

    def test_email_missing_last(self):
        result = sort_contacts(self.contacts, "Email")
        self.assertEqual(self.names(result),
                         ["Amy Beta", "Zed Alpha", "Max NoMail"])

    def test_unknown_sort_defaults_to_name(self):
        self.assertEqual(self.names(sort_contacts(self.contacts, "Bogus")),
                         ["Amy Beta", "Max NoMail", "Zed Alpha"])

    def test_input_not_mutated(self):
        before = [c.display_name for c in self.contacts]
        sort_contacts(self.contacts, "Name Z–A")
        self.assertEqual([c.display_name for c in self.contacts], before)


if __name__ == "__main__":
    unittest.main()
