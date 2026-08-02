"""Results browser — pick a saved simulation JSON (steady or unsteady),
optionally rename/delete it, then open the corresponding results page.

Left pane: two collapsible sections (Steady, Unsteady) with the runs
inside each.  Selected run is drawn with a subtle darker background.
Right pane: filename + size, and Open / Rename / Delete buttons.
"""

from __future__ import annotations

import json
from pathlib import Path
from tkinter import messagebox, simpledialog

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app import backend_bridge
from src.ui.app.services import i18n


# How long the "Confirm delete" state sticks around before reverting
# to a plain "Delete" button.
_CONFIRM_DELETE_TIMEOUT_MS = 3000


class ResultsBrowserPage(ctk.CTkFrame):
    TITLE = "Browse saved results"

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate

        # Selection state — (kind, Path) where kind ∈ {"steady", "unsteady"}
        self._selected: tuple[str, Path] | None = None

        # Collapsible-section state — each header can hide its list.
        self._expanded: dict[str, bool] = {"steady": True, "unsteady": True}

        # Cached row widgets, per kind, so click-highlight can be
        # applied by iterating them.
        self._row_widgets: dict[str, list[tuple[Path, ctk.CTkFrame]]] = {
            "steady": [], "unsteady": [],
        }

        # Delete-button state machine.
        self._delete_state: str = "idle"      # 'idle' | 'confirm'
        self._delete_reset_after_id: str | None = None

        self._build()

    # ----------------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------------

    def on_show(self) -> None:
        """Refresh the file list on every entry so new saves show up."""
        self._refresh_list()

    # ----------------------------------------------------------------------
    # Build
    # ----------------------------------------------------------------------

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1, minsize=380)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # ---- list pane -----------------------------------------------
        list_pane = ctk.CTkScrollableFrame(
            self, label_text=i18n.t("browser.list_header"),
        )
        list_pane.grid(row=0, column=0, sticky="nsew",
                       padx=(theme.PAD_M, theme.PAD_S), pady=theme.PAD_M)
        self._list_pane = list_pane

        # ---- detail pane ---------------------------------------------
        detail = ctk.CTkFrame(self)
        detail.grid(row=0, column=1, sticky="nsew",
                    padx=(theme.PAD_S, theme.PAD_M), pady=theme.PAD_M)
        self._detail = detail

        self._selected_label = ctk.CTkLabel(
            detail, text=i18n.t("browser.no_selection"),
            font=ctk.CTkFont(size=theme.SIZE_H2),
            anchor="w", justify="left",
            wraplength=520,
        )
        self._selected_label.pack(fill="x", padx=theme.PAD_M,
                                  pady=(theme.PAD_M, theme.PAD_S))

        self._meta_label = ctk.CTkLabel(
            detail, text="", anchor="w", justify="left",
            text_color=theme.TEXT_MUTED, wraplength=520,
        )
        self._meta_label.pack(fill="x", padx=theme.PAD_M,
                              pady=(0, theme.PAD_M))

        # ---- action row on the detail pane ---------------------------
        actions = ctk.CTkFrame(detail, fg_color="transparent")
        actions.pack(fill="x", padx=theme.PAD_M, pady=(0, theme.PAD_S),
                     anchor="w")

        # Open results — slate-blue accent (more contrast than the
        # previous cyan; white text stays readable).
        self._open_btn = ctk.CTkButton(
            actions, text=i18n.t("browser.open"),
            width=180, height=40,
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            fg_color=theme.ACCENT_SLATE,
            hover_color=theme.ACCENT_SLATE_HOVER,
            state="disabled",
            command=self._show_selected,
        )
        self._open_btn.pack(side="left")

        # Delete — red, two-click state machine
        self._delete_btn = ctk.CTkButton(
            actions, text=i18n.t("browser.delete"),
            width=120, height=36,
            fg_color=theme.MRT_RED_THEMED,
            hover_color=theme.MRT_RED_HOVER,
            state="disabled",
            command=self._on_delete_click,
        )
        self._delete_btn.pack(side="left", padx=(theme.PAD_S, 0))

        # Rename — outlined secondary
        self._rename_btn = ctk.CTkButton(
            actions, text=i18n.t("browser.rename"),
            width=120, height=36,
            fg_color="transparent",
            text_color=("gray25", "gray75"),
            border_width=1,
            state="disabled",
            command=self._rename_selected,
        )
        self._rename_btn.pack(side="left", padx=(theme.PAD_S, 0))

        # Show in folder — outlined secondary, matches Rename styling.
        self._reveal_btn = ctk.CTkButton(
            actions, text="Show in folder",
            width=140, height=36,
            fg_color="transparent",
            text_color=("gray25", "gray75"),
            border_width=1,
            state="disabled",
            command=self._reveal_selected,
        )
        self._reveal_btn.pack(side="left", padx=(theme.PAD_S, 0))

        # ---- inline status line under the actions --------------------
        self._status_label = ctk.CTkLabel(
            detail, text="",
            text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
            anchor="w", justify="left", wraplength=520,
        )
        self._status_label.pack(fill="x", padx=theme.PAD_M)

    # ----------------------------------------------------------------------
    # List refresh
    # ----------------------------------------------------------------------

    def _refresh_list(self) -> None:
        # Clear existing children.
        for w in self._list_pane.winfo_children():
            w.destroy()
        self._row_widgets = {"steady": [], "unsteady": []}

        steady_files   = backend_bridge.list_steady_results()
        unsteady_files = backend_bridge.list_unsteady_results()

        if not steady_files and not unsteady_files:
            ctk.CTkLabel(
                self._list_pane,
                text=i18n.t("browser.empty"),
                text_color=theme.TEXT_MUTED,
                justify="center",
            ).pack(padx=theme.PAD_M, pady=theme.PAD_L)
            # Also clear the detail pane if what we had selected no
            # longer exists.
            if self._selected is not None and not self._selected[1].exists():
                self._selected = None
                self._refresh_detail()
            return

        # ---- Steady section ------------------------------------------
        self._build_section("steady", i18n.t("browser.section_steady"),
                            steady_files)

        # A little gap between the two sections.
        ctk.CTkFrame(self._list_pane, height=8,
                     fg_color="transparent").pack()

        # ---- Unsteady section ----------------------------------------
        self._build_section("unsteady", i18n.t("browser.section_unsteady"),
                            unsteady_files)

        # If the previously-selected file was deleted underfoot, clear.
        if self._selected is not None and not self._selected[1].exists():
            self._selected = None
        self._refresh_detail()

    def _build_section(self, kind: str, title: str,
                       files: list[Path]) -> None:
        """One collapsible section: clickable header + list of rows."""
        expanded = self._expanded.get(kind, True)
        chev = "▼" if expanded else "▶"
        count = len(files)

        header = ctk.CTkButton(
            self._list_pane,
            text=f"{chev}  {title}   ({count})",
            anchor="w",
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            fg_color="transparent",
            text_color=("gray10", "gray90"),
            hover_color=theme.CARD_HOVER,
            command=lambda k=kind: self._toggle_section(k),
        )
        header.pack(fill="x", padx=theme.PAD_XS, pady=(theme.PAD_XS, 2))

        if not expanded:
            return

        if not files:
            ctk.CTkLabel(
                self._list_pane,
                text=i18n.t("browser.section_empty"),
                text_color=theme.TEXT_MUTED,
                font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
                anchor="w",
            ).pack(fill="x", padx=(theme.PAD_L, theme.PAD_XS),
                   pady=(0, theme.PAD_XS))
            return

        for path in files:
            self._make_row(kind, path)

    def _make_row(self, kind: str, path: Path) -> None:
        wrap = ctk.CTkFrame(self._list_pane, fg_color="transparent",
                            corner_radius=6)
        wrap.pack(fill="x", padx=theme.PAD_XS, pady=1)

        btn = ctk.CTkButton(
            wrap, text=path.name,
            anchor="w",
            fg_color="transparent",
            text_color=("gray10", "gray90"),
            hover_color=theme.CARD_HOVER,
            command=lambda p=path, k=kind: self._select(k, p),
        )
        btn.pack(fill="x", padx=0)

        self._row_widgets[kind].append((path, wrap))

        if self._selected is not None and self._selected == (kind, path):
            wrap.configure(fg_color=theme.CARD_BG)

    # ----------------------------------------------------------------------
    # Selection + collapse
    # ----------------------------------------------------------------------

    def _toggle_section(self, kind: str) -> None:
        self._expanded[kind] = not self._expanded.get(kind, True)
        self._refresh_list()

    def _select(self, kind: str, path: Path) -> None:
        self._selected = (kind, path)
        self._reset_delete_state()
        for k in ("steady", "unsteady"):
            for p, wrap in self._row_widgets[k]:
                if (k, p) == self._selected:
                    wrap.configure(fg_color=theme.CARD_BG)
                else:
                    wrap.configure(fg_color="transparent")
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        self._reset_delete_state()
        self._status_label.configure(text="", text_color=theme.TEXT_MUTED)
        if self._selected is None:
            self._selected_label.configure(text=i18n.t("browser.no_selection"))
            self._meta_label.configure(text="")
            self._open_btn.configure(state="disabled")
            self._rename_btn.configure(state="disabled")
            self._delete_btn.configure(state="disabled")
            self._reveal_btn.configure(state="disabled")
            return

        _kind, path = self._selected
        size_kb = path.stat().st_size / 1024 if path.exists() else 0.0
        self._selected_label.configure(text=path.name)
        self._meta_label.configure(
            text=f"{path}\n{i18n.t('browser.size_kib')}: {size_kb:,.1f} KiB",
        )
        self._open_btn.configure(state="normal")
        self._rename_btn.configure(state="normal")
        self._delete_btn.configure(state="normal")
        self._reveal_btn.configure(state="normal")

    # ----------------------------------------------------------------------
    # Open results
    # ----------------------------------------------------------------------

    def _show_selected(self) -> None:
        if self._selected is None:
            return
        kind, path = self._selected
        try:
            with open(path, "r", encoding="utf-8") as f:
                result_dict = json.load(f)
        except Exception as exc:
            self._status_label.configure(
                text=f"{type(exc).__name__}: {exc}",
                text_color=theme.ERROR,
            )
            return

        shell = self.winfo_toplevel()
        target = "steady_results" if kind == "steady" else "unsteady_results"
        try:
            results_page = shell._ensure_page(target)
            results_page.load_results(path, result_dict)
            shell.go(target)
        except Exception as exc:
            self._status_label.configure(
                text=f"{type(exc).__name__}: {exc}",
                text_color=theme.ERROR,
            )

    # ----------------------------------------------------------------------
    # Reveal in native file browser
    # ----------------------------------------------------------------------

    def _reveal_selected(self) -> None:
        if self._selected is None:
            return
        _kind, path = self._selected
        from src.ui.app.services.os_utils import reveal_in_file_explorer
        reveal_in_file_explorer(path)

    # ----------------------------------------------------------------------
    # Rename
    # ----------------------------------------------------------------------

    def _rename_selected(self) -> None:
        if self._selected is None:
            return
        _kind, path = self._selected

        new_stem = simpledialog.askstring(
            i18n.t("browser.rename_title"),
            i18n.t("browser.rename_prompt"),
            initialvalue=path.stem,
            parent=self.winfo_toplevel(),
        )
        if not new_stem:
            return
        safe = new_stem.strip().replace("/", "_").replace("\\", "_").strip(".")
        if not safe:
            self._status_label.configure(
                text=i18n.t("browser.rename_invalid"),
                text_color=theme.ERROR,
            )
            return

        new_path = path.with_name(safe + path.suffix)
        if new_path == path:
            return
        if new_path.exists():
            self._status_label.configure(
                text=i18n.t("browser.rename_exists"),
                text_color=theme.ERROR,
            )
            return

        try:
            path.rename(new_path)
        except Exception as exc:
            self._status_label.configure(
                text=f"{type(exc).__name__}: {exc}",
                text_color=theme.ERROR,
            )
            return

        self._selected = (self._selected[0], new_path)
        self._refresh_list()
        self._status_label.configure(
            text=f"{i18n.t('browser.renamed_to')} {new_path.name}",
            text_color=theme.SUCCESS,
        )

    # ----------------------------------------------------------------------
    # Delete (two-click state machine)
    # ----------------------------------------------------------------------

    def _on_delete_click(self) -> None:
        if self._selected is None:
            return
        if self._delete_state == "idle":
            self._set_delete_state("confirm")
            return
        _kind, path = self._selected
        # A single "run" is the .json file plus (optionally) a sibling
        # folder with the same stem containing the PDF/PNG bundle
        # produced by save_to_pdf / save_to_png.  Delete both so the
        # user doesn't have orphan folders piling up.
        try:
            if path.exists():
                path.unlink()
            sibling_folder = path.with_suffix("")
            if sibling_folder.is_dir():
                import shutil
                shutil.rmtree(sibling_folder, ignore_errors=True)
        except Exception as exc:
            self._status_label.configure(
                text=f"{type(exc).__name__}: {exc}",
                text_color=theme.ERROR,
            )
            self._set_delete_state("idle")
            return
        self._selected = None
        self._refresh_list()
        self._status_label.configure(
            text=f"{i18n.t('browser.deleted')} {path.name}",
            text_color=theme.SUCCESS,
        )
        self._set_delete_state("idle")

    def _set_delete_state(self, state: str) -> None:
        self._clear_delete_timeout()
        if state == "idle":
            self._delete_btn.configure(text=i18n.t("browser.delete"),
                                       width=120)
        elif state == "confirm":
            self._delete_btn.configure(text=i18n.t("browser.confirm_delete"),
                                       width=180)
            self._delete_reset_after_id = self.after(
                _CONFIRM_DELETE_TIMEOUT_MS,
                lambda: self._set_delete_state("idle"),
            )
        self._delete_state = state

    def _clear_delete_timeout(self) -> None:
        if self._delete_reset_after_id is not None:
            try:
                self.after_cancel(self._delete_reset_after_id)
            except Exception:
                pass
            self._delete_reset_after_id = None

    def _reset_delete_state(self) -> None:
        if self._delete_state != "idle":
            self._set_delete_state("idle")
