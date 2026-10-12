"""
ask_text — a styled single-line prompt.

Replaces tkinter's simpledialog.askstring, which renders as a tiny unstyled
Win32 box that ignores the app's theme entirely and is genuinely hard to read
at normal display scaling. This is the same dialog at a sensible size, in the
app's own colours.

    new_name = ask_text(self, "Rename run", "New name:", initial=current)

Returns the entered string, or None if cancelled.
"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from src.ui.app import theme


def ask_text(parent, title: str, prompt: str, *,
             initial: str = "", ok_text: str = "OK",
             width: int = 520, height: int = 240) -> Optional[str]:
    """Ask for one line of text. Returns the answer, or None if cancelled."""
    window = ctk.CTkToplevel(parent)
    window.title(title)
    window.transient(parent.winfo_toplevel())
    window.resizable(False, False)

    window.update_idletasks()
    try:
        root = parent.winfo_toplevel()
        x = root.winfo_rootx() + (root.winfo_width() - width) // 2
        y = root.winfo_rooty() + (root.winfo_height() - height) // 3
        window.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
    except Exception:                           # noqa: BLE001
        window.geometry(f"{width}x{height}")
    window.after(10, window.grab_set)

    answer: dict = {"value": None}
    var = ctk.StringVar(value=initial)

    def cancel() -> None:
        answer["value"] = None
        window.destroy()

    def confirm() -> None:
        text = var.get().strip()
        answer["value"] = text or None
        window.destroy()

    ctk.CTkLabel(window, text=title,
                 font=ctk.CTkFont(size=theme.SIZE_H1, weight="bold")).pack(
        pady=(theme.PAD_L, theme.PAD_XS))
    ctk.CTkLabel(window, text=prompt, anchor="w",
                 font=ctk.CTkFont(size=theme.SIZE_BODY),
                 text_color=theme.TEXT_MUTED).pack(
        fill="x", padx=theme.PAD_L, pady=(0, theme.PAD_XS))

    entry = ctk.CTkEntry(window, textvariable=var, height=40,
                         font=ctk.CTkFont(size=theme.SIZE_H2))
    entry.pack(fill="x", padx=theme.PAD_L, pady=(0, theme.PAD_L))

    actions = ctk.CTkFrame(window, fg_color="transparent")
    actions.pack(pady=(0, theme.PAD_L))
    ctk.CTkButton(actions, text="Cancel", width=140, height=40,
                  fg_color="transparent", border_width=1,
                  text_color=theme.TEXT_MUTED, hover_color=theme.CARD_HOVER,
                  font=ctk.CTkFont(size=theme.SIZE_BODY),
                  command=cancel).pack(side="left", padx=theme.PAD_S)
    ctk.CTkButton(actions, text=ok_text, width=140, height=40,
                  fg_color=theme.ACCENT_SLATE,
                  hover_color=theme.ACCENT_SLATE_HOVER,
                  font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold"),
                  command=confirm).pack(side="left", padx=theme.PAD_S)

    # Enter confirms, Escape cancels — what anyone would try first.
    window.bind("<Return>", lambda _e: confirm())
    window.bind("<Escape>", lambda _e: cancel())
    window.protocol("WM_DELETE_WINDOW", cancel)

    # Focus the entry with the text selected, so typing replaces the old name.
    def focus() -> None:
        try:
            entry.focus_set()
            entry.select_range(0, "end")
        except Exception:                       # noqa: BLE001
            pass
    window.after(60, focus)

    window.wait_window()
    return answer["value"]
