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
from src.ui.app.widgets.kv_row import (KVRow, SearchResultRow, describe,
                                       native_system_of, format_scalar)
from src.ui.app.widgets.search_entry import SearchEntry

UNIT_SYSTEMS = ("SI", "IMP", "MRT")

# How long typing has to stop before the results are rebuilt. Long enough that a
# burst of typing costs one rebuild rather than one per character, short enough
# that it still reads as instant.
_SEARCH_DEBOUNCE_MS = 250
# Separate timer for the dot leader, so a resize redraws the leaders without
# rebuilding the list.
_SEARCH_DOTS_MS = 120
# A query matching everything is a query nobody reads to the end of.
_SEARCH_MAX_ROWS = 300

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
        # Rows that re-unit with the rest but are never filtered or exported:
        # the summary box and the per-phase grid. See add_row(filterable=...).
        self._unfiltered_rows: list[KVRow] = []
        self._sections: list = []
        # Every searchable value, as (path, label, key, value, text_builder).
        # Built as the tabs render; see set_row_path() and the Search section
        # below. A builder is set only for rows that are not a plain number.
        self._search_index: list = []
        self._search_rows: list = []
        # Result rows are built once and re-pointed at whatever matches next.
        # See _render_search() for why they are not rebuilt.
        self._search_pool: list = []
        self._row_path: tuple = ()
        self._search_open = False
        self._search_after = None
        self._dots_after = None
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
        self._build_search_overlay()

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
                    placeholder="Search every tab by name…").pack(
            fill="x", expand=True)
        self._filter_var.trace_add("write", lambda *_: self._on_filter_changed())

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
                    self._select_tab(others[0])
            bar.delete(name)

    def _select_tab(self, name: str) -> None:
        """Select a tab, then make sure it is still the one on screen.

        CTkTabview.set() ends with `after(100, forget every tab but this one)`.
        Two selections inside that window leave the first timer to un-grid the
        tab the second one just showed, and the page goes blank with its button
        still lit. Re-asserting the current tab once the timers have run costs
        one idle callback and closes that hole.
        """
        try:
            self.tabs.set(name)
        except Exception:                       # noqa: BLE001
            return
        try:
            self.after(150, self._reassert_tab)
        except Exception:                       # noqa: BLE001
            pass

    def _reassert_tab(self) -> None:
        try:
            self.tabs._set_grid_current_tab()   # noqa: SLF001
        except Exception:                       # noqa: BLE001
            pass

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

        # Parsing a multi-megabyte results file and then building every row is
        # one uninterrupted main-thread stretch, long enough on a big run for
        # Windows to grey the window out. busy() pumps once on the way in and
        # claims the page against a second click; the pump below splits the
        # parse from the render so neither half is counted as one long freeze.
        if not self.busy("Loading run…"):
            return
        try:
            try:
                self.results = json.loads(json_path.read_text(encoding="utf-8"))
                # Do this before anything renders: every row converts FROM this.
                self.native_system = native_system_of(self.results)
            except Exception as exc:            # noqa: BLE001
                self._set_status(f"Could not read {json_path.name}: {exc}", error=True)
                return

            self.run_path = json_path
            self._rows.clear()
            self._unfiltered_rows.clear()
            self._dynamic_labels.clear()
            # Without this the next run's values are indexed on top of the last
            # one's, and searching then offers rows from a file you closed.
            self._reset_search()
            self._row_path = ()

            self.pump("Rendering results…")
            self._refresh_panels()
            self._on_filter_changed()
            self._set_status(f"{backend_bridge.run_display_name(path)}  ·  "
                             f"{json_path.stat().st_size // 1024} KB")
        finally:
            self.done_busy()

    # ==================================================================
    # Rendering helpers
    # ==================================================================

    def clear(self, frame) -> None:
        """Empty a tab, and forget the rows that lived in it.

        Without the forgetting, loading a second run leaves the first run's
        destroyed widgets in _rows, and every filter or unit change then walks
        hundreds of dead references.
        """
        for child in list(frame.winfo_children()):
            child.destroy()
        self._rows = [r for r in self._rows if r.winfo_exists()]
        self._unfiltered_rows = [r for r in self._unfiltered_rows if r.winfo_exists()]
        self._sections = [s for s in self._sections if s.winfo_exists()]

    def add_row(self, parent, key: str, value: Any, *,
                filterable: bool = True, label: Optional[str] = None,
                searchable: Optional[bool] = None) -> KVRow:
        """One name/value row, registered for unit switching.

        `filterable=False` keeps the row out of exports and out of the list the
        unit toggle walks as ordinary rows. The summary box and the per-phase
        grid use it, being fixed layouts rather than lists.

        `searchable` defaults to `filterable` and separates the two: the summary
        box is not a list you scroll, but its values are still results, and
        somebody searching for apogee should find it there.

        `label` overrides the registry's name, for rows whose meaning depends on
        where they sit rather than on their key.
        """
        row = KVRow(parent, key, value, self.system,
                    native_system=self.native_system, label=label)
        row.pack(fill="x", pady=1)
        if filterable:
            self._rows.append(row)
        else:
            self._unfiltered_rows.append(row)
        if searchable is None:
            searchable = filterable
        if searchable:
            self._register_searchable(key, row.label, value)
        return row

    def add_section(self, parent, title: str, *, start_open: bool = False,
                    subtitle: str = ""):
        """A collapsible block. Registered so a reload can forget it cleanly."""
        from src.ui.app.widgets.section import CollapsibleSection

        section = CollapsibleSection(parent, title, start_open=start_open,
                                     subtitle=subtitle)
        self._sections.append(section)
        return section

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
        for row in self._rows + self._unfiltered_rows:
            try:
                row.update_system(system)
            except Exception:                   # noqa: BLE001
                pass
        for widget, build_text in self._dynamic_labels:
            try:
                widget.configure(text=build_text(system))
            except Exception:                   # noqa: BLE001
                pass
        self._refresh_search_units()

    def _highlight_unit_button(self) -> None:
        """Show which system is active. Selected is solid, the rest outlined."""
        for system, button in getattr(self, "_unit_buttons", {}).items():
            active = system == self.system
            button.configure(
                fg_color=theme.ACCENT_SLATE if active else "transparent",
                border_width=0 if active else 1,
                text_color=("white" if active else theme.TEXT_MUTED),
                hover_color=theme.ACCENT_SLATE_HOVER if active else theme.CARD_HOVER)

    # ==================================================================
    # Search
    # ==================================================================
    #
    # Typing anything moves you to a results view that lists every matching
    # value as one flat row, each carrying the path you would have clicked
    # through to reach it.  Clearing the box puts you back where you were.
    #
    # It is a separate view rather than a filter over the real tabs because the
    # real tabs are mostly collapsed sections now: hiding rows inside folded
    # blocks means typing appears to do nothing, and opening every block that
    # holds a match rearranges the page under the user.  Building a list is both
    # simpler and more useful, since a result can then say where it lives.

    def set_row_path(self, *parts: str) -> None:
        """Where rows added from here on actually live.

        Renderers call this as they walk into a tab, a section and a sub-heading.
        The parts become the breadcrumb on a search result, so a value found by
        searching can be found again by clicking.
        """
        self._row_path = tuple(p for p in parts if p)

    def add_searchable_text(self, label: str, text_builder,
                            *, key: str = "") -> None:
        """Register a result that search should find but that is not a KVRow.

        The summary box builds some of its rows by hand: a verdict in words, a
        pair of masses sharing one unit. Those are still results. The builder is
        handed the unit system and returns the text, so a search result showing
        one re-units exactly like the row it came from.
        """
        self._register_searchable(key, label, None, text_builder)

    def _register_searchable(self, key: str, label: str, value: Any,
                             text_builder=None) -> None:
        self._search_index.append(
            (self._row_path, label, key, value, text_builder))

    def _build_search_overlay(self) -> None:
        """The results view: a panel that covers the current tab's contents.

        Deliberately NOT a tab. It used to be one, and the tab bar is a shared
        widget: showing the view meant inserting a button, selecting it, and
        deleting it again on every keystroke. Worse, CTkTabview.set() ends with
        `after(100, forget every tab except this one)`, so two of those in
        flight with different names would un-grid the tab you had just returned
        to. That is the tab that kept coming back empty.

        A placed overlay touches none of it. The tab bar stays live underneath,
        so clicking a tab still works and the tabview shows it without being
        told to. Clearing the box just takes the panel away, revealing the tab
        that was never actually left.
        """
        try:
            background = self.tabs.cget("fg_color")
        except Exception:                       # noqa: BLE001
            background = None
        self._search_overlay = ctk.CTkFrame(
            self.tabs, corner_radius=0,
            **({"fg_color": background} if background else {}))

        self._search_header = ctk.CTkLabel(
            self._search_overlay, text="", anchor="w",
            text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL))
        self._search_header.pack(fill="x", padx=theme.PAD_M,
                                 pady=(theme.PAD_S, 0))

        self._search_body = ctk.CTkScrollableFrame(self._search_overlay,
                                                   label_text="")
        self._search_body.pack(fill="both", expand=True,
                               padx=theme.PAD_S, pady=theme.PAD_S)
        try:
            # add="+", because CustomTkinter has its own Configure binding on
            # this frame and replacing it breaks scrolling.
            self._search_body.bind("<Configure>",
                                   lambda _e: self._schedule_dots(), add="+")
        except Exception:                       # noqa: BLE001
            pass

        try:
            self.tabs.configure(command=self._on_tab_clicked)
        except Exception:                       # noqa: BLE001
            pass

    def _current_tab_frame(self):
        try:
            return self.tabs.tab(self.tabs.get())
        except Exception:                       # noqa: BLE001
            return None

    def _show_search(self) -> None:
        if self._search_open:
            return
        anchor = self._current_tab_frame()
        try:
            if anchor is not None:
                self._search_overlay.place(in_=anchor, x=0, y=0,
                                           relwidth=1, relheight=1)
            else:
                self._search_overlay.place(relx=0, rely=0,
                                           relwidth=1, relheight=1)
            self._search_overlay.lift()
        except Exception:                       # noqa: BLE001
            return
        self._search_open = True

    def _hide_search(self) -> None:
        if not self._search_open:
            return
        self._search_open = False
        try:
            self._search_overlay.place_forget()
        except Exception:                       # noqa: BLE001
            pass

    def _reset_search(self) -> None:
        """Forget the last run's results without destroying the row widgets."""
        self._search_index.clear()
        self._search_rows = []
        for row in self._search_pool:
            try:
                if row.winfo_manager():
                    row.pack_forget()
            except Exception:                   # noqa: BLE001
                pass
        self._hide_search()

    def _on_tab_clicked(self) -> None:
        """Clicking a tab abandons the search.

        Nothing here selects anything: the tabview has already shown the tab
        that was clicked by the time this runs. Emptying the box takes the
        overlay away, and that is the whole of it.
        """
        if self._filter_var.get():
            self._filter_var.set("")

    def _on_filter_changed(self) -> None:
        """Called on every keystroke. Does as little as possible.

        Rebuilding the results list per character was enough work to make the
        typed letter itself appear late. The work is pushed onto a timer, and
        each new keystroke cancels the pending one, so a burst of typing costs
        one rebuild at the end of it.

        Emptying the box is the exception: leaving the search is cheap and
        waiting to do it feels like the page has stuck.
        """
        if self._search_after is not None:
            try:
                self.after_cancel(self._search_after)
            except Exception:                   # noqa: BLE001
                pass
            self._search_after = None
        if not (self._filter_var.get() or "").strip():
            self._apply_filter()
            return
        try:
            self._search_after = self.after(_SEARCH_DEBOUNCE_MS,
                                            self._apply_filter)
        except Exception:                       # noqa: BLE001
            self._apply_filter()

    def _apply_filter(self) -> None:
        """Rebuild the results view for whatever is in the box."""
        self._search_after = None
        query = (self._filter_var.get() or "").strip()
        if not query:
            self._hide_search()
            return
        self._render_search(query)
        self._show_search()

    def _render_search(self, query: str) -> None:
        """One row per match, in the order the tabs present them.

        The query is tested against the value's own name only, never against
        the breadcrumb. Searching "chamber" should find the things actually
        called chamber something, not every row that sits inside CV4.

        Rows are reused. The pool grows to the largest result set the session
        has seen and then stops, so a keystroke costs a few hundred string
        writes rather than a few hundred widget constructions and as many
        destructions. That churn is not just slow: every CustomTkinter widget
        is a canvas, and Tk aborts the process outright if Windows ever
        refuses it a drawing buffer.
        """
        needle = query.lower()
        hits = [entry for entry in self._search_index
                if needle in entry[1].lower()]
        total = len(hits)
        hits = hits[:_SEARCH_MAX_ROWS]

        if total == 0:
            self._search_header.configure(
                text=f"Nothing matching \u201c{query}\u201d.")
        elif total > len(hits):
            self._search_header.configure(
                text=f"{total} results for \u201c{query}\u201d. "
                     f"Showing the first {len(hits)}.")
        else:
            plural = "s" if total != 1 else ""
            self._search_header.configure(
                text=f"{total} result{plural} for \u201c{query}\u201d")

        for index, (path, label, key, value, builder) in enumerate(hits):
            if index < len(self._search_pool):
                row = self._search_pool[index]
            else:
                row = SearchResultRow(self._search_body, system=self.system,
                                      native_system=self.native_system)
                self._search_pool.append(row)
            row.show(key=key, label=label, value=value, path=path,
                     system=self.system, native_system=self.native_system,
                     text_builder=builder)
            if not row.winfo_manager():
                row.pack(fill="x", pady=1)

        # Hidden rows are always a suffix of the pool, so re-packing them later
        # in index order puts them back in the order they were built.
        for row in self._search_pool[len(hits):]:
            try:
                if row.winfo_manager():
                    row.pack_forget()
            except Exception:                   # noqa: BLE001
                pass

        self._search_rows = self._search_pool[:len(hits)]
        self._schedule_dots()

    def _schedule_dots(self) -> None:
        """Ask for a dot leader pass, later.

        Later matters. Drawing the leader means measuring widgets and then
        writing to one of them, and a write that happens inside the Configure
        event that layout fires can provoke the next Configure. Doing it from a
        timer puts the write after layout has settled instead of inside it.
        """
        if self._dots_after is not None:
            try:
                self.after_cancel(self._dots_after)
            except Exception:                   # noqa: BLE001
                pass
            self._dots_after = None
        if not self._search_rows:
            return
        try:
            self._dots_after = self.after(_SEARCH_DOTS_MS, self._draw_dots)
        except Exception:                       # noqa: BLE001
            self._draw_dots()

    def _draw_dots(self) -> None:
        self._dots_after = None
        try:
            available = self._search_body.winfo_width() - 4 * theme.PAD_M
        except Exception:                       # noqa: BLE001
            return
        for row in self._search_rows:
            try:
                row.draw_dots(available)
            except Exception:                   # noqa: BLE001
                pass

    def _refresh_search_units(self) -> None:
        for row in self._search_rows:
            try:
                row.update_system(self.system)
            except Exception:                   # noqa: BLE001
                pass
        self._schedule_dots()

    # ==================================================================
    # Actions
    # ==================================================================

    def _visible_rows(self) -> list[KVRow]:
        """Every searchable row. Exports cover the whole run, not a search.

        They used to follow the filter, back when searching hid rows in place.
        A search is now its own view, and exporting whatever happened to match a
        half-typed word is not what anyone means by "export results".
        """
        return list(self._rows)

    def _as_table(self) -> list[tuple[str, str, Any]]:
        """(key, label, value) for every visible row.

        Exports follow the filter and the unit toggle: what you exported is what
        you were looking at, in the units you were looking at it in.

        The value is the NUMBER, not the string on screen. The label is rounded
        for reading and will gain digit grouping, and neither survives a paste
        into a spreadsheet: a cell reading "5 274.4" is text. Non-numeric rows
        (terminal state, model names) pass through as themselves.
        """
        table = []
        for row in self._visible_rows():
            table.append((row.key, row._name_widget.cget("text"), row.raw_value))  # noqa: SLF001
        return table

    def _on_copy(self) -> None:
        rows = self._as_table()
        if not rows:
            self._set_status("Nothing to copy", error=True)
            return
        # Blanks stay blank rather than becoming the word "None".
        text = "\n".join(f"{label}\t{'' if value is None else value}"
                         for _key, label, value in rows)
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
