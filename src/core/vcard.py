"""Stdlib-only vCard parser (vCard 2.1 / 3.0 / 4.0 subset)."""

from __future__ import annotations

import quopri
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Contact:
    display_name: str = ""
    first_name: str = ""
    last_name: str = ""
    middle_name: str = ""
    prefix: str = ""
    suffix: str = ""
    organisation: str = ""
    title: str = ""
    phones: list = field(default_factory=list)      # [(label, value)]
    emails: list = field(default_factory=list)      # [(label, value)]
    addresses: list = field(default_factory=list)   # [(label, formatted)]
    urls: list = field(default_factory=list)
    birthday: str = ""
    note: str = ""
    version: str = ""
    raw: str = ""
    source: str = ""

    def searchable(self) -> str:
        parts = [self.display_name, self.organisation, self.title, self.note]
        parts += [v for _, v in self.phones]
        parts += [v for _, v in self.emails]
        parts += [v for _, v in self.addresses]
        parts += self.urls
        parts += [label for label, _ in
                  self.phones + self.emails + self.addresses if label]
        return "\n".join(parts).lower()

    def subtitle(self) -> str:
        if self.organisation:
            return self.organisation
        if self.emails:
            return self.emails[0][1]
        if self.phones:
            return self.phones[0][1]
        return ""

    def to_text(self) -> str:
        lines = [self.display_name or "(No name)"]
        if self.title or self.organisation:
            lines.append(" — ".join(p for p in (self.title, self.organisation) if p))
        for label, value in self.phones:
            lines.append(f"{label}: {value}" if label else value)
        for label, value in self.emails:
            lines.append(f"{label}: {value}" if label else value)
        for label, value in self.addresses:
            lines.append(f"{label}: {value}" if label else value)
        lines += self.urls
        if self.birthday:
            lines.append(f"Birthday: {self.birthday}")
        if self.note:
            lines.append(self.note)
        return "\n".join(lines)


@dataclass
class Issue:
    """One problem found while parsing, with a fix hint for the user."""
    source: str = ""
    line: int = 0
    problem: str = ""
    fix: str = ""


def _unescape(value: str) -> str:
    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            if nxt in ("n", "N"):
                out.append("\n")
            elif nxt == "\\":
                out.append("\\")
            elif nxt == ",":
                out.append(",")
            elif nxt == ";":
                out.append(";")
            else:
                out.append(nxt)
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _split_unescaped(text: str, sep: str) -> list:
    parts, current, escaped = [], [], False
    for ch in text:
        if escaped:
            current.append(ch)
            escaped = False
        elif ch == "\\":
            current.append(ch)
            escaped = True
        elif ch == sep:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def _decode_value(value: str, params: dict) -> str:
    """Decode vCard 2.1 style QUOTED-PRINTABLE values."""
    kinds = [e.upper() for e in params.get("ENCODING", [])]
    kinds += [t.upper() for t in params.get("TYPE", [])]
    if "QUOTED-PRINTABLE" not in kinds and "QUOTEDPRINTABLE" not in kinds:
        return value
    try:
        raw = quopri.decodestring(value.encode("ascii"))
    except Exception:
        return value
    for charset in params.get("CHARSET", []) + ["utf-8", "cp1252"]:
        try:
            return raw.decode(charset)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def _parse_line(line: str):
    """Split one content line into (prop_name, params, value)."""
    if ":" not in line:
        return None, {}, ""
    left, _, value = line.partition(":")
    segments = _split_unescaped(left, ";")
    name = segments[0].strip().upper()
    if "." in name:  # grouped property, e.g. item1.TEL
        name = name.rsplit(".", 1)[-1]
    params: dict = {}
    for seg in segments[1:]:
        if "=" in seg:
            key, _, val = seg.partition("=")
            key = key.strip().upper()
            vals = [_unescape(v.strip()) for v in _split_unescaped(val.strip(), ",")]
            params[key] = vals
        elif seg.strip():
            params.setdefault("TYPE", []).append(_unescape(seg.strip()))
    value = _decode_value(value.strip(), params)
    return name, params, value


def _type_label(params: dict) -> str:
    types = [t for t in params.get("TYPE", []) if t]
    seen, labels = set(), []
    for t in types:
        key = t.upper()
        if key in ("VOICE", "PREF") or key in seen:
            continue
        seen.add(key)
        labels.append(key.capitalize())
    return ", ".join(labels)


def _format_address(value: str) -> str:
    parts = [_unescape(p) for p in _split_unescaped(value, ";")]
    while len(parts) < 7:
        parts.append("")
    _po, _ext, street, city, region, postal, country = parts[:7]
    line1 = street.replace("\n", ", ")
    line2 = ", ".join(p for p in (city, region, postal) if p)
    return ", ".join(p for p in (line1, line2, country) if p)


def _strip_tel_uri(value: str) -> str:
    if value.lower().startswith("tel:"):
        return value[4:]
    return value


def _logical_lines(text: str) -> list:
    """Fold-aware split: returns [(start_lineno, logical_line)]."""
    out = []
    for lineno, raw_line in enumerate(
            text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), start=1):
        if raw_line[:1] in (" ", "\t") and out:
            prev_no, prev_text = out[-1]
            out[-1] = (prev_no, prev_text + raw_line[1:])
        else:
            out.append((lineno, raw_line))
    return out


