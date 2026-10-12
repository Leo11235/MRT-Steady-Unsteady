"""
Keyboard shortcuts: abstract actions bound to key sequences.

The shell binds every action globally and dispatches to whichever page is
visible. Pages that don't care about an action ignore it. That keeps the
binding table in one place instead of scattered across pages, and means
rebinding a key doesn't require touching any page.

Bindings live in user_data/ui_settings.json under "shortcuts", as
{action: sequence} in Tk's own syntax. Anything the user hasn't overridden
falls back to the defaults below.
"""

from __future__ import annotations

from typing import Callable

from src.ui.app import settings as user_settings


# The actions the app recognises. Pages opt in by handling the ones they care
# about in handle_shortcut(); "cancel" is handled centrally by the shell.
ACTIONS: tuple[str, ...] = ("run", "save", "load", "cancel")

DEFAULT_BINDINGS: dict[str, str] = {
    "run":    "<Control-r>",
    "save":   "<Control-s>",
    "load":   "<Control-o>",
    "cancel": "<Escape>",
}

ACTION_LABELS: dict[str, str] = {
    "run":    "Run simulation",
    "save":   "Save preset",
    "load":   "Load preset",
    "cancel": "Cancel run",
}


# =============================================================================
# Persistence
# =============================================================================

def load_bindings() -> dict[str, str]:
    """Current bindings, with defaults filled in for anything unset."""
    stored = user_settings.get("shortcuts", {}) or {}
    if not isinstance(stored, dict):
        stored = {}
    merged = dict(DEFAULT_BINDINGS)
    for action, sequence in stored.items():
        if action in DEFAULT_BINDINGS and isinstance(sequence, str) and sequence:
            merged[action] = sequence
    return merged


def save_bindings(bindings: dict[str, str]) -> None:
    """Persist bindings, discarding anything that isn't a known action."""
    settings = user_settings.load_settings()
    settings["shortcuts"] = {
        action: sequence for action, sequence in bindings.items()
        if action in DEFAULT_BINDINGS and isinstance(sequence, str) and sequence
    }
    user_settings.save_settings(settings)


# =============================================================================
# Binding
# =============================================================================

class ShortcutRouter:
    """Owns the bind_all calls on the root window."""

    def __init__(self, root, dispatch: Callable[[str], None]) -> None:
        self._root = root
        self._dispatch = dispatch
        self._bound: dict[str, str] = {}
        self.rebind(load_bindings())

    def rebind(self, bindings: dict[str, str]) -> None:
        """Replace every binding. Safe to call repeatedly."""
        for sequence in self._bound.values():
            try:
                self._root.unbind_all(sequence)
            except Exception:                   # noqa: BLE001
                pass

        self._bound = dict(bindings)
        for action, sequence in bindings.items():
            try:
                self._root.bind_all(
                    sequence, lambda _e, a=action: self._fire(a), add="+")
            except Exception:                   # noqa: BLE001
                # A malformed sequence in a hand-edited settings file
                # shouldn't stop the app from starting.
                pass

    def _fire(self, action: str) -> None:
        try:
            self._dispatch(action)
        except Exception:                       # noqa: BLE001
            pass    # a shortcut must never be able to break the app


# =============================================================================
# Display
# =============================================================================

def humanize(sequence: str) -> str:
    """'<Control-Shift-r>' -> 'Ctrl+Shift+R', for the settings page."""
    if not sequence:
        return ""
    pretty = []
    for part in sequence.strip("<>").split("-"):
        lowered = part.lower()
        if lowered == "control":
            pretty.append("Ctrl")
        elif lowered == "shift":
            pretty.append("Shift")
        elif lowered in ("alt", "meta"):
            pretty.append(lowered.capitalize())
        elif lowered == "escape":
            pretty.append("Esc")
        elif lowered == "return":
            pretty.append("Enter")
        elif len(part) == 1:
            pretty.append(part.upper())
        else:
            pretty.append(part.capitalize())
    return "+".join(pretty)


def parse_event(event) -> str:
    """Turn a key press into the '<...>' syntax Tk's bind() expects.

    Used by the rebind dialog. Returns "" for a lone modifier press, since
    Ctrl on its own isn't a shortcut — the caller should keep listening until
    a real key arrives.
    """
    keysym = event.keysym
    if keysym in ("Control_L", "Control_R", "Shift_L", "Shift_R",
                  "Alt_L", "Alt_R", "Meta_L", "Meta_R"):
        return ""

    state = int(event.state)
    parts: list[str] = []
    if state & 0x0004:
        parts.append("Control")
    if state & 0x0001:
        parts.append("Shift")
    if state & 0x0008 or state & 0x0080:
        parts.append("Alt")

    # Tk wants lowercase letters in sequences (<Control-r>, not <Control-R>),
    # otherwise Shift becomes implicit and the binding misses.
    parts.append(keysym.lower() if len(keysym) == 1 and keysym.isalpha() else keysym)
    return "<" + "-".join(parts) + ">"
