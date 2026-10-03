"""Core vCard logic (no UI)."""

from .query import SORT_OPTIONS, TYPE_FILTERS, filter_contacts, sort_contacts
from .vcard import (
    Contact,
    Issue,
    parse_file,
    parse_file_with_issues,
    parse_vcards,
    parse_with_diagnostics,
)

__all__ = [
    "Contact",
    "Issue",
    "SORT_OPTIONS",
    "TYPE_FILTERS",
    "filter_contacts",
    "parse_file",
    "parse_file_with_issues",
    "parse_vcards",
    "parse_with_diagnostics",
    "sort_contacts",
]
