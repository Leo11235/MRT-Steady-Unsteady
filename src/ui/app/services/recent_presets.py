"""
Recently-loaded presets, remembered across sessions.

Stored in user_data/ui_settings.json under "recent_presets", one list per
simulator, newest first:

    {"steady": ["C:/.../steady_example.jsonc", ...], "unsteady": [...]}

Paths that no longer exist are filtered out on read rather than on write, so
moving a file doesn't corrupt the list and a file that comes back reappears
where it was. That matters here: presets live in a folder people reorganise,
and a stale list of dead paths is worse than no list.
"""

from __future__ import annotations

from pathlib import Path

from src.ui.app import settings as user_settings

MAX_RECENT = 10

_KINDS = ("steady", "unsteady")


def _all() -> dict:
    stored = user_settings.get("recent_presets", {}) or {}
    if not isinstance(stored, dict):
        return {}
    return stored


def recent(kind: str, *, existing_only: bool = True) -> list[Path]:
    """Recent presets for "steady" or "unsteady", newest first.

    Filters out anything that's been moved or deleted, unless asked not to.
    """
    raw = _all().get(kind, [])
    if not isinstance(raw, list):
        return []
    paths = []
    for entry in raw:
        try:
            path = Path(entry)
        except (TypeError, ValueError):
            continue
        if not existing_only or path.exists():
            paths.append(path)
    return paths[:MAX_RECENT]


def remember(kind: str, path: Path) -> None:
    """Push a preset to the front of the list.

    Re-loading something already in the list moves it up rather than
    duplicating it.
    """
    if kind not in _KINDS:
        return
    resolved = str(Path(path).resolve())

    stored = _all()
    existing = [p for p in stored.get(kind, []) if isinstance(p, str)]
    existing = [p for p in existing if str(Path(p)) != str(Path(resolved))]
    stored[kind] = [resolved] + existing[:MAX_RECENT - 1]

    settings = user_settings.load_settings()
    settings["recent_presets"] = stored
    user_settings.save_settings(settings)


def forget(kind: str, path: Path) -> None:
    """Drop one entry, for when a load fails and the file is clearly bad."""
    stored = _all()
    target = str(Path(path).resolve())
    stored[kind] = [p for p in stored.get(kind, [])
                    if isinstance(p, str) and str(Path(p).resolve()) != target]
    settings = user_settings.load_settings()
    settings["recent_presets"] = stored
    user_settings.save_settings(settings)


def clear(kind: str | None = None) -> None:
    """Empty one list, or all of them."""
    stored = _all()
    for k in ([kind] if kind else list(_KINDS)):
        stored[k] = []
    settings = user_settings.load_settings()
    settings["recent_presets"] = stored
    user_settings.save_settings(settings)


def prune() -> int:
    """Drop every path that no longer exists. Returns how many went.

    Called at startup so the stored list doesn't grow a tail of dead entries
    from folders that have been reorganised.
    """
    stored = _all()
    removed = 0
    for kind in _KINDS:
        before = [p for p in stored.get(kind, []) if isinstance(p, str)]
        after = [p for p in before if Path(p).exists()]
        removed += len(before) - len(after)
        stored[kind] = after
    if removed:
        settings = user_settings.load_settings()
        settings["recent_presets"] = stored
        user_settings.save_settings(settings)
    return removed
