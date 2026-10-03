"""Parser tests: vCard 2.1 / 3.0 / 4.0 subset, unfolding, escapes, encodings."""

import tempfile
import unittest
from pathlib import Path

from core import parse_file, parse_vcards, parse_with_diagnostics


def card(*lines):
    return "\n".join(["BEGIN:VCARD", *lines, "END:VCARD"])


class TestParseBasics(unittest.TestCase):
    def test_full_contact(self):
        contacts = parse_vcards(card(
            "VERSION:3.0",
            "N:Doe;John;Q;Mr;Jr",
            "FN:John Doe",
            "ORG:Acme;Research",
            "TITLE:Engineer",
            "TEL;TYPE=CELL,VOICE:555-1234",
            "TEL;TYPE=HOME:555-0000",
            "EMAIL;TYPE=HOME:john@example.com",
            "ADR;TYPE=HOME:;;Main St 1;Springfield;IL;12345;USA",
            "URL:https://example.com",
            "BDAY:1980-01-02",
            "NOTE:hello",
        ))
        self.assertEqual(len(contacts), 1)
        c = contacts[0]
        self.assertEqual(c.display_name, "John Doe")
        self.assertEqual((c.first_name, c.last_name), ("John", "Doe"))
        self.assertEqual(c.organisation, "Acme / Research")
        self.assertEqual(c.title, "Engineer")
        self.assertEqual(c.phones, [("Cell", "555-1234"), ("Home", "555-0000")])
        self.assertEqual(c.emails, [("Home", "john@example.com")])
        self.assertEqual(c.addresses,
                         [("Home", "Main St 1, Springfield, IL, 12345, USA")])
        self.assertEqual(c.urls, ["https://example.com"])
        self.assertEqual(c.birthday, "1980-01-02")
        self.assertEqual(c.note, "hello")

    def test_name_falls_back_to_n(self):
        (c,) = parse_vcards(card("VERSION:3.0", "N:Doe;Jane;;;", "TEL:1"))
        self.assertEqual(c.display_name, "Jane Doe")

    def test_name_falls_back_to_org_then_placeholder(self):
        (c,) = parse_vcards(card("VERSION:3.0", "ORG:Acme"))
        self.assertEqual(c.display_name, "Acme")
        (c,) = parse_vcards(card("VERSION:3.0", "TEL:1"))
        self.assertEqual(c.display_name, "(No name)")

    def test_multiple_contacts(self):
        text = "\n".join([
            card("VERSION:3.0", "FN:A", "TEL:1"),
            card("VERSION:4.0", "FN:B", "EMAIL:b@x.io"),
        ])
        contacts = parse_vcards(text)
        self.assertEqual([c.display_name for c in contacts], ["A", "B"])

    def test_empty_and_unterminated(self):
        self.assertEqual(parse_vcards(""), [])
        self.assertEqual(parse_vcards("FN:lonely\n"), [])
        contacts, issues = parse_with_diagnostics("BEGIN:VCARD\nFN:no end\n")
        self.assertEqual([c.display_name for c in contacts], ["no end"])
        self.assertEqual(len(issues), 1)
        self.assertIn("END:VCARD", issues[0].fix)

    def test_diagnostics_outside_text_and_stray_end(self):
        text = "hello\nEND:VCARD\n" + card("VERSION:3.0", "FN:D", "TEL:1")
        contacts, issues = parse_with_diagnostics(text)
        self.assertEqual([c.display_name for c in contacts], ["D"])
        self.assertEqual([i.line for i in issues], [1, 2])
        self.assertTrue(all(i.fix for i in issues))

    def test_diagnostics_missing_colon(self):
        contacts, issues = parse_with_diagnostics(
            card("VERSION:3.0", "FN:E", "TEL"))
        self.assertEqual([c.display_name for c in contacts], ["E"])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].line, 4)
        self.assertIn("':'", issues[0].problem)

    def test_diagnostics_clean_file(self):
        contacts, issues = parse_with_diagnostics(
            card("VERSION:3.0", "FN:F", "TEL:1"))
        self.assertEqual(len(contacts), 1)
        self.assertEqual(issues, [])

    def test_crlf_and_cr_line_endings(self):
        text = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:CRLF\r\nTEL:1\r\nEND:VCARD\r\n"
        (c,) = parse_vcards(text)
        self.assertEqual(c.display_name, "CRLF")
        (c,) = parse_vcards("BEGIN:VCARD\rVERSION:3.0\rFN:CR\rTEL:1\rEND:VCARD\r")
        self.assertEqual(c.display_name, "CR")

    def test_property_groups(self):
        (c,) = parse_vcards(card("VERSION:4.0", "FN:G", "item1.TEL:555",
                                 "item1.X-ABLABEL:custom"))
        self.assertEqual(c.phones, [("", "555")])

    def test_tel_uri_stripped(self):
        (c,) = parse_vcards(card("VERSION:4.0", "FN:U", "TEL:tel:555-42"))
        self.assertEqual(c.phones, [("", "555-42")])

    def test_multiple_notes_joined(self):
        (c,) = parse_vcards(card("VERSION:3.0", "FN:N", "NOTE:one", "NOTE:two"))
        self.assertEqual(c.note, "one\ntwo")


