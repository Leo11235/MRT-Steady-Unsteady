"""
ResultsBrowserPage — the list of saved runs.

A list of runs on the left, details and actions on the right. Steady and
unsteady are listed separately because they open different pages and their
files have different shapes.

TWO LAYOUTS, ONE LIST
---------------------
Steady writes `<name>.json` straight into its results folder. Unsteady writes
`<name>/` holding sim_data.json plus any graphs. The bridge's run_json_path and
run_display_name paper over that, so this page never branches on which it's
looking at, and old runs from before the layout change still appear.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from src.ui.app import backend_bridge, theme
from src.ui.app.services import os_utils
from src.ui.app.widgets.confirm_button import ConfirmButton
from src.ui.app.widgets.search_entry import SearchEntry
from src.ui.app.widgets.text_prompt import ask_text

_LIST_MIN_W = 380

# The run list is the whole point of this page, so it gets read at a
# comfortable size rather than the small type used for incidental labels.
_HEADER_SIZE = theme.SIZE_TITLE     # 24
_ROW_SIZE = theme.SIZE_H2           # 16

# Every secondary action shares one size, so the row reads as a set.
_ACTION_W, _ACTION_H = 140, 36


class ResultsBrowserPage(ctk.CTkFrame):
    TITLE = "Saved results"

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate

        self._selected: Optional[Path] = None
        self._selected_kind: str = ""
        self._rows: list[tuple[str, Path, ctk.CTkButton]] = []
        self._filter_var = ctk.StringVar()

        self._build()

    # ==================================================================
    # Layout
    # ==================================================================

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1, minsize=_LIST_MIN_W)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.grid(row=0, column=0, sticky="ew",
                        padx=(theme.PAD_M, theme.PAD_S), pady=(theme.PAD_M, 0))
        SearchEntry(filter_row, textvariable=self._filter_var,
                    placeholder="Filter runs…").pack(fill="x", expand=True)
        self._filter_var.trace_add("write", lambda *_: self._refresh_list())

        self._list = ctk.CTkScrollableFrame(self, label_text="")
        self._list.grid(row=1, column=0, sticky="nsew",
                        padx=(theme.PAD_M, theme.PAD_S), pady=theme.PAD_M)

        detail = ctk.CTkFrame(self)
        detail.grid(row=0, column=1, rowspan=2, sticky="nsew",
                    padx=(theme.PAD_S, theme.PAD_M), pady=theme.PAD_M)
        self._build_detail(detail)

    def _build_detail(self, parent) -> None:
        self._name_label = ctk.CTkLabel(
            parent, text="Nothing selected", anchor="w", justify="left",
            wraplength=520, font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"))
        self._name_label.pack(fill="x", padx=theme.PAD_M,
                              pady=(theme.PAD_M, theme.PAD_S))

        self._meta_label = ctk.CTkLabel(
            parent, text="Pick a run from the list.", anchor="w", justify="left",
            text_color=theme.TEXT_MUTED, wraplength=520)
        self._meta_label.pack(fill="x", padx=theme.PAD_M, pady=(0, theme.PAD_M))

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.pack(fill="x", padx=theme.PAD_M, pady=(0, theme.PAD_S), anchor="w")

        self._open_btn = ctk.CTkButton(
            actions, text="Open results", width=180, height=40,
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            fg_color=theme.ACCENT_SLATE, hover_color=theme.ACCENT_SLATE_HOVER,
            state="disabled", command=self._open_selected)
        self._open_btn.pack(side="left")

        # Deleting a run is irreversible and there's no undo, so it takes two
        # clicks like the other destructive actions in the app.
        self._delete_btn = ConfirmButton(
            actions, text="Delete", confirm_text="Confirm delete",
            command=self._delete_selected,
            width=_ACTION_W, confirm_width=_ACTION_W, height=_ACTION_H)
        self._delete_btn.configure(state="disabled")
        self._delete_btn.pack(side="left", padx=(theme.PAD_S, 0))

        self._rename_btn = ctk.CTkButton(
            actions, text="Rename", width=_ACTION_W, height=_ACTION_H,
            fg_color="transparent", border_width=1,
            text_color=theme.TEXT_MUTED, hover_color=theme.CARD_HOVER,
            state="disabled", command=self._rename_selected)
        self._rename_btn.pack(side="left", padx=(theme.PAD_S, 0))

        self._folder_btn = ctk.CTkButton(
            actions, text="Show in folder", width=_ACTION_W, height=_ACTION_H,
            fg_color="transparent", border_width=1,
            text_color=theme.TEXT_MUTED, hover_color=theme.CARD_HOVER,
            state="disabled", command=self._reveal_selected)
        self._folder_btn.pack(side="left", padx=(theme.PAD_S, 0))

        self._status = ctk.CTkLabel(
            parent, text="", anchor="w", text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL))
        self._status.pack(fill="x", padx=theme.PAD_M, pady=(theme.PAD_S, 0))

    # ==================================================================
    # The list
    # ==================================================================

    def _refresh_list(self) -> None:
        for child in list(self._list.winfo_children()):
            child.destroy()
        self._rows.clear()

        query = self._filter_var.get().lower().strip()
        total = 0
        for kind, title in (("steady", "Steady"), ("unsteady", "Unsteady")):
            runs = backend_bridge.list_runs(kind)
            if query:
                runs = [r for r in runs
                        if query in backend_bridge.run_display_name(r).lower()]
            total += len(runs)

            ctk.CTkLabel(self._list, text=f"{title}  ({len(runs)})", anchor="w",
                         font=ctk.CTkFont(size=_HEADER_SIZE, weight="bold"),
                         text_color=theme.TEXT_MUTED).pack(
                fill="x", pady=(theme.PAD_M, theme.PAD_XS))

            if not runs:
                ctk.CTkLabel(self._list, text="none yet", anchor="w",
                             text_color=theme.TEXT_FAINT,
                             font=ctk.CTkFont(size=_ROW_SIZE)).pack(
                    fill="x", padx=theme.PAD_M)
                continue

            for run in runs:
                self._add_row(kind, run)

        if total == 0 and not query:
            ctk.CTkLabel(self._list, text="No saved runs yet.",
                         text_color=theme.TEXT_FAINT).pack(pady=theme.PAD_XL)

    def _add_row(self, kind: str, run: Path) -> None:
        name = backend_bridge.run_display_name(run)
        when = backend_bridge.run_timestamp(run).strftime("%Y-%m-%d %H:%M")

        button = ctk.CTkButton(
            self._list, text=f"{name}\n{when}", anchor="w", height=64,
            fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=theme.CARD_HOVER,
            font=ctk.CTkFont(size=_ROW_SIZE),
            command=lambda k=kind, r=run: self._select(k, r))
        button.pack(fill="x", pady=2)
        self._rows.append((kind, run, button))

    def _select(self, kind: str, run: Path) -> None:
        self._selected, self._selected_kind = run, kind
        self._delete_btn.disarm()       # never carry an armed delete between runs

        for _kind, row_run, button in self._rows:
            button.configure(fg_color=theme.CARD_BG if row_run == run else "transparent")

        json_path = backend_bridge.run_json_path(run)
        size = f"{json_path.stat().st_size // 1024} KB" if json_path else "unreadable"
        layout = "folder" if run.is_dir() else "single file"
        extras = []
        if run.is_dir():
            if (run / "run_report.pdf").exists():
                extras.append("PDF report")
            if (run / "graphs").is_dir():
                extras.append(f"{len(list((run / 'graphs').glob('*.png')))} PNGs")

        self._name_label.configure(text=backend_bridge.run_display_name(run))
        self._meta_label.configure(text="\n".join([
            f"{kind} run  ·  {layout}  ·  {size}",
            backend_bridge.run_timestamp(run).strftime("%A %d %B %Y, %H:%M"),
            ("also contains: " + ", ".join(extras)) if extras else "",
            str(run),
        ]).strip())

        state = "normal" if json_path else "disabled"
        for button in (self._open_btn, self._delete_btn,
                       self._rename_btn, self._folder_btn):
            button.configure(state=state)
        self._set_status("" if json_path else "No results file inside this run")

    # ==================================================================
    # Actions
    # ==================================================================

    def _open_selected(self) -> None:
        if self._selected is None:
            return
        target = ("steady_results" if self._selected_kind == "steady"
                  else "unsteady_results")
        shell = self.winfo_toplevel()
        page = shell._ensure_page(target)       # noqa: SLF001 - the shell's own API
        if hasattr(page, "show_run"):
            page.show_run(self._selected)
        shell.go(target)

    def _reveal_selected(self) -> None:
        if self._selected is not None:
            os_utils.reveal_in_file_explorer(self._selected)

    def _rename_selected(self) -> None:
        if self._selected is None:
            return
        current = backend_bridge.run_display_name(self._selected)
        new_name = ask_text(self, "Rename run", "New name:", initial=current,
                            ok_text="Rename")
        if not new_name or new_name == current:
            return

        # Keep the suffix for the single-file layout; a folder has none.
        target = self._selected.parent / (
            new_name if self._selected.is_dir() else f"{new_name}{self._selected.suffix}")
        if target.exists():
            self._set_status(f"{new_name} already exists", error=True)
            return
        try:
            self._selected.rename(target)
        except OSError as exc:
            self._set_status(f"Could not rename: {exc}", error=True)
            return
        self._selected = target
        self._refresh_list()
        self._select(self._selected_kind, target)
        self._set_status(f"Renamed to {new_name}")

    def _delete_selected(self) -> None:
        if self._selected is None:
            return
        run = self._selected
        try:
            if run.is_dir():
                shutil.rmtree(run)
            else:
                run.unlink()
                # The old single-file layout kept graphs in a sibling folder
                # named after the run; remove it too rather than orphaning it.
                sibling = run.parent / run.stem
                if sibling.is_dir():
                    shutil.rmtree(sibling)
        except OSError as exc:
            self._set_status(f"Could not delete: {exc}", error=True)
            return

        self._selected = None
        self._refresh_list()
        self._clear_detail()
        self._set_status(f"Deleted {backend_bridge.run_display_name(run)}")

    def _clear_detail(self) -> None:
        self._name_label.configure(text="Nothing selected")
        self._meta_label.configure(text="Pick a run from the list.")
        for button in (self._open_btn, self._delete_btn,
                       self._rename_btn, self._folder_btn):
            button.configure(state="disabled")

    def _set_status(self, text: str, *, error: bool = False) -> None:
        self._status.configure(
            text=text, text_color=theme.ERROR if error else theme.TEXT_MUTED)

    # ==================================================================
    # Shell contract
    # ==================================================================

    def on_show(self) -> None:
        # Re-read every time: a run may have finished since the last visit.
        self._refresh_list()
        if self._selected is not None and not self._selected.exists():
            self._selected = None
            self._clear_detail()
