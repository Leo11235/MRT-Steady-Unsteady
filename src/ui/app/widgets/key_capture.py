"""
Modal that listens for one key combination and hands it back in Tk's
'<Control-r>' syntax.

Modifier-only presses are ignored (see shortcuts.parse_event), so holding Ctrl
while deciding doesn't close the dialog.
"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app.services import shortcuts

_W, _H = 460, 260


def capture_key(parent, action_label: str) -> Optional[str]:
    """Show the dialog and block until it closes.

    Returns the captured sequence, or None if the user cancelled.
    """
    window = ctk.CTkToplevel(parent)
    window.title("Rebind shortcut")
    window.geometry(f"{_W}x{_H}")
    window.resizable(False, False)
    window.transient(parent.winfo_toplevel())

    captured: dict[str, Optional[str]] = {"sequence": None}

    ctk.CTkLabel(window, text=f"Rebind “{action_label}”",
                 font=ctk.CTkFont(size=theme.SIZE_H1, weight="bold")).pack(
        pady=(theme.PAD_L, theme.PAD_S))
    ctk.CTkLabel(window, text="Press the new key combination.",
                 text_color=theme.TEXT_MUTED,
                 font=ctk.CTkFont(size=theme.SIZE_BODY)).pack()

    preview = ctk.CTkLabel(window, text="…", height=56,
                           font=ctk.CTkFont(family="Consolas",
                                            size=theme.SIZE_TITLE, weight="bold"))
    preview.pack(pady=theme.PAD_M)

    hint = ctk.CTkLabel(window, text="Esc closes without changing anything.",
                        text_color=theme.TEXT_FAINT,
                        font=ctk.CTkFont(size=theme.SIZE_SMALL))
    hint.pack()

    def close() -> None:
        try:
            window.grab_release()
        except Exception:                       # noqa: BLE001
            pass
        window.destroy()

    def on_key(event) -> str:
        sequence = shortcuts.parse_event(event)
        if not sequence:
            return "break"                      # lone modifier; keep listening

        # Escape with no modifier is the way out. Escape WITH a modifier is a
        # legitimate binding, so only the bare press cancels.
        if event.keysym == "Escape" and sequence == "<Escape>":
            captured["sequence"] = None
            close()
            return "break"

        captured["sequence"] = sequence
        preview.configure(text=shortcuts.humanize(sequence))
        # Let the user see what landed before the dialog vanishes.
        window.after(220, close)
        return "break"

    ctk.CTkButton(window, text="Cancel", width=140, height=36,
                  fg_color="transparent", border_width=1,
                  text_color=theme.TEXT_MUTED, hover_color=theme.CARD_HOVER,
                  command=close).pack(pady=(theme.PAD_M, theme.PAD_L))

    window.bind("<Key>", on_key)
    window.update_idletasks()
    _center_on(window, parent)
    try:
        window.grab_set()
    except Exception:                           # noqa: BLE001
        pass
    window.focus_force()
    window.wait_window()
    return captured["sequence"]


def _center_on(window, parent) -> None:
    top = parent.winfo_toplevel()
    try:
        x = top.winfo_rootx() + (top.winfo_width() - _W) // 2
        y = top.winfo_rooty() + (top.winfo_height() - _H) // 3
        window.geometry(f"{_W}x{_H}+{max(x, 0)}+{max(y, 0)}")
    except Exception:                           # noqa: BLE001
        pass
