"""HelpIcon — a small circled '?' label with a hover tooltip.

Drop-in helper for anywhere in the UI where a bit of context would
help but a full paragraph would clutter the layout.  Uses the shared
Tooltip widget for the popup, so it fades in on hover after a short
delay and dismisses on cursor-leave.

Usage:
    HelpIcon(parent, "SI = SI units; IMP = imperial; MRT = MRT mix.")
        .pack(side="left", padx=(2, 0))
"""

from __future__ import annotations

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app.widgets.tooltip import Tooltip


class HelpIcon(ctk.CTkLabel):
    """Small circled '?' with a hover-triggered explanatory tooltip.

    The Unicode 'ⓘ' (circled 'i') would also work but 'ⓘ'/'❓' render
    inconsistently across Windows/macOS/Linux emoji fallbacks.
    A boxed '?' from Segoe UI Symbol / DejaVu Sans is reliable on
    every platform, so we go with that.
    """

    def __init__(self, master, help_text: str) -> None:
        super().__init__(
            master,
            text=" ? ",
            width=20, height=20,
            corner_radius=10,
            fg_color=theme.CARD_BG,
            text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL, weight="bold"),
        )
        # The tooltip does the heavy lifting on hover.
        Tooltip(self, help_text)
