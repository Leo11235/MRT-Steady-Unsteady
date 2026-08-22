"""
Unsteady results.

Six tabs:

    Overall        headline performance
    Per phase      the same numbers broken down by flight phase
    Inputs         what the physics actually ran on, post-conversion
    Events         the transition log
    Warnings       runtime range checks, worst first

Graphs are not a tab. "Choose graphs…" in the sidebar opens each one in its own
window, so you can put a figure beside the numbers it came from. The same
builders draw those windows and the figures in `graphs.pdf`, so the two cannot
drift.
"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app.pages.results_page import ResultsPage
from src.ui.app.widgets import figure_window
from src.ui.app.widgets.graph_picker import show_graph_picker

# Worst first, matching the preflight dialog.
_SEVERITY_ORDER = ("critical", "caution", "advisory")
_SEVERITY_COLOR = {
    "critical": theme.ERROR,
    "caution": theme.WARNING_STRONG,
    "advisory": theme.WARNING,
}


class UnsteadyResultsPage(ResultsPage):
    TITLE = "Unsteady results"
    KIND = "unsteady"

    def _build_tabs(self) -> None:
        self._overall = self.add_tab("Overall")
        self._phases = self.add_tab("Per phase")
        self._inputs = self.add_tab("Inputs")
        self._events = self.add_tab("Events")
        self._warnings = self.add_tab("Warnings")
        self._selected_plots: Optional[list[str]] = None

    def _build_extra_actions(self, parent) -> None:
        ctk.CTkLabel(parent, text="Graphs", anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold")).pack(
            fill="x", pady=(theme.PAD_L, theme.PAD_XS))
        ctk.CTkButton(parent, text="Choose graphs…", width=200, height=36,
                      command=self._on_choose_graphs).pack(pady=theme.PAD_XS)

    # ==================================================================
    # Panels
    # ==================================================================

    def _refresh_panels(self) -> None:
        for frame in (self._overall, self._phases, self._inputs,
                      self._events, self._warnings):
            self.clear(frame)
        # Loading a different run invalidates whatever is on screen.
        figure_window.close_all()

        performance = self.results.get("performance") or {}
        self._render_overall(performance.get("overall") or {})
        self._render_phases(performance.get("by_phase") or {})
        self._render_inputs()
        self._render_events(self.results.get("event_log") or [])
        self._render_warnings(self.results.get("warnings"))

    def _render_overall(self, overall: dict) -> None:
        if not overall:
            self.add_empty(self._overall, "No performance block in this file.")
            return
        self.add_dict(self._overall, "Overall", overall)

        metadata = self.results.get("metadata") or {}
        if metadata:
            self.add_dict(self._overall, "Run metadata", metadata)

    def _render_phases(self, by_phase: dict) -> None:
        if not by_phase:
            self.add_empty(self._phases, "No per-phase breakdown in this file.")
            return
        # Phase keys sort naturally except for the 4a/4c sub-phases, which
        # sort correctly as strings anyway.
        for phase in sorted(by_phase):
            self.add_dict(self._phases, self._phase_title(phase), by_phase[phase])

    @staticmethod
    def _phase_title(phase: str) -> str:
        try:
            from src.common.plotting.unsteady_plots import PHASE_LABELS
            return PHASE_LABELS.get(phase, phase)
        except Exception:                       # noqa: BLE001
            return phase

    def _render_inputs(self) -> None:
        inputs = (self.results.get("static") or {}).get("rocket_inputs") or {}
        if not inputs:
            self.add_empty(self._inputs, "No inputs recorded in this file.")
            return
        # CV_models is a dict of which model each control volume used; it reads
        # better as its own section than as one row of JSON.
        models = inputs.get("CV_models")
        flat = {k: v for k, v in inputs.items() if k != "CV_models"}
        self.add_dict(self._inputs, "Rocket inputs (as the physics saw them)", flat)
        if isinstance(models, dict):
            self.add_dict(self._inputs, "Physics models", models)

    def _render_events(self, events: list) -> None:
        if not events:
            self.add_empty(self._events, "No events logged.")
            return
        self.add_heading(self._events, f"Event log ({len(events)})")
        for event in events:
            if not isinstance(event, dict):
                continue
            when = event.get("t_s", event.get("t"))
            message = event.get("message", event.get("event", ""))
            kind = event.get("event_type", "")
            row = ctk.CTkFrame(self._events, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=f"{when:.4f} s" if isinstance(when, (int, float))
                         else str(when), width=110, anchor="w",
                         text_color=theme.TEXT_MUTED,
                         font=ctk.CTkFont(family="Consolas",
                                          size=theme.SIZE_SMALL)).pack(side="left")
            ctk.CTkLabel(row, text=kind, width=150, anchor="w",
                         text_color=theme.TEXT_FAINT,
                         font=ctk.CTkFont(size=theme.SIZE_SMALL)).pack(side="left")
            ctk.CTkLabel(row, text=str(message), anchor="w", justify="left",
                         wraplength=520).pack(side="left", fill="x", expand=True)

    def _render_warnings(self, warnings) -> None:
        if warnings == "disabled":
            self.add_empty(self._warnings,
                           "Warnings were switched off for this run.")
            return
        if not isinstance(warnings, dict) or not warnings:
            self.add_empty(self._warnings, "No warnings. The run looked clean.")
            return

        level = warnings.get("overall_warning_level")
        triggered = warnings.get("triggered_warnings")
        # Two shapes in the wild: the newer nested one, and a flat dict of
        # warning entries from older runs.
        entries = triggered if isinstance(triggered, dict) else warnings

        if level:
            self.add_heading(self._warnings, f"Overall level: {level}")

        def severity_of(entry) -> str:
            value = entry.get("severity") if isinstance(entry, dict) else None
            return value if value in _SEVERITY_COLOR else "advisory"

        for severity in _SEVERITY_ORDER:
            group = {k: v for k, v in entries.items()
                     if isinstance(v, dict) and severity_of(v) == severity}
            if not group:
                continue
            ctk.CTkLabel(
                self._warnings, text=f"{severity.capitalize()} ({len(group)})",
                anchor="w", text_color=_SEVERITY_COLOR[severity],
                font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold")).pack(
                fill="x", pady=(theme.PAD_M, theme.PAD_XS))
            for warning_id, entry in group.items():
                card = ctk.CTkFrame(self._warnings, fg_color=theme.CARD_BG,
                                    corner_radius=6)
                card.pack(fill="x", pady=2)
                ctk.CTkLabel(card, text=str(entry.get("message", warning_id)),
                             anchor="w", justify="left", wraplength=620).pack(
                    fill="x", padx=theme.PAD_S, pady=(theme.PAD_S, 2))
                ctk.CTkLabel(card, text=warning_id, anchor="w",
                             text_color=theme.TEXT_FAINT,
                             font=ctk.CTkFont(family="Consolas",
                                              size=theme.SIZE_SMALL)).pack(
                    fill="x", padx=theme.PAD_S, pady=(0, theme.PAD_S))

    # ==================================================================
    # Graphs
    # ==================================================================

    def _on_choose_graphs(self) -> None:
        if not self.results:
            self._set_status("No run open", error=True)
            return

        chosen = show_graph_picker(self, preselected=self._selected_plots)
        if chosen is None:
            return                              # cancelled
        self._selected_plots = chosen
        if not chosen:
            figure_window.close_all()
            self._set_status("No graphs selected")
            return

        self._render_graphs(chosen)

    def _render_graphs(self, names: list[str]) -> None:
        """Build each figure and open it in its own window."""
        self._set_status(f"Drawing {len(names)} graph"
                         f"{'s' if len(names) != 1 else ''}…")
        self.update_idletasks()

        from src.common.plotting import unsteady_plots

        def build():
            for name in names:
                try:
                    yield (unsteady_plots.label_of(name),
                           unsteady_plots.build_figure(name, self.results))
                except Exception as exc:        # noqa: BLE001
                    yield name, exc             # one bad plot costs only itself

        self.report_render(*figure_window.show_figures(self, build()))

    def reset_to_defaults(self) -> None:
        """Close the graph windows when leaving. Figures are expensive to hold
        onto, and a window whose run is no longer open is just confusing."""
        figure_window.close_all()
