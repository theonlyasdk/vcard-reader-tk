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
    raw: str = ""
    source: str = ""

    def searchable(self) -> str:
        parts = [self.display_name, self.organisation, self.title, self.note]
        parts += [v for _, v in self.phones]
        parts += [v for _, v in self.emails]
        parts += [v for _, v in self.addresses]
        parts += self.urls
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


def parse_vcards(text: str, source: str = "") -> list:
    """Parse vCard text into a list of Contact."""
    # Unfold: lines starting with space/tab continue the previous line.
    logical = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw_line[:1] in (" ", "\t") and logical:
            logical[-1] += raw_line[1:]
        else:
            logical.append(raw_line)

    contacts: list = []
    current: list = []
    inside = False
    for line in logical:
        if line.strip().upper() == "BEGIN:VCARD":
            inside = True
            current = [line]
        elif line.strip().upper() == "END:VCARD" and inside:
            current.append(line)
            contact = _build_contact(current, source)
            if contact is not None:
                contacts.append(contact)
            inside = False
            current = []
        elif inside:
            current.append(line)
    return contacts


def _build_contact(lines: list, source: str = "") -> Contact | None:
    contact = Contact(raw="\n".join(lines), source=source)
    has_prop = False
    for line in lines:
        name, params, value = _parse_line(line)
        if name is None:
            continue
        if name in ("BEGIN", "END", "VERSION", "PRODID", "REV", "UID", "CLASS",
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
    path = Path(path)
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1252"):
        try:
            return parse_vcards(data.decode(encoding), source=str(path))
        except (UnicodeDecodeError, UnicodeError):
            continue
    return parse_vcards(data.decode("utf-8", errors="replace"), source=str(path))
