"""Tooltip helper.

Attach a hover-triggered tooltip to any Tk widget:

    Tooltip(entry, "Chamber stagnation pressure; typical 20–40 bar.")

The tooltip appears after a short delay to avoid flicker while the
cursor is just moving through the widget, and disappears when the
cursor leaves or the widget is destroyed.

It also keeps itself inside the app window: a tooltip on a widget near
the right edge grows leftwards from that widget instead of running off,
and one near the bottom flips above it.  It always stays touching the
widget it belongs to.  See _place().

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

    _DELAY_MS  = 450        # cursor must sit on the widget for this long
    _WRAP_PX   = 320        # max width before wrap
    _MARGIN_PX = 8          # closest the tooltip gets to a screen edge

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
            anchor_x = self._widget.winfo_rootx()
            anchor_y = self._widget.winfo_rooty()
            anchor_w = self._widget.winfo_width()
            anchor_h = self._widget.winfo_height()
        except Exception:
            return

        tip = tk.Toplevel(self._widget)
        # Borderless, always-on-top; doesn't steal focus.
        tip.wm_overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except Exception:
            pass
        # Build it off-screen so the user never sees it at the wrong place.
        # Placing it correctly needs its size, and its size needs it laid out.
        tip.wm_geometry("+-4000+-4000")

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
        self._place(tip, anchor_x, anchor_y, anchor_w, anchor_h)

    def _bounds(self) -> tuple[int, int, int, int]:
        """The rectangle the tooltip has to stay inside, as (left, top, right,
        bottom) in root coordinates.

        This is the APP WINDOW, not the screen. Two reasons. It's what the
        complaint is actually about — text disappearing off the edge of the UI
        — and screen metrics can't be trusted to share a coordinate space with
        winfo_rootx() once Windows display scaling is involved, which is how an
        earlier version of this ended up parking tooltips in the middle of the
        page. Both numbers here come from the same widget tree, so they agree.
        """
        try:
            top_level = self._widget.winfo_toplevel()
            left = top_level.winfo_rootx()
            top = top_level.winfo_rooty()
            return (left, top,
                    left + top_level.winfo_width(),
                    top + top_level.winfo_height())
        except Exception:
            try:
                return (0, 0,
                        self._widget.winfo_screenwidth(),
                        self._widget.winfo_screenheight())
            except Exception:
                return (0, 0, 1920, 1080)

    def _place(self, tip, anchor_x: int, anchor_y: int,
               anchor_w: int, anchor_h: int) -> None:
        """Position the tooltip so it touches its widget and stays in bounds.

        Preferred spot is just below and slightly right of the widget. If that
        would run past the right edge, the tooltip is RIGHT-ALIGNED to the
        widget instead — it grows leftwards from the icon rather than being
        flung against the window edge, so it stays visibly attached to the
        thing you're hovering. Same idea vertically: it flips above.

        Costs one update_idletasks() per hover — a few hundred microseconds
        for a widget that only exists while the cursor is resting.
        """
        try:
            tip.update_idletasks()
            width = tip.winfo_reqwidth()
            height = tip.winfo_reqheight()
        except Exception:
            return

        left, top, right, bottom = self._bounds()

        # ---- horizontal ------------------------------------------------
        x = anchor_x + 12
        if x + width > right - self._MARGIN_PX:
            # Hang it off the widget's right edge, extending left.
            x = anchor_x + anchor_w - width
        x = max(left + self._MARGIN_PX, min(x, right - width - self._MARGIN_PX))

        # ---- vertical --------------------------------------------------
        y = anchor_y + anchor_h + 6
        if y + height > bottom - self._MARGIN_PX:
            above = anchor_y - height - 6
            # Only flip if there's genuinely room up there; a tooltip taller
            # than the window should show its first line rather than its last.
            y = above if above >= top + self._MARGIN_PX else top + self._MARGIN_PX

        try:
            tip.wm_geometry(f"+{int(x)}+{int(y)}")
        except Exception:
            pass

    def _hide(self, _event=None) -> None:
        self._cancel_pending()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None
