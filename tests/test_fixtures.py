"""Fixture tests: version-specific .vcf files in tests/data/, via parse_file."""

import unittest
from pathlib import Path

from core import parse_file

DATA = Path(__file__).resolve().parent / "data"


class TestFixtures(unittest.TestCase):
    def test_every_fixture_yields_named_contacts(self):
        files = sorted(DATA.glob("*.vcf"))
        self.assertGreaterEqual(len(files), 3, "expected 2.1/3.0/4.0 fixtures")
        for path in files:
            with self.subTest(path.name):
                contacts = parse_file(path)
                self.assertGreater(len(contacts), 0)
                for contact in contacts:
                    self.assertTrue(contact.display_name)
                    self.assertEqual(contact.source, str(path))

    def test_v21_bare_params_and_quoted_printable(self):
        (c,) = parse_file(DATA / "vcard21.vcf")
        self.assertEqual(c.display_name, "Hans M\u00fcller")
        self.assertEqual(c.phones, [("Home", "030-123456"),
                                    ("Cell", "0171-987654")])
        self.assertIn("Berlin", c.addresses[0][1])
        self.assertIn("\u00c4rztin", c.note)

    def test_v30_types_and_minimal_contact(self):
        jane, bob = parse_file(DATA / "vcard30.vcf")
        self.assertEqual(jane.display_name, "Jane Smith")
        self.assertEqual(jane.organisation, "Example Corp / Engineering")
        self.assertEqual(jane.phones, [("Work", "+1-555-0100"),
                                       ("Home", "+1-555-0101")])
        self.assertEqual(jane.emails, [("Work", "jane.smith@example.com"),
                                       ("Home", "jane@example.org")])
        self.assertIn("follow up.", jane.note)
        self.assertEqual(jane.birthday, "1990-05-17")
        self.assertEqual(bob.display_name, "Bob NoDetails")
        self.assertEqual(bob.phones, [])

    def test_v40_uri_values_and_groups(self):
        (c,) = parse_file(DATA / "vcard40.vcf")
        self.assertEqual(c.display_name, "John Doe")
        self.assertEqual(c.phones, [("Cell", "+1-555-0199"),
                                    ("Home", "+1-555-0188"),
                                    ("", "+1-555-0177")])
        self.assertEqual(c.emails, [("Work", "john.doe@example.com")])


if __name__ == "__main__":
    unittest.main()
