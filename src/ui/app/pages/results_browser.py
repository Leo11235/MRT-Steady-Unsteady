"""
Results browser — pick a saved unsteady-simulation JSON and open it
in the existing matplotlib visualizer (display_unsteady_results).

This is the one page that has a wired-up button in the skeleton: it
proves the UI → backend → matplotlib path works end-to-end.
"""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app import backend_bridge


class ResultsBrowserPage(ctk.CTkFrame):
    TITLE = "Browse saved unsteady results"

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate
        self._results: list[Path] = []
        self._selected: Path | None = None
        self._build()

    # ----------------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------------

    def on_show(self) -> None:
        """Called by the shell whenever this page becomes active.
        Refresh the list so newly-saved runs show up without an app restart."""
        self._refresh_list()

    # ----------------------------------------------------------------------
    # Build
    # ----------------------------------------------------------------------

    def _build(self) -> None:
        # Two-column layout: list of files on the left, details + actions on the right
        self.grid_columnconfigure(0, weight=1, minsize=320)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # ---- list pane ---------------------------------------------------
        list_pane = ctk.CTkScrollableFrame(self, label_text="Saved runs (newest first)")
        list_pane.grid(row=0, column=0, sticky="nsew",
                       padx=(theme.PAD_M, theme.PAD_S), pady=theme.PAD_M)
        self._list_pane = list_pane

        # ---- detail pane -------------------------------------------------
        detail = ctk.CTkFrame(self)
        detail.grid(row=0, column=1, sticky="nsew",
                    padx=(theme.PAD_S, theme.PAD_M), pady=theme.PAD_M)
        self._detail = detail

        self._selected_label = ctk.CTkLabel(
            detail, text="(no run selected)",
            font=ctk.CTkFont(size=theme.SIZE_H2),
            anchor="w", justify="left",
        )
        self._selected_label.pack(fill="x", padx=theme.PAD_M, pady=(theme.PAD_M, theme.PAD_S))

        self._meta_label = ctk.CTkLabel(
            detail, text="", anchor="w", justify="left",
            text_color=("gray30", "gray70"),
        )
        self._meta_label.pack(fill="x", padx=theme.PAD_M, pady=(0, theme.PAD_M))

        self._show_btn = ctk.CTkButton(
            detail, text="Open results",
            width=180, height=40,
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            fg_color=("#2a9d8f", "#2a9d8f"),
            hover_color=("#21867a", "#21867a"),
            state="disabled",
            command=self._show_graphs,
        )
        self._show_btn.pack(padx=theme.PAD_M, pady=theme.PAD_M, anchor="w")

        self._status_label = ctk.CTkLabel(
            detail, text="",
            text_color=("gray40", "gray60"),
            font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
            anchor="w", justify="left",
        )
        self._status_label.pack(fill="x", padx=theme.PAD_M)

    # ----------------------------------------------------------------------
    # Data
    # ----------------------------------------------------------------------

    def _refresh_list(self) -> None:
        # clear existing rows
        for w in self._list_pane.winfo_children():
            w.destroy()

        self._results = backend_bridge.list_unsteady_results()

        if not self._results:
            ctk.CTkLabel(
                self._list_pane,
                text="No saved runs found in\nuser_data/simulation_results/unsteady/",
                text_color=("gray40", "gray60"),
                justify="center",
            ).pack(padx=theme.PAD_M, pady=theme.PAD_L)
            self._selected = None
            self._refresh_detail()
            return

        for path in self._results:
            ctk.CTkButton(
                self._list_pane,
                text=path.name,
                anchor="w",
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray85", "gray25"),
                command=lambda p=path: self._select(p),
            ).pack(fill="x", padx=theme.PAD_XS, pady=1)

        # auto-select the latest
        self._select(self._results[0])

    def _select(self, path: Path) -> None:
        self._selected = path
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        if self._selected is None:
            self._selected_label.configure(text="(no run selected)")
            self._meta_label.configure(text="")
            self._show_btn.configure(state="disabled")
            return

        size_kb = self._selected.stat().st_size / 1024
        self._selected_label.configure(text=self._selected.name)
        self._meta_label.configure(
            text=f"{self._selected}\nsize: {size_kb:,.1f} KiB",
        )
        self._show_btn.configure(state="normal")
        self._status_label.configure(text="")

    # ----------------------------------------------------------------------
    # Action
    # ----------------------------------------------------------------------

    def _show_graphs(self) -> None:
        if self._selected is None:
            return
        # Load the file into the unsteady results page and navigate there.
        import json
        try:
            with open(self._selected, "r", encoding="utf-8") as f:
                result_dict = json.load(f)
        except Exception as exc:
            self._status_label.configure(
                text=f"Could not load file:\n{type(exc).__name__}: {exc}",
                text_color=("#b00020", "#ff6b6b"),
            )
            return

        shell = self.winfo_toplevel()
        try:
            results_page = shell._ensure_page("unsteady_results")
            results_page.load_results(self._selected, result_dict)
            shell.go("unsteady_results")
        except Exception as exc:
            self._status_label.configure(
                text=f"Could not open results page:\n{type(exc).__name__}: {exc}",
                text_color=("#b00020", "#ff6b6b"),
            )
