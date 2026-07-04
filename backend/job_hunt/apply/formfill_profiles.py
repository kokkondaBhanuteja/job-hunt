"""Load + validate declarative ATS form profiles from config/formfill/<ats>.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PROFILE_DIR = Path(__file__).resolve().parents[2] / "config" / "formfill"


def load_profile(ats: str) -> dict[str, Any] | None:
    """Return the parsed form profile for an ATS, or None if there is no profile file."""
    path = _PROFILE_DIR / f"{ats}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def validate_profile(p: dict[str, Any]) -> str | None:
    """Return an error message if the profile is malformed, else None."""
    if not isinstance(p.get("ats"), str):
        return "profile missing string 'ats'"
    fields = p.get("fields")
    if not isinstance(fields, list) or not fields:
        return "profile missing non-empty 'fields' list"
    for i, f in enumerate(fields):
        if not isinstance(f.get("selector"), str) or not isinstance(f.get("source"), str):
            return f"field[{i}] needs string 'selector' and 'source'"
    return None
