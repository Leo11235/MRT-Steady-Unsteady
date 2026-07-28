"""Tooltip helper.

Attach a hover-triggered tooltip to any Tk widget:

    Tooltip(entry, "Chamber stagnation pressure; typical 20–40 bar.")

The tooltip appears after a short delay to avoid flicker while the
cursor is just moving through the widget, and disappears when the
cursor leaves or the widget is destroyed.

Implementation is a plain top-level Tk window (borderless, always on
top).  We don't use customtkinter for the popup because we want it as
lightweight as possible — hundreds of these can exist in a form and
they should cost nothing until hovered.
"""

from __future__ import annotations

import tkinter as tk

from src.ui.app import theme


class Tooltip:
    """Attach an on-hover tooltip to `widget`."""

    _DELAY_MS = 450         # cursor must sit on the widget for this long
    _WRAP_PX  = 320         # max width before wrap

    def __init__(self, widget, text: str) -> None:
        self._widget = widget
        self._text   = text
        self._tip: tk.Toplevel | None = None
        self._after_id: str | None = None

        widget.bind("<Enter>",   self._schedule, add="+")
        widget.bind("<Leave>",   self._hide,     add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide,     add="+")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_text(self, text: str) -> None:
        """Change the tooltip text (in case the label is retranslated)."""
        self._text = text

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _schedule(self, _event=None) -> None:
        self._cancel_pending()
        self._after_id = self._widget.after(self._DELAY_MS, self._show)

    def _cancel_pending(self) -> None:
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        if self._tip is not None or not self._text:
            return
        try:
            x = self._widget.winfo_rootx() + 12
            y = self._widget.winfo_rooty() + self._widget.winfo_height() + 6
        except Exception:
            return
        tip = tk.Toplevel(self._widget)
        # Borderless, always-on-top; doesn't steal focus.
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        try:
            tip.attributes("-topmost", True)
        except Exception:
            pass
        # Plain Tk Label instead of CTkLabel — cheaper for something
        # that flickers in and out often.
        lbl = tk.Label(
            tip, text=self._text,
            justify="left",
            background="#232326",
            foreground="#f0f0f0",
            wraplength=self._WRAP_PX,
            padx=8, pady=6,
            borderwidth=1, relief="solid",
            font=("TkDefaultFont", theme.SIZE_SMALL),
        )
        lbl.pack()
        self._tip = tip

    def _hide(self, _event=None) -> None:
        self._cancel_pending()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None