class TestUnfoldingAndEscapes(unittest.TestCase):
    def test_folded_line(self):
        (c,) = parse_vcards(card(
            "VERSION:3.0", "FN:F", "NOTE:first part",
            " second part", "\tthird part", "TEL:1"))
        self.assertEqual(c.note, "first partsecond partthird part")

    def test_escapes(self):
        (c,) = parse_vcards(card(
            "VERSION:3.0",
            r"FN:A\;B\,C\\D",
            "TEL:1"))
        self.assertEqual(c.display_name, "A;B,C\\D")

    def test_nul_bytes_stripped(self):
        (c,) = parse_vcards("BEGIN:VCARD\nVERSION:3.0\nFN:Nu\x00l\nTEL:1\nEND:VCARD\n")
        self.assertEqual(c.display_name, "Nul")

    def test_escaped_newline_in_note(self):
        (c,) = parse_vcards(card("VERSION:3.0", "FN:F", r"NOTE:line1\nline2", "TEL:1"))
        self.assertEqual(c.note, "line1\nline2")


class TestQuotedPrintable(unittest.TestCase):
    def test_qp_utf8(self):
        (c,) = parse_vcards(card(
            "VERSION:2.1",
            "N;ENCODING=QUOTED-PRINTABLE:M=C3=BCller;Hans;;;",
            "FN;ENCODING=QUOTED-PRINTABLE:Hans M=C3=BCller",
            "TEL:1"))
        self.assertEqual(c.display_name, "Hans M\u00fcller")
        self.assertEqual(c.last_name, "M\u00fcller")

    def test_version_parsed(self):
        (c,) = parse_vcards(card("VERSION:3.0", "FN:V", "TEL:1"))
        self.assertEqual(c.version, "3.0")

    def test_qp_plain_ascii_untouched(self):
        (c,) = parse_vcards(card("VERSION:3.0", "FN:Plain", "TEL:1"))
        self.assertEqual(c.display_name, "Plain")


class TestParseFile(unittest.TestCase):
    def test_roundtrip_utf8(self):
        text = card("VERSION:3.0", "FN:File Test", "EMAIL:f@t.co") + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.vcf"
            path.write_text(text, encoding="utf-8")
            (c,) = parse_file(path)
            self.assertEqual(c.display_name, "File Test")
            self.assertEqual(str(c.source), str(path))

    def test_bom_tolerated(self):
        text = card("VERSION:3.0", "FN:BOM", "TEL:1") + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.vcf"
            path.write_text(text, encoding="utf-8-sig")
            (c,) = parse_file(path)
            self.assertEqual(c.display_name, "BOM")


class TestContactHelpers(unittest.TestCase):
    def test_searchable_covers_fields(self):
        (c,) = parse_vcards(card(
            "VERSION:3.0", "FN:Sam", "ORG:Initech", "TEL:999", "EMAIL:s@i.co"))
        for needle in ("sam", "initech", "999", "s@i.co"):
            self.assertIn(needle, c.searchable())

    def test_subtitle_prefers_org(self):
        (c,) = parse_vcards(card(
            "VERSION:3.0", "FN:S", "ORG:Org", "EMAIL:s@i.co", "TEL:1"))
        self.assertEqual(c.subtitle(), "Org")

    def test_subtitle_falls_back(self):
        (c,) = parse_vcards(card("VERSION:3.0", "FN:S", "EMAIL:s@i.co"))
        self.assertEqual(c.subtitle(), "s@i.co")
        (c,) = parse_vcards(card("VERSION:3.0", "FN:S", "TEL:1"))
        self.assertEqual(c.subtitle(), "1")
        (c,) = parse_vcards(card("VERSION:3.0", "FN:S"))
        self.assertEqual(c.subtitle(), "")

    def test_to_text(self):
        (c,) = parse_vcards(card(
            "VERSION:3.0", "FN:T", "TITLE:Dev", "ORG:Org",
            "TEL;TYPE=CELL:1", "EMAIL:e@x.io"))
        text = c.to_text()
        for needle in ("T", "Dev", "Org", "Cell: 1", "e@x.io"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
