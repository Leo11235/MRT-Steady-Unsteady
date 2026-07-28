"""Little helpers for section titles, dividers, and inline notes.

Both simulation pages had their own identical copies of these — moving
them here keeps everything in one place so a design change touches one
file rather than four.
"""

from __future__ import annotations

import customtkinter as ctk

from src.ui.app import theme


def section_title(parent, text: str) -> ctk.CTkLabel:
    """A bold section title.  Packs itself; returns the widget for chaining."""
    lbl = ctk.CTkLabel(
        parent, text=text, anchor="w",
        font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
    )
    lbl.pack(fill="x", pady=(theme.PAD_S, theme.PAD_XS))
    return lbl


def divider(parent) -> ctk.CTkFrame:
    """A thin horizontal rule."""
    d = ctk.CTkFrame(parent, height=1, fg_color=theme.DIVIDER)
    d.pack(fill="x", pady=theme.PAD_S)
    return d


def note(parent, text: str, *, left_pad: int = 220 + theme.PAD_S) -> ctk.CTkLabel:
    """A grey italic informational note.  Left-padded so it visually
    aligns with the value column of the surrounding form."""
    lbl = ctk.CTkLabel(
        parent, text=text, anchor="w", justify="left",
        text_color=theme.TEXT_MUTED,
        font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
        wraplength=800,
    )
    lbl.pack(fill="x", padx=(left_pad, 0),
             pady=(theme.PAD_XS, theme.PAD_S))
    return lbl
