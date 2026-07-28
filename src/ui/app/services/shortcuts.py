"""Configurable keyboard-shortcut service.

Maps abstract action names to Tk key-sequence strings.  The shell binds
every action globally; when a key fires, we dispatch to whichever page
is currently active — pages that don't handle a given action simply
ignore it.

The bindings persist in `user_data/ui_settings.json` under the key
`shortcuts` as `{action: keysequence}`.  Missing entries fall back to
the defaults defined below.
"""

from __future__ import annotations

from typing import Callable

from src.ui.app import settings as user_settings


# ---------------------------------------------------------------------------
# Actions we recognise.  Each has:
#   - a default key-sequence (Tk syntax; e.g. "<Control-r>", "<Escape>")
#   - an i18n key for the display label in Settings
# ---------------------------------------------------------------------------

ACTIONS: tuple[str, ...] = ("run", "save", "load", "cancel")

DEFAULT_BINDINGS: dict[str, str] = {
    "run":    "<Control-r>",
    "save":   "<Control-s>",
    "load":   "<Control-o>",
    "cancel": "<Escape>",
}

ACTION_LABEL_KEYS: dict[str, str] = {
    "run":    "shortcut.run",
    "save":   "shortcut.save",
    "load":   "shortcut.load",
    "cancel": "shortcut.cancel",
}


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def load_bindings() -> dict[str, str]:
    """Return the current bindings, with defaults merged in for any
    action the user hasn't overridden."""
    stored = user_settings.get("shortcuts", {}) or {}
    if not isinstance(stored, dict):
        stored = {}
    merged = dict(DEFAULT_BINDINGS)
    for action, seq in stored.items():
        if action in DEFAULT_BINDINGS and isinstance(seq, str) and seq:
            merged[action] = seq
    return merged


def save_bindings(bindings: dict[str, str]) -> None:
    """Persist bindings to ui_settings.json.  Only keys in ACTIONS are kept."""
    s = user_settings.load_settings()
    cleaned = {a: seq for a, seq in bindings.items()
               if a in DEFAULT_BINDINGS and isinstance(seq, str) and seq}
    s["shortcuts"] = cleaned
    user_settings.save_settings(s)


# ---------------------------------------------------------------------------
# Tk binding
# ---------------------------------------------------------------------------

class ShortcutRouter:
    """Owns the bind_all calls on a root window.  Rebind on demand
    (e.g. after the user edits Settings)."""

    def __init__(self, root, dispatch: Callable[[str], None]) -> None:
        self._root = root
        self._dispatch = dispatch
        self._current: dict[str, str] = {}
        self.rebind(load_bindings())

    def rebind(self, bindings: dict[str, str]) -> None:
        # Unbind whatever we had before so old sequences don't linger.
        for _, seq in self._current.items():
            try:
                self._root.unbind_all(seq)
            except Exception:
                pass
        self._current = dict(bindings)
        for action, seq in bindings.items():
            try:
                self._root.bind_all(seq,
                                     lambda _e, a=action: self._fire(a),
                                     add="+")
            except Exception:
                # Malformed sequences shouldn't crash the app.
                pass

    def _fire(self, action: str) -> None:
        try:
            self._dispatch(action)
        except Exception:
            # Router must never break the app.
            pass


# ---------------------------------------------------------------------------
# Pretty rendering
# ---------------------------------------------------------------------------

def humanize(seq: str) -> str:
    """Turn a Tk key-sequence like '<Control-Shift-r>' into 'Ctrl+Shift+R'."""
    if not seq:
        return ""
    inner = seq.strip("<>")
    parts = inner.split("-")
    pretty_parts: list[str] = []
    for p in parts:
        pl = p.lower()
        if pl == "control":
            pretty_parts.append("Ctrl")
        elif pl == "shift":
            pretty_parts.append("Shift")
        elif pl in ("alt", "meta"):
            pretty_parts.append(pl.capitalize())
        elif pl == "escape":
            pretty_parts.append("Esc")
        elif pl == "return":
            pretty_parts.append("Enter")
        elif len(p) == 1:
            pretty_parts.append(p.upper())
        else:
            pretty_parts.append(p.capitalize())
    return "+".join(pretty_parts)


def parse_event(event) -> str:
    """Turn a Tk KeyPress event into a canonical <...> sequence string.

    Used by the Settings 'rebind' dialog to capture whatever the user
    pressed and store it in the same syntax Tk's bind() expects.
    Ignores lone modifier presses (Ctrl / Shift / Alt) — the caller
    should only lock in when a non-modifier key follows.
    """
    keysym = event.keysym
    if keysym in (
        "Control_L", "Control_R",
        "Shift_L", "Shift_R",
        "Alt_L", "Alt_R", "Meta_L", "Meta_R",
    ):
        return ""

    state = int(event.state)
    parts: list[str] = []
    if state & 0x0004:
        parts.append("Control")
    if state & 0x0001:
        parts.append("Shift")
    if state & 0x0008 or state & 0x0080:
        parts.append("Alt")

    # Normalize letter keysyms to lowercase (Tk convention for
    # <Control-x>) so bindings stay case-insensitive from the user's
    # POV.  For non-letter keys keep the original keysym.
    if len(keysym) == 1 and keysym.isalpha():
        parts.append(keysym.lower())
    else:
        parts.append(keysym)

    return "<" + "-".join(parts) + ">"
