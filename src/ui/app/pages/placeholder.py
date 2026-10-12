"""
PlaceholderPage — stands in for a page that hasn't been written yet.

The shell resolves pages lazily by import path. When a page's module doesn't
exist, the shell substitutes one of these instead of crashing, so the app runs
end to end from the first day the shell exists and each real page simply
replaces its placeholder when it lands.

Without this, navigation couldn't be exercised until every page was finished,
which is exactly the sort of big-bang integration this rebuild is trying to
avoid.
"""

from __future__ import annotations

import customtkinter as ctk

from src.ui.app import theme


class PlaceholderPage(ctk.CTkFrame):
    """A polite 'not built yet' screen."""

    TITLE = ""

    def __init__(self, master, on_navigate, *,
                 page_name: str = "", reason: str = "") -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate
        self.TITLE = page_name.replace("_", " ").title() if page_name else "Not built yet"

        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.place(relx=0.5, rely=0.42, anchor="center")

        ctk.CTkLabel(
            wrap, text="Not built yet",
            font=ctk.CTkFont(size=theme.SIZE_TITLE, weight="bold"),
            text_color=theme.TEXT_MUTED,
        ).pack(pady=(0, theme.PAD_S))

        ctk.CTkLabel(
            wrap,
            text=f"The {self.TITLE.lower()} page arrives in a later step of the rebuild.",
            font=ctk.CTkFont(size=theme.SIZE_BODY),
            text_color=theme.TEXT_FAINT,
            wraplength=460, justify="center",
        ).pack(pady=(0, theme.PAD_M))

        if reason:
            # Shown only when the import failed for a reason other than the
            # module being absent — that's a real error worth surfacing rather
            # than hiding behind a friendly message.
            ctk.CTkLabel(
                wrap, text=reason,
                font=ctk.CTkFont(family="Consolas", size=theme.SIZE_SMALL),
                text_color=theme.ERROR,
                wraplength=460, justify="center",
            ).pack(pady=(0, theme.PAD_M))

        ctk.CTkButton(
            wrap, text="Back to menu", width=180, height=36,
            command=lambda: self.on_navigate("main"),
        ).pack()
