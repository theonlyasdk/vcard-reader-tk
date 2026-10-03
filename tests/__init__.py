"""Test bootstrap: put src/ on sys.path (mirrors vcard_reader.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
