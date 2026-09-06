"""
ResultsPage — everything the two results views have in common.

LAYOUT
------
    +----------------------------------------------------+-----------+
    | search .............................................|  Units    |
    +----------------------------------------------------+  Actions  |
    | [Tab] [Tab] [Tab]                                   |  Copy     |
    |                                                     |  Export   |
    |   scrollable rows                                   |  Folder   |
    |                                                     |  Graphs   |
    +----------------------------------------------------+-----------+
    | status line                                                     |
    +-----------------------------------------------------------------+

Same shape as the input pages: tabs on the left, a fixed action sidebar on the
right, one status line at the bottom. Consistency is the point — the two halves
of the app shouldn't feel like different programs.

THE UNIT TOGGLE
---------------
One control at the very top of the sidebar, above Actions, switching between
SI, MRT and IMP. Rows re-label and re-convert in place rather than being
rebuilt, which matters because a results page can hold several hundred of them.
It sits above the buttons because it governs them: the same choice decides what
the graphs and the generated PDF report are drawn in.

The search box filters rows live across every tab at once, matching on label,
raw JSON key and value, so you can find a number whether you know what it's
called in the app or in the file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import customtkinter as ctk

from src.ui.app import backend_bridge, theme
from src.ui.app import settings as user_settings
from src.ui.app.services import os_utils
from src.ui.app.widgets.help_icon import HelpIcon
from src.ui.app.widgets.kv_row import KVRow, describe, native_system_of, format_scalar
from src.ui.app.widgets.search_entry import SearchEntry

UNIT_SYSTEMS = ("SI", "IMP", "MRT")

_SIDEBAR_MIN_W = 220
_ACTION_W = 200


class ResultsPage(ctk.CTkFrame):
    """Base class for the steady and unsteady results views."""

    TITLE = ""
    KIND = ""

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate

        self.run_path: Optional[Path] = None
        self.results: dict = {}
        # True while a long main-thread job (graphs, PNGs, PDF) is pumping the
        # event loop. See busy() / pump().
        self._busy = False
        # Every KVRow on the page, so the unit toggle and the filter can reach
        # all of them without knowing which tab they live in.
        self._rows: list[KVRow] = []
        # Labels that aren't rows but still carry converted numbers — section
        # headers naming a sweep point's coordinates, for instance. Each is a
        # (widget, builder) pair; the builder is re-run on a unit change.
        self._dynamic_labels: list[tuple] = []
        # Embedded matplotlib figures, as (canvas, figure). Both halves are
        # kept because destroying the widget alone leaves pyplot holding the
        # figure, and a few dozen of those exhausts memory quickly.

        self.system = user_settings.get("default_program_units", "SI")
        # What the preference said last time we looked, so on_show can tell a
        # settings change apart from the user's own toolbar click.
        self._settings_system = self.system
        # Tab names in creation order, so set_tab_visible can put one back
        # where it belongs instead of at the end.
        self._tab_order: list[str] = []
        # The unit system the OPEN FILE's numbers are stored in. Not always SI:
        # see kv_row.native_system_of().
        self.native_system = "SI"
        self._system_var = ctk.StringVar(value=self.system)
        self._filter_var = ctk.StringVar()

        self._build_frame()
        self._build_tabs()

    # ==================================================================
    # Frame
    # ==================================================================

    def _build_frame(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=_SIDEBAR_MIN_W)
        self.grid_rowconfigure(1, weight=1)

        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.grid(row=0, column=0, columnspan=2, sticky="ew",
                        padx=theme.PAD_M, pady=(theme.PAD_M, 0))
        SearchEntry(filter_row, textvariable=self._filter_var,
                    placeholder="Filter by name, key or value…").pack(
            fill="x", expand=True)
        self._filter_var.trace_add("write", lambda *_: self._apply_filter())

        self.tabs = ctk.CTkTabview(self, anchor="w")
        self.tabs.grid(row=1, column=0, sticky="nsew",
                       padx=(theme.PAD_M, theme.PAD_S), pady=theme.PAD_M)

        sidebar = ctk.CTkFrame(self, fg_color="transparent")
        sidebar.grid(row=1, column=1, sticky="ns",
                     padx=(theme.PAD_S, theme.PAD_M), pady=theme.PAD_M)
        self._build_sidebar(sidebar)

        self.status_label = ctk.CTkLabel(
            self, text="", anchor="w", text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
        )
        self.status_label.grid(row=2, column=0, columnspan=2, sticky="ew",
                               padx=theme.PAD_M, pady=(0, theme.PAD_S))

    def _build_sidebar(self, parent) -> None:
        # Units first, above Actions. It governs everything below it — the rows
        # on screen, the graphs, and the generated report — so it reads wrong
        # sitting underneath the buttons it controls.
        self._build_units_group(parent)

        ctk.CTkLabel(parent, text="Actions", anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold")).pack(
            fill="x", pady=(theme.PAD_L, theme.PAD_S))

        ctk.CTkButton(parent, text="Copy to clipboard", width=_ACTION_W, height=36,
                      command=self._on_copy).pack(pady=theme.PAD_XS)
        ctk.CTkButton(parent, text="Export as CSV…", width=_ACTION_W, height=36,
                      command=self._on_export_csv).pack(pady=theme.PAD_XS)
        # Subclass hook, deliberately between CSV and Show in folder. Only the
        # unsteady page has a report to generate, and the base class should not
        # have to know which one that is.
        self._build_report_action(parent)
        ctk.CTkButton(parent, text="Show in folder", width=_ACTION_W, height=36,
                      command=self._on_show_in_folder).pack(pady=theme.PAD_XS)

        self._build_extra_actions(parent)

    def _build_units_group(self, parent) -> None:
        units_header = ctk.CTkFrame(parent, fg_color="transparent")
        units_header.pack(fill="x", pady=(0, theme.PAD_XS))
        ctk.CTkLabel(units_header, text="Units", anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold")).pack(
            side="left")
        HelpIcon(units_header,
                 "Select which unit to display values, create graphs, and "
                 "generate the report in. \nSI: International system \nIMP: "
                 "Imperial system \nMRT: A mix of SI and IMP catered to the "
                 "McGill Rocket Team").pack(side="left", padx=(theme.PAD_XS, 0))

        # Three buttons that together span exactly the width of one action
        # button below, gaps included — so the sidebar reads as one column
        # rather than the units group bulging out of it.
        self._unit_buttons: dict[str, ctk.CTkButton] = {}
        gaps = theme.PAD_XS * (len(UNIT_SYSTEMS) - 1)
        cell_w = (_ACTION_W - gaps) // len(UNIT_SYSTEMS)

        units_row = ctk.CTkFrame(parent, fg_color="transparent",
                                 width=_ACTION_W, height=32)
        units_row.pack(pady=theme.PAD_XS)
        units_row.pack_propagate(False)     # honour the explicit width
        for index, system in enumerate(UNIT_SYSTEMS):
            button = ctk.CTkButton(
                units_row, text=system, width=cell_w, height=32,
                font=ctk.CTkFont(size=theme.SIZE_SMALL),
                command=lambda s=system: self._on_system_changed(s))
            button.pack(side="left",
                        padx=(0 if index == 0 else theme.PAD_XS, 0))
            self._unit_buttons[system] = button
        self._highlight_unit_button()

    def _build_extra_actions(self, parent) -> None:
        """Hook for per-page sidebar buttons. Unsteady adds its graph picker."""

    def add_tab(self, name: str) -> ctk.CTkScrollableFrame:
        tab = self.tabs.add(name)
        wrap = ctk.CTkScrollableFrame(tab, label_text="")
        wrap.pack(fill="both", expand=True)
        self._tab_order.append(name)
        return wrap

    def set_tab_visible(self, name: str, visible: bool) -> None:
        """Show or hide a tab, keeping the original left-to-right order.

        Which tabs make sense depends on the run: a parametric study has no
        single performance block or trajectory, so those tabs would only ever
        say "nothing here".

        CTkTabview has no hide. Its own `delete` destroys the tab's frame and
        everything in it, and `insert` builds a fresh empty one, so using those
        would throw away the panel we just rendered. We hide the BUTTON on the
        segmented bar instead: the frame stays alive, the content survives, and
        tabs.set(name) still works. Insert index comes from the build order, so
        a re-shown tab lands back in place rather than at the end.
        """
        if name not in self._tab_order:
            return
        bar = self.tabs._segmented_button                # noqa: SLF001
        shown = list(bar._value_list)                    # noqa: SLF001

        if visible and name not in shown:
            wanted = self._tab_order.index(name)
            before = [n for n in self._tab_order[:wanted] if n in shown]
            bar.insert(len(before), name)
        elif not visible and name in shown:
            # Never leave the view sitting on a tab with no button.
            if self.tabs.get() == name:
                others = [n for n in self._tab_order
                          if n in shown and n != name]
                if others:
                    self.tabs.set(others[0])
            bar.delete(name)

    # ==================================================================
    # Subclass hooks
    # ==================================================================

    def _build_tabs(self) -> None:
        raise NotImplementedError

    def _refresh_panels(self) -> None:
        """Re-render every tab from self.results."""
        raise NotImplementedError

    # ==================================================================
    # Loading a run
    # ==================================================================

    def show_run(self, run: Any) -> None:
        """Display a saved run.

        Accepts whatever the backend returned or the browser selected: the
        results JSON, or the folder holding it.
        """
        try:
            path = Path(run)
        except (TypeError, ValueError):
            self._set_status("Nothing to show", error=True)
            return

        json_path = backend_bridge.run_json_path(path)
        if json_path is None:
            self._set_status(f"No results file in {path.name}", error=True)
            return

        try:
            self.results = json.loads(json_path.read_text(encoding="utf-8"))
            # Do this before anything renders: every row converts FROM this.
            self.native_system = native_system_of(self.results)
        except Exception as exc:                # noqa: BLE001
            self._set_status(f"Could not read {json_path.name}: {exc}", error=True)
            return

        self.run_path = json_path
        self._rows.clear()
        self._dynamic_labels.clear()
        self._refresh_panels()
        self._apply_filter()
        self._set_status(f"{backend_bridge.run_display_name(path)}  ·  "
                         f"{json_path.stat().st_size // 1024} KB")

    # ==================================================================
    # Rendering helpers
    # ==================================================================

    def clear(self, frame) -> None:
        for child in list(frame.winfo_children()):
            child.destroy()

    def add_row(self, parent, key: str, value: Any) -> KVRow:
        """One name/value row, registered for filtering and unit switching."""
        row = KVRow(parent, key, value, self.system,
                    native_system=self.native_system)
        row.pack(fill="x", pady=1)
        self._rows.append(row)
        return row

    def add_dynamic_label(self, widget, build_text) -> None:
        """Register a label whose text depends on the unit system.

        `build_text(system)` returns the label. Called immediately and again
        on every unit change.
        """
        self._dynamic_labels.append((widget, build_text))
        try:
            widget.configure(text=build_text(self.system))
        except Exception:                       # noqa: BLE001
            pass

    def add_heading(self, parent, text: str, *, text_color=None) -> None:
        """A section heading. `text_color` defaults to the theme's body colour.

        The colour override exists for headings that carry a severity, where
        the colour is the fastest part to read.
        """
        label = ctk.CTkLabel(parent, text=text, anchor="w",
                             font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"))
        if text_color is not None:
            label.configure(text_color=text_color)
        label.pack(fill="x", pady=(theme.PAD_M, theme.PAD_XS))

    def add_dict(self, parent, title: str, data: dict, *, child_title=None) -> None:
        """A heading and one row per entry, skipping nested structures.

        Nested dicts get their own section rather than being flattened into an
        unreadable single row.

        `child_title(parent_title, key) -> str` overrides the heading a nested
        dict gets. The default chains them, which reads fine two levels deep
        and turns into "Simulation settings — parametric_study_settings —
        oxidizer_mass_flow_rate" at three.
        """
        if not isinstance(data, dict) or not data:
            return
        self.add_heading(parent, title)
        for key, value in data.items():
            if isinstance(value, dict):
                nested = (child_title(title, key) if child_title
                          else f"{title} — {key}")
                self.add_dict(parent, nested, value, child_title=child_title)
            else:
                self.add_row(parent, key, value)

    # ---- long blocking jobs ------------------------------------------

    def busy(self, message: str) -> bool:
        """Claim the page for a long main-thread job. False if one is running.

        pump() lets the user click during a build, so every entry point that
        pumps has to be re-entrant-safe. One flag, checked at the top of each
        handler, is enough: the job never yields to anything but the event
        loop, so there is no race to lose.
        """
        if getattr(self, "_busy", False):
            return False
        self._busy = True
        self.pump(message)
        return True

    def done_busy(self) -> None:
        self._busy = False

    def pump(self, message: Optional[str] = None) -> None:
        """Update the status line and service the event loop.

        update() rather than update_idletasks(), and that is the whole point.
        update_idletasks() flushes pending redraws but never dispatches from
        the OS message queue, and on Windows a top-level window whose thread
        has not pumped that queue for five seconds gets painted over with a
        ghost copy and "(Not responding)" in the titlebar. Rendering fifteen
        plots takes longer than five seconds, so the title always went grey
        part-way through even though the status counter was visibly moving.

        The cost is that update() also dispatches input, so a second click on
        the button that started the job would re-enter it. busy() guards that.
        Anything else the user manages to click can still tear this page down
        underneath the job, hence the blanket except: a half-destroyed widget
        raising out of a progress tick would lose the work that was nearly done.
        """
        try:
            if message is not None:
                self._set_status(message)
            self.update()
        except Exception:                       # noqa: BLE001
            pass                # page torn down mid-job; nothing left to paint

    # ---- figures -----------------------------------------------------

    def render_progress(self, total: int):
        """A callback for figure_window.show_figures(on_progress=...).

        Figures are built hidden and revealed together, so nothing appears on
        screen until the last one is done. With ~27 plots that is several
        silent seconds, which reads as a freeze. This keeps a counter moving.
        """
        def progress(done: int) -> None:
            self.pump(f"Rendering graphs…  {done} of {total}")
        return progress

    def report_render(self, drawn: int, skipped: int, failed: int) -> None:
        """Summarise a batch of graph windows in the status line."""
        parts = [f"{drawn} drawn"]
        if skipped:
            parts.append(f"{skipped} not applicable to this run")
        if failed:
            parts.append(f"{failed} failed")
        self._set_status("  ·  ".join(parts), error=bool(failed))

    def add_empty(self, parent, text: str) -> None:
        ctk.CTkLabel(parent, text=text, text_color=theme.TEXT_FAINT,
                     font=ctk.CTkFont(size=theme.SIZE_BODY)).pack(
            pady=theme.PAD_XL)

    # ==================================================================
    # Units and filtering
    # ==================================================================

    def _on_system_changed(self, system: str) -> None:
        """Re-unit every row in place. No rebuild — there can be hundreds."""
        self.system = system
        self._system_var.set(system)
        self._highlight_unit_button()
        for row in self._rows:
            try:
                row.update_system(system)
            except Exception:                   # noqa: BLE001
                pass
        for widget, build_text in self._dynamic_labels:
            try:
                widget.configure(text=build_text(system))
            except Exception:                   # noqa: BLE001
                pass
        self._apply_filter()        # labels changed, so matches may have too

    def _highlight_unit_button(self) -> None:
        """Show which system is active. Selected is solid, the rest outlined."""
        for system, button in getattr(self, "_unit_buttons", {}).items():
            active = system == self.system
            button.configure(
                fg_color=theme.ACCENT_SLATE if active else "transparent",
                border_width=0 if active else 1,
                text_color=("white" if active else theme.TEXT_MUTED),
                hover_color=theme.ACCENT_SLATE_HOVER if active else theme.CARD_HOVER)

    def _apply_filter(self) -> None:
        """Show only the rows matching the search box, across every tab."""
        query = self._filter_var.get()
        for row in self._rows:
            try:
                if row.matches(query):
                    if not row.winfo_ismapped():
                        row.pack(fill="x", pady=1)
                elif row.winfo_ismapped():
                    row.pack_forget()
            except Exception:                   # noqa: BLE001
                pass

    # ==================================================================
    # Actions
    # ==================================================================

    def _visible_rows(self) -> list[KVRow]:
        return [r for r in self._rows if r.winfo_ismapped()]

    def _as_table(self) -> list[tuple[str, str, str]]:
        """(key, label, displayed value) for every visible row.

        Exports follow the filter and the unit toggle: what you exported is
        what you were looking at.
        """
        table = []
        for row in self._visible_rows():
            label, si_unit = describe(row.key)
            shown = row._value_widget.cget("text")      # noqa: SLF001
            table.append((row.key, row._name_widget.cget("text"), shown))  # noqa: SLF001
        return table

    def _on_copy(self) -> None:
        rows = self._as_table()
        if not rows:
            self._set_status("Nothing to copy", error=True)
            return
        text = "\n".join(f"{label}\t{value}" for _key, label, value in rows)
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._set_status(f"Copied {len(rows)} rows")
        except Exception as exc:                # noqa: BLE001
            self._set_status(f"Could not copy: {exc}", error=True)

    def _on_export_csv(self) -> None:
        from tkinter import filedialog
        import csv

        rows = self._as_table()
        if not rows:
            self._set_status("Nothing to export", error=True)
            return
        default = (self.run_path.parent.name if self.run_path else self.KIND) or "results"
        chosen = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(), title="Export results as CSV",
            initialfile=f"{default}.csv", defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not chosen:
            return
        try:
            with open(chosen, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["key", "name", f"value ({self.system})"])
                writer.writerows(rows)
        except Exception as exc:                # noqa: BLE001
            self._set_status(f"Could not export: {exc}", error=True)
            return
        self._set_status(f"Exported {len(rows)} rows to {Path(chosen).name}")

    def _build_report_action(self, parent) -> None:
        """Report button slot. Nothing by default; unsteady fills it in."""

    def _on_show_in_folder(self) -> None:
        if self.run_path is None:
            self._set_status("No run open", error=True)
            return
        os_utils.reveal_in_file_explorer(self.run_path)

    # ==================================================================
    # Shell contract
    # ==================================================================

    def _set_status(self, text: str, *, error: bool = False) -> None:
        self.status_label.configure(
            text=text, text_color=theme.ERROR if error else theme.TEXT_MUTED)

    def on_show(self) -> None:
        # The preference may have changed since this page was built, and pages
        # are cached rather than rebuilt. Only move if it actually changed, so
        # a system picked with the toolbar buttons survives navigating away.
        wanted = user_settings.get("default_program_units", "SI")
        if wanted != self._settings_system:
            self._settings_system = wanted
            self._on_system_changed(wanted)

        # A run may have finished since this page was last visible.
        if not self.results:
            self._set_status("No run open — pick one from Browse saved results")
