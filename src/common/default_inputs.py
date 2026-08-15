"""
Loader for static_data/default_inputs.jsonc.

Kept separate from the UI so the defaults are data rather than code, and so the
backend can read the same values if it ever needs them. See the comments in the
.jsonc for what each value is and where it comes from.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

_FILE = Path(__file__).resolve().parent / "static_data" / "default_inputs.jsonc"

_cache: Optional[dict] = None


def _load() -> dict:
    global _cache
    if _cache is None:
        text = _FILE.read_text(encoding="utf-8")
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
        _cache = json.loads(text)
    return _cache


def defaults_for(kind: str) -> dict:
    """Every default for "steady" or "unsteady", as {key: [value, unit]}."""
    return dict(_load().get(kind, {}))


def default_for(key: str) -> Any:
    """The default for one key, or None if it hasn't got one.

    Searches both simulators, since keys are unique across the two.
    """
    for block in _load().values():
        if key in block:
            return block[key]
    return None


def has_default(key: str) -> bool:
    return default_for(key) is not None
