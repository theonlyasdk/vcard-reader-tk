"""Best-effort persistence of UI state (recent files, last directory).

Never raises: a broken or missing state file just yields defaults.
Tests point it at a temp file via the VCARD_READER_STATE env var.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

MAX_RECENT = 5


def _default_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", "~")).expanduser()
        return base / "ASDK" / "vcard-reader-tk" / "state.json"
    base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    return base / "vcard-reader-tk" / "state.json"


def state_path() -> Path:
    override = os.environ.get("VCARD_READER_STATE")
    return Path(override) if override else _default_path()


def load_state() -> dict:
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
        recent = [p for p in data.get("recent", []) if isinstance(p, str)]
        last_dir = data.get("last_dir", "")
        return {
            "recent": recent[:MAX_RECENT],
            "last_dir": last_dir if isinstance(last_dir, str) else "",
        }
    except Exception:
        return {"recent": [], "last_dir": ""}


def save_state(recent, last_dir="") -> None:
    try:
        path = state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"recent": list(recent)[:MAX_RECENT], "last_dir": last_dir}
        path.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass
