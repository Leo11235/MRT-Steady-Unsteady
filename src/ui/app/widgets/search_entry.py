"""SearchEntry — a text entry with a leading 🔍 icon and a trailing ✕
clear button.  Used at the top of both results pages.

Reads and writes a caller-supplied StringVar so existing trace_add
wiring on that var (used to fire the filter) keeps working with a
one-line change at the call site.
"""

from __future__ import annotations

import customtkinter as ctk

from src.ui.app import theme


class SearchEntry(ctk.CTkFrame):
    def __init__(self, master, *, textvariable: ctk.StringVar,
                 placeholder: str = "") -> None:
        super().__init__(master, fg_color="transparent")

        # ---- 🔍 leading icon ------------------------------------------
        ctk.CTkLabel(
            self, text="🔍",
            width=28, anchor="e",
            text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_H2),
        ).pack(side="left", padx=(0, theme.PAD_XS))

        # ---- entry -----------------------------------------------------
        self._var = textvariable
        self._entry = ctk.CTkEntry(
            self, textvariable=self._var,
            placeholder_text=placeholder,
        )
        self._entry.pack(side="left", fill="x", expand=True)

        # ---- ✕ trailing clear button ----------------------------------
        # Round transparent button that only shows when there's text.
        self._clear_btn = ctk.CTkButton(
            self, text="✕",
            width=28, height=28, corner_radius=14,
            fg_color="transparent",
            text_color=theme.TEXT_MUTED,
            hover_color=theme.CARD_HOVER,
            command=self._clear,
        )
        # Not packed initially — we bring it in on first keystroke.
        self._var.trace_add("write", lambda *_: self._sync_clear_visibility())
        self._sync_clear_visibility()

    # ------------------------------------------------------------------

    def _clear(self) -> None:
        self._var.set("")
        # After clearing, return focus to the entry so the user can
        # keep typing immediately.
        self._entry.focus_set()

    def _sync_clear_visibility(self) -> None:
        has_text = bool(self._var.get())
        if has_text:
            if not self._clear_btn.winfo_ismapped():
                self._clear_btn.pack(side="right", padx=(theme.PAD_XS, 0))
        else:
            if self._clear_btn.winfo_ismapped():
                self._clear_btn.pack_forget()
