"""Core vCard logic (no UI)."""

from .query import SORT_OPTIONS, TYPE_FILTERS, filter_contacts, sort_contacts
from .state import MAX_RECENT, load_state, save_state, state_path
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
    "MAX_RECENT",
    "SORT_OPTIONS",
    "TYPE_FILTERS",
    "filter_contacts",
    "load_state",
    "parse_file",
    "parse_file_with_issues",
    "parse_vcards",
    "parse_with_diagnostics",
    "save_state",
    "sort_contacts",
    "state_path",
]
