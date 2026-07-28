"""GraphPicker — modal for choosing which plots to open.

Replaces the previous "Show select graphs" / "Show all graphs" split
with a single "Show graphs…" button on both results pages.  Users see
a scrollable list of checkboxes, one per available plot, plus All /
None / Cancel / Show buttons at the bottom.

Usage from a page:
    from src.ui.app.widgets.graph_picker import GraphPicker
    GraphPicker(
        parent=self,
        items=[
            ("Kinematics (altitude, velocity, accel)", "kinematics", True),
            ("Thrust vs. time",                        "thrust",     True),
            ("Forces breakdown",                       "forces",     False),
        ],
        on_confirm=self._render_selected_graphs,
    )

The `on_confirm` callback receives a list of the wire-form keys of the
checked items.  It's the page's job to translate those keys into
matplotlib figures.
"""

from __future__ import annotations

from typing import Callable, Iterable

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app.services import i18n


class GraphPicker(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        *,
        items: Iterable[tuple[str, str, bool]],
        on_confirm: Callable[[list[str]], None],
        title: str | None = None,
    ) -> None:
        """
        items: iterable of (pretty_label, wire_key, default_checked).
        on_confirm: called with the list of wire_keys the user ticked.
        """
        super().__init__(parent)
        self.title(title or i18n.t("graphs.picker_title"))
        # Wide enough to fit the longest labels comfortably.
        self.geometry("560x520")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.resizable(False, True)

        self._on_confirm = on_confirm
        self._vars: dict[str, ctk.BooleanVar] = {}

        # ---- header ---------------------------------------------------
        ctk.CTkLabel(
            self, text=i18n.t("graphs.picker_body"),
            font=ctk.CTkFont(size=theme.SIZE_BODY),
            anchor="w", justify="left",
            wraplength=500,
            text_color=theme.TEXT_MUTED,
        ).pack(fill="x", padx=theme.PAD_L, pady=(theme.PAD_L, theme.PAD_S))

        # ---- checkbox list (scrollable) -------------------------------
        list_wrap = ctk.CTkScrollableFrame(self, label_text="")
        list_wrap.pack(fill="both", expand=True,
                       padx=theme.PAD_L, pady=theme.PAD_S)

        for pretty, key, default in items:
            var = ctk.BooleanVar(value=bool(default))
            self._vars[key] = var
            ctk.CTkCheckBox(
                list_wrap, text=pretty, variable=var,
                font=ctk.CTkFont(size=theme.SIZE_BODY),
            ).pack(anchor="w", pady=2, fill="x")

        # ---- footer buttons -------------------------------------------
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=theme.PAD_L, pady=theme.PAD_M)

        ctk.CTkButton(
            footer, text=i18n.t("graphs.all"), width=90,
            fg_color="transparent", border_width=1,
            text_color=("gray25", "gray75"),
            command=lambda: self._set_all(True),
        ).pack(side="left")

        ctk.CTkButton(
            footer, text=i18n.t("graphs.none"), width=90,
            fg_color="transparent", border_width=1,
            text_color=("gray25", "gray75"),
            command=lambda: self._set_all(False),
        ).pack(side="left", padx=(theme.PAD_S, 0))

        ctk.CTkButton(
            footer, text=i18n.t("graphs.cancel"), width=90,
            fg_color="transparent", border_width=1,
            text_color=("gray25", "gray75"),
            command=self.destroy,
        ).pack(side="right")

        ctk.CTkButton(
            footer, text=i18n.t("graphs.show"), width=140,
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            fg_color=theme.SUCCESS,
            hover_color=theme.SUCCESS_HOVER,
            command=self._on_show_click,
        ).pack(side="right", padx=(0, theme.PAD_S))

    def _set_all(self, value: bool) -> None:
        for var in self._vars.values():
            var.set(value)

    def _on_show_click(self) -> None:
        selected = [key for key, var in self._vars.items() if var.get()]
        self.destroy()
        try:
            self._on_confirm(selected)
        except Exception:
            # Never let a consumer bug leak out of the modal
            import traceback
            traceback.print_exc()