def parse_with_diagnostics(text: str, source: str = "") -> tuple:
    """Parse vCard text, returning (contacts, issues).

    Issues are Issue entries with 1-based line numbers plus a fix hint,
    for files that are malformed but still (partly) readable.
    """
    # NUL bytes survive file decoding but poison native strings downstream
    # (Tcl/Tk C APIs); they carry no vCard meaning, so drop them up front.
    text = text.replace("\x00", "")

    contacts: list = []
    issues: list = []
    current: list = []
    inside = False
    start = 0

    def flush():
        if current:
            contact = _build_contact([line for _, line in current], source)
            if contact is not None:
                contacts.append(contact)

    for lineno, line in _logical_lines(text):
        upper = line.strip().upper()
        if upper == "BEGIN:VCARD":
            if inside:
                issues.append(Issue(
                    source, lineno,
                    "BEGIN:VCARD opens a new card before the previous one was closed",
                    "Close each contact with END:VCARD on its own line."))
                flush()
            inside, start, current = True, lineno, [(lineno, line)]
        elif upper == "END:VCARD":
            if not inside:
                issues.append(Issue(
                    source, lineno,
                    "END:VCARD has no matching BEGIN:VCARD",
                    "Remove this line, or add the missing BEGIN:VCARD above the contact."))
            else:
                current.append((lineno, line))
                flush()
                inside, current = False, []
        elif not inside:
            if line.strip():
                issues.append(Issue(
                    source, lineno,
                    "Text outside any vCard is ignored",
                    "Wrap each contact in BEGIN:VCARD … END:VCARD lines."))
        else:
            current.append((lineno, line))
            name, _, _ = _parse_line(line)
            if name is None and line.strip():
                issues.append(Issue(
                    source, lineno,
                    "Property line has no ':' between name and value",
                    "Write it as NAME:value, e.g. TEL:+1-555-0100."))
    if inside:
        issues.append(Issue(
            source, start,
            "Card opened here was never closed with END:VCARD",
            "Add END:VCARD on its own line at the end of the contact."))
        flush()
    return contacts, issues


def parse_vcards(text: str, source: str = "") -> list:
    """Parse vCard text into a list of Contact."""
    contacts, _ = parse_with_diagnostics(text, source)
    return contacts


def _build_contact(lines: list, source: str = "") -> Contact | None:
    contact = Contact(raw="\n".join(lines), source=source)
    has_prop = False
    for line in lines:
        name, params, value = _parse_line(line)
        if name is None:
            continue
        if name == "VERSION":
            if not contact.version:
                contact.version = value
            continue
        if name in ("BEGIN", "END", "PRODID", "REV", "UID", "CLASS",
                    "PHOTO", "LOGO", "KEY", "SOUND", "AGENT"):
            continue
        has_prop = True
        if name == "FN":
            if not contact.display_name:
                contact.display_name = _unescape(value)
        elif name == "N":
            parts = [_unescape(p) for p in _split_unescaped(value, ";")]
            while len(parts) < 5:
                parts.append("")
            last, first, middle, prefix, suffix = parts[:5]
            contact.last_name = last
            contact.first_name = first
            contact.middle_name = middle
            contact.prefix = prefix
            contact.suffix = suffix
        elif name == "ORG":
            orgs = [_unescape(p) for p in _split_unescaped(value, ";")]
            contact.organisation = " / ".join(p for p in orgs if p)
        elif name == "TITLE":
            if not contact.title:
                contact.title = _unescape(value)
        elif name in ("TEL", "PHONE"):
            number = _unescape(_strip_tel_uri(value)).strip()
            if number:
                contact.phones.append((_type_label(params), number))
        elif name == "EMAIL":
            email = _unescape(value).strip()
            if email:
                contact.emails.append((_type_label(params), email))
        elif name in ("ADR", "ADDRESS"):
            formatted = _format_address(value)
            if formatted:
                contact.addresses.append((_type_label(params), formatted))
        elif name == "URL":
            url = _unescape(value).strip()
            if url:
                contact.urls.append(url)
        elif name == "BDAY":
            contact.birthday = _unescape(value).strip()
        elif name == "NOTE":
            note = _unescape(value).strip()
            contact.note = f"{contact.note}\n{note}".strip() if contact.note else note
        elif name == "NICKNAME":
            if not contact.display_name:
                contact.display_name = _unescape(value).split(",")[0].strip()
    if not has_prop:
        return None
    if not contact.display_name:
        full = " ".join(p for p in (
            contact.prefix, contact.first_name, contact.middle_name,
            contact.last_name, contact.suffix) if p).strip()
        contact.display_name = full or contact.organisation or "(No name)"
    return contact


def parse_file(path: str | Path) -> list:
    """Read a .vcf file, trying common encodings."""
    contacts, _ = parse_file_with_issues(path)
    return contacts


def parse_file_with_issues(path: str | Path) -> tuple:
    """Read a .vcf file, returning (contacts, issues)."""
    path = Path(path)
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1252"):
        try:
            text = data.decode(encoding)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    return parse_with_diagnostics(text, source=str(path))
