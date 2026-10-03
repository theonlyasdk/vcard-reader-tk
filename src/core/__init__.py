"""Core vCard logic (no UI)."""

from .query import SORT_OPTIONS, TYPE_FILTERS, filter_contacts, sort_contacts
from .vcard import Contact, parse_file, parse_vcards

__all__ = [
    "Contact",
    "SORT_OPTIONS",
    "TYPE_FILTERS",
    "filter_contacts",
    "parse_file",
    "parse_vcards",
    "sort_contacts",
]
