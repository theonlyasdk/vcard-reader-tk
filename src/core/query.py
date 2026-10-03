"""Pure contact filtering and sorting (no UI, no I/O)."""

from __future__ import annotations

TYPE_FILTERS = (
    "All",
    "Has phone",
    "Has email",
    "Has address",
    "Has organisation",
)

SORT_OPTIONS = (
    "Name A–Z",
    "Name Z–A",
    "First name",
    "Last name",
    "Organisation",
    "Email",
)


def filter_contacts(contacts: list, query: str = "", kind: str = "All") -> list:
    """Return contacts matching a search query and a type filter."""
    items = list(contacts)
    query = (query or "").strip().lower()
    if query:
        items = [c for c in items if query in c.searchable()]
    if kind == "Has phone":
        items = [c for c in items if c.phones]
    elif kind == "Has email":
        items = [c for c in items if c.emails]
    elif kind == "Has address":
        items = [c for c in items if c.addresses]
    elif kind == "Has organisation":
        items = [c for c in items if c.organisation]
    return items


def sort_contacts(contacts: list, sort: str = "Name A–Z") -> list:
    """Return contacts in the requested order (input untouched)."""
    if sort == "Name Z–A":
        return sorted(contacts, key=lambda c: c.display_name.lower(), reverse=True)
    if sort == "First name":
        return sorted(contacts, key=lambda c: (
            not c.first_name, c.first_name.lower(), c.display_name.lower()))
    if sort == "Last name":
        return sorted(contacts, key=lambda c: (
            not c.last_name, c.last_name.lower(), c.display_name.lower()))
    if sort == "Organisation":
        return sorted(contacts,
                      key=lambda c: (c.organisation.lower(), c.display_name.lower()))
    if sort == "Email":
        return sorted(contacts, key=lambda c: (
            c.emails[0][1].lower() if c.emails else "\uffff",
            c.display_name.lower()))
    return sorted(contacts, key=lambda c: c.display_name.lower())
