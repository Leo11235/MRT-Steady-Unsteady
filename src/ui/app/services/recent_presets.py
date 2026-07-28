"""Recent-presets tracker.

Keeps a per-kind ("steady" or "unsteady") list of the most recently
loaded / saved preset file paths, MRU-first.  Persisted to
`user_data/ui_settings.json` under the key `recent_presets` as:

    {
        "steady":   ["/abs/path/one.jsonc", "/abs/path/two.jsonc", ...],
        "unsteady": ["/abs/path/three.jsonc", ...],
    }

Files that no longer exist are pruned automatically on read, so the
dropdown never surfaces broken paths.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from src.ui.app import settings as user_settings


Kind = Literal["steady", "unsteady"]

MAX_ENTRIES = 10


def _load_all() -> dict[str, list[str]]:
    stored = user_settings.get("recent_presets", {}) or {}
    if not isinstance(stored, dict):
        return {"steady": [], "unsteady": []}
    return {
        "steady":   list(stored.get("steady",   []) or []),
        "unsteady": list(stored.get("unsteady", []) or []),
    }


def _save_all(data: dict[str, list[str]]) -> None:
    s = user_settings.load_settings()
    s["recent_presets"] = {
        "steady":   list(data.get("steady", []))[:MAX_ENTRIES],
        "unsteady": list(data.get("unsteady", []))[:MAX_ENTRIES],
    }
    user_settings.save_settings(s)


def list_recent(kind: Kind) -> list[Path]:
    """Return the recent presets for `kind`, freshest first, with any
    now-missing paths pruned (and the pruned list re-persisted)."""
    all_data = _load_all()
    raw = all_data.get(kind, []) or []
    keep: list[str] = []
    seen: set[str] = set()
    for p in raw:
        if not isinstance(p, str) or not p or p in seen:
            continue
        seen.add(p)
        if Path(p).exists():
            keep.append(p)
    # If we filtered anything out, persist the pruned list.
    if keep != raw:
        all_data[kind] = keep
        _save_all(all_data)
    return [Path(p) for p in keep]


def record(kind: Kind, path: Path) -> None:
    """Push `path` to the front of the MRU list.  De-duplicates by
    absolute-path string comparison."""
    abs_str = str(Path(path).resolve())
    all_data = _load_all()
    existing = [p for p in all_data.get(kind, []) if p != abs_str]
    all_data[kind] = ([abs_str] + existing)[:MAX_ENTRIES]
    _save_all(all_data)


def clear(kind: Kind) -> None:
    all_data = _load_all()
    all_data[kind] = []
    _save_all(all_data)
