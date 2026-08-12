"""
Per-user UI settings: load, save, reset.

Two files, both under user_data/:

  default_ui_settings.json    committed, read-only, the baseline
  ui_settings.json            per-user, gitignored, absent on a fresh checkout

Reset-to-defaults copies the first over the second.  Everything is a flat JSON
object, so adding a setting means adding it to default_ui_settings.json and
building a widget for it on the settings page.

Keys starting with "_" are treated as comments and stripped on both read and
write, which lets the committed defaults file document itself.
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
    """The writable per-user settings file.

    Frozen: %APPDATA%\\MRT-Steady-Unsteady\\user_data\\.
    Source: the checkout's user_data/.
    """
    return backend_bridge.project_root() / "user_data" / "ui_settings.json"


def default_settings_path() -> Path:
    """The read-only baseline that Reset restores from.  Bundled inside the exe
    when frozen, checked in at user_data/default_ui_settings.json otherwise."""
    return backend_bridge.bundled_root() / "user_data" / "default_ui_settings.json"


# =============================================================================
# Defaults
# =============================================================================
#
# Last-resort values, used only when default_ui_settings.json is missing too.
# Keep them in sync with that file; this exists so a corrupted install still
# opens rather than crashing on startup.

_HARDCODED_DEFAULTS: dict = {
    # Which unit system the results pages display in: "SI", "MRT" or "IMP".
    # Inputs carry a unit per field, so this only affects output.
    "default_output_units": "SI",
    # Run without prompting for a preset name, auto-saving instead.
    "default_auto_save_inputs": True,
    # customtkinter appearance: "light", "dark" or "system".
    "theme_appearance": "system",
    # Keyboard bindings, in Tk event syntax.
    "shortcuts": {
        "run": "<Control-r>",
        "save": "<Control-s>",
        "load": "<Control-o>",
        "cancel": "<Escape>",
    },
}


def load_defaults() -> dict:
    """Read the committed defaults file, falling back to the hardcoded set."""
    path = default_settings_path()
    if not path.exists():
        return dict(_HARDCODED_DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception:                           # noqa: BLE001
        return dict(_HARDCODED_DEFAULTS)


# =============================================================================
# Load / save / reset
# =============================================================================

def load_settings() -> dict:
    """Read the user's settings, creating the file from defaults if absent.

    Returns a fresh dict every call — mutating it does nothing on its own, pass
    it to save_settings().  Missing keys are backfilled from the defaults, so
    the returned dict always has the full set even after an upgrade adds one.
    """
    path = user_settings_path()
    if not path.exists():
        reset_to_defaults()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:                           # noqa: BLE001
        data = {}
    merged = load_defaults()
    merged.update({k: v for k, v in data.items() if not k.startswith("_")})
    return merged


def save_settings(settings: dict) -> None:
    """Write the user settings file, dropping comment keys."""
    path = user_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: v for k, v in settings.items() if not k.startswith("_")}
    path.write_text(json.dumps(payload, indent=4), encoding="utf-8")


def reset_to_defaults() -> dict:
    """Restore the user settings file from the baseline.

    Returns the freshly loaded settings so the caller can refresh its widgets.
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
# Convenience
# =============================================================================

def get(key: str, fallback=None):
    """Read one setting.  Re-reads the file, so don't call it in a tight loop."""
    return load_settings().get(key, fallback)


def set(key: str, value) -> None:      # noqa: A001 - deliberate, reads well at the call site
    """Write one setting, leaving the rest untouched."""
    settings = load_settings()
    settings[key] = value
    save_settings(settings)
