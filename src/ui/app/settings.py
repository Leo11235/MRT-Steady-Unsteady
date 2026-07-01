"""
UI settings — load, save, reset.

Two files live in user_data/:
  - default_ui_settings.json   (committed; the baseline)
  - ui_settings.json           (per-user; gitignored; missing on first run)

Reset-to-defaults copies the former over the latter.

The settings dict is just a flat JSON object.  Add new keys by:
  1.  adding them to default_ui_settings.json,
  2.  building a widget for them in pages/settings_page.py.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from src.ui.app import backend_bridge


# =============================================================================
# Paths
# =============================================================================

def user_settings_path() -> Path:
    return backend_bridge.project_root() / "user_data" / "ui_settings.json"


def default_settings_path() -> Path:
    return backend_bridge.project_root() / "user_data" / "default_ui_settings.json"


# =============================================================================
# Built-in defaults (used only when even default_ui_settings.json is missing)
# =============================================================================

_HARDCODED_DEFAULTS = {
    "default_output_units": "SI",
}


# =============================================================================
# Load / save / reset
# =============================================================================

def load_defaults() -> dict:
    """Read the committed default settings file."""
    p = default_settings_path()
    if not p.exists():
        return dict(_HARDCODED_DEFAULTS)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # strip the "_comment_" key if present
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception:
        return dict(_HARDCODED_DEFAULTS)


def load_settings() -> dict:
    """
    Read the user-specific settings file, creating it from defaults if
    it doesn't yet exist.  Returns a fresh dict (mutating it does NOT
    write back; use save_settings).
    """
    p = user_settings_path()
    if not p.exists():
        reset_to_defaults()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    # backfill any missing keys from defaults so the schema is always complete
    merged = load_defaults()
    merged.update({k: v for k, v in data.items() if not k.startswith("_")})
    return merged


def save_settings(settings: dict) -> None:
    """Atomically write the user settings file."""
    p = user_settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: v for k, v in settings.items() if not k.startswith("_")}
    p.write_text(json.dumps(payload, indent=4), encoding="utf-8")


def reset_to_defaults() -> dict:
    """
    Restore the user settings file from defaults.  Returns the freshly
    loaded settings dict so the caller can refresh its UI.
    """
    src = default_settings_path()
    dst = user_settings_path()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.copyfile(src, dst)
    else:
        dst.write_text(json.dumps(_HARDCODED_DEFAULTS, indent=4), encoding="utf-8")
    return load_settings()


# =============================================================================
# Convenience getters / setters
# =============================================================================

def get(key: str, fallback=None):
    return load_settings().get(key, fallback)


def set(key: str, value) -> None:
    s = load_settings()
    s[key] = value
    save_settings(s)
