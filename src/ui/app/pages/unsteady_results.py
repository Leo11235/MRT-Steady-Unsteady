"""
Unsteady results.

Five tabs:

    Overall                 the summary box, and everything else the run measured
    Hardware & Parameters   the rocket as the physics saw it, one block per CV
    Per phase               the same numbers broken down by flight phase
    Events                  the transition log
    Warnings                runtime range checks, worst first

Nothing on this page is computed. Every number comes from the results file, and
the only arithmetic allowed is unit conversion and the radius-to-diameter
doubling, which lives in the output registry rather than here.

Graphs are not a tab. "Plot select graphs" in the sidebar opens the ones you
pick in their own windows, so you can put a figure beside the numbers it came
from. "Save graphs as PNGs" writes them all to graphs/ instead.

"Generate PDF report" writes the full run report: inputs, performance, phases,
events, warnings, then every plot. One registry builds all three outputs, so
the windows, the PNGs and the report cannot drift apart.
"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from src.common import output_registry as outputs
from src.common.unit_labels import pretty_unit
from src.ui.app import theme
from src.ui.app.widgets import kv_row
from src.ui.app.widgets.section import CollapsibleSection
from src.ui.app.pages.results_page import ResultsPage
from src.ui.app.services import os_utils
from src.ui.app.widgets import figure_window
from src.ui.app.widgets.graph_picker import show_graph_picker

# Worst first, matching the preflight dialog.
_SEVERITY_ORDER = ("critical", "caution", "advisory")
_SEVERITY_COLOR = {
    "critical": theme.ERROR,
    "caution": theme.WARNING_STRONG,
    "advisory": theme.WARNING,
}

# The overall level is a verdict on the run rather than a group label, so
# advisory reads as "fine" here and gets the green the group heading doesn't.
_LEVEL_COLOR = {
    "critical": theme.ERROR,
    "caution": theme.WARNING_STRONG,
    "advisory": theme.SUCCESS,
    "nominal": theme.SUCCESS,
}


# =============================================================================
# Layout
# =============================================================================
#
# What appears where, as data rather than as code.  Every entry is a key the
# output registry knows, so the label, the unit and the radius-to-diameter
# handling all come from there and none of it is repeated here.

# The summary box, in reading order.  Two entries are not plain keys:
# "__run__" is the terminal state, and "__level__" the overall warning level,
# both of which are verdicts rather than measurements.  A tuple means one row
# built from two values, rendered "used / available".
_MAIN_ROWS: tuple = (
    "__run__",
    "__level__",
    "apogee_agl",
    "burntime",
    "peak_thrust",
    "average_thrust",
    "total_impulse",
    "pad_thrust_to_weight",
    "peak_acceleration",
    ("ox_mass_consumed", "ox_mass_available", "Oxidizer mass used / available"),
    ("fuel_mass_consumed", "fuel_mass_available", "Fuel mass used / available"),
    "average_OF_ratio",
    ("peak_chamber_temperature", None, "Chamber stagnation temperature"),
    "specific_impulse",
)

# Everything in the summary box, so the Performance section below it can show
# the remainder without repeating anything.
_MAIN_KEYS = frozenset(
    entry[0] if isinstance(entry, tuple) else entry for entry in _MAIN_ROWS
) | frozenset(
    entry[1] for entry in _MAIN_ROWS if isinstance(entry, tuple) and entry[1]
)

# Hardware & Parameters, one block per control volume.  Sub-sections are
# ordered the way the oxidizer meets them, which is how anyone tracing a run
# reads the rocket.  A label after a key overrides the registry's name, for
# rows whose meaning comes from the heading above them.
_HARDWARE: tuple = (
    ("CV1_tank", "CV1: Tank", (
        ("Geometry", (
            "tank_internal_radius",
            "tank_internal_length",
            "tank_volume",
        )),
        ("N₂O parameters", (
            "tank_temperature",
            "tank_oxidizer_mass",
            "tank_ullage_fraction",
            "tank_liquid_volume",
            "tank_ullage_volume",
        )),
    )),
    ("CV2_valve", "CV2: Valve", ()),        # model-dependent; see _render_valve
    ("CV3_injector", "CV3: Injector", (
        ("Geometry", (
            "injector_discharge_coefficient",
            "injector_number_of_holes",
            "injector_hole_radius",
            "injector_hole_area",
        )),
        (None, (
            "feed_pressure_loss",
        )),
    )),
    ("CV4_chamber", "CV4: Chamber", (
        ("Fuel cell", (
            ("chamber_fuel_external_radius", "External diameter"),
            ("chamber_fuel_internal_radius", "Initial internal diameter"),
            ("chamber_fuel_length", "Length"),
            ("chamber_fuel_mass", "Mass"),
            ("chamber_fuel_density", "Density"),
        )),
        ("Pre chamber", (
            ("pre_chamber_radius", "Diameter"),
            ("pre_chamber_length", "Length"),
            ("pre_chamber_volume", "Volume"),
        )),
        ("Post chamber", (
            ("post_chamber_radius", "Diameter"),
            ("post_chamber_length", "Length"),
            ("post_chamber_volume", "Volume"),
        )),
        ("Combustion parameters", (
            "chamber_regression_rate_scaling_constant",
            "chamber_regression_rate_exponent",
            "chamber_cstar_efficiency",
            "average_cstar_actual",
            "average_cstar_theoretical",
        )),
    )),
    ("CV5_nozzle", "CV5: Nozzle", (
        ("Geometry", (
            "nozzle_throat_radius",
            "nozzle_exit_radius",
            "nozzle_throat_area",
            "nozzle_exit_area",
            "nozzle_expansion_ratio",
        )),
    )),
    ("CV6_trajectory", "CV6: Trajectory", (
        ("Construction", (
            "rocket_dry_mass",
            "rocket_outer_radius",
            "rocket_frontal_area",
        )),
        ("Flight parameters", (
            "rocket_drag_coefficient",
            "rocket_launch_angle",
            "launch_site_altitude_asl",
            "landing_downrange",
        )),
        ("Parachutes", (
            "drogue_parachute_radius",
            "drogue_parachute_drag_coefficient",
            "main_parachute_radius",
            "main_parachute_drag_coefficient",
            "main_parachute_deployment_altitude_agl",
        )),
    )),
)

# What each valve model has to say for itself.  "instant" has no parameters at
# all, and an empty section reads like a bug, so it gets a sentence instead.
_VALVE_ROWS = {
    "instant": (),
    "linear": ("valve_time_constant",),
    "sigmoid": ("sigmoid_half_time", "sigmoid_steepness"),
}
_VALVE_NOTE = {
    "instant": "Not simulated. Valve opened instantly.",
}

# Per-phase grid rows, grouped so the burn-only and flight-only blocks do not
# interleave into a checkerboard of dashes.
_PHASE_ROW_GROUPS: tuple = (
    (None, ("t_start", "t_end", "duration")),
    ("Engine", ("total_impulse", "peak_thrust", "average_thrust",
                "peak_chamber_pressure", "peak_chamber_temperature",
                "average_OF_ratio", "ox_mass_consumed", "fuel_mass_consumed")),
    ("Descent", ("peak_velocity", "terminal_velocity")),
)

# Terminal states, said in a way a person would say them.
_RUN_LABELS = {
    "success_landed": "Success",
    "liquid_quench": "Liquid quench",
    "apogee_abort": "Apogee abort",
    "phase_timeout": "Phase timeout",
    "failed_to_launch": "Failed to launch",
    "unknown": "Unknown terminal state",
}


class UnsteadyResultsPage(ResultsPage):
    TITLE = "Unsteady results"
    KIND = "unsteady"

    def _build_tabs(self) -> None:
        self._overall = self.add_tab("Overall")
        self._hardware = self.add_tab("Hardware & Parameters")
        self._phases = self.add_tab("Per phase")
        self._events = self.add_tab("Events")
        self._warnings = self.add_tab("Warnings")
        self._selected_plots: Optional[list[str]] = None

    def _build_report_action(self, parent) -> None:
        ctk.CTkButton(parent, text="Generate PDF report", width=200, height=36,
                      command=self._on_generate_report).pack(pady=theme.PAD_XS)

    def _build_extra_actions(self, parent) -> None:
        ctk.CTkLabel(parent, text="Graphs", anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold")).pack(
            fill="x", pady=(theme.PAD_L, theme.PAD_XS))
        ctk.CTkButton(parent, text="Plot select graphs", width=200, height=36,
                      command=self._on_choose_graphs).pack(pady=theme.PAD_XS)
        ctk.CTkButton(parent, text="Save graphs as PNGs", width=200, height=36,
                      command=self._on_save_pngs).pack(pady=theme.PAD_XS)

    # ==================================================================
    # Panels
    # ==================================================================

    def _refresh_panels(self) -> None:
        for frame in (self._overall, self._hardware, self._phases,
                      self._events, self._warnings):
            self.clear(frame)
        # Loading a different run invalidates whatever is on screen.
        figure_window.close_all()

        performance = self.results.get("performance") or {}
        self._render_overall(performance.get("overall") or {})
        self._render_hardware(performance.get("overall") or {})
        self._render_phases(performance.get("by_phase") or {})
        self._render_events(self.results.get("event_log") or [])
        self._render_warnings(self.results.get("warnings"))

    def _warning_entries(self) -> dict:
        """The triggered warnings, whatever shape this file uses.

        Two shapes in the wild: the current nested one under
        'triggered_warnings', and a flat dict of entries from older runs.
        Both panels need this, and they must agree, or the Overall tab could
        announce a count the Warnings tab doesn't show.
        """
        warnings = self.results.get("warnings")
        if not isinstance(warnings, dict) or not warnings:
            return {}
        triggered = warnings.get("triggered_warnings")
        return triggered if isinstance(triggered, dict) else warnings

    # ---- shared -------------------------------------------------------

    def _convert(self, value, key: str, system: str):
        """(number, unit label) for one value in the page's unit system.

        Goes through the same registry lookups a KVRow does, including the
        radius-to-diameter scale, so a number shown outside a KVRow cannot
        disagree with the same number shown inside one.
        """
        _label, si_unit = kv_row.describe(key)
        scaled = value
        scale = kv_row.display_scale_of(key)
        if scale != 1.0 and isinstance(value, (int, float)) and not isinstance(value, bool):
            scaled = value * scale
        return kv_row.value_for_display(scaled, si_unit, system,
                                        kv_row.category_of_key(key),
                                        self.native_system)

    def _unit_suffix(self, key: str, system: str) -> str:
        """" (N)" for a key that has a unit, "" for one that does not."""
        _value, unit = self._convert(1.0, key, system)
        shown = pretty_unit(unit)
        return f" ({shown})" if shown else ""

    def _add_text_row(self, parent, label: str, text: str, colour=None) -> None:
        """A row whose value is a word rather than a measurement."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(row, text=label, width=340, anchor="w").pack(
            side="left", padx=(0, theme.PAD_S))
        value = ctk.CTkLabel(row, text=text, anchor="w", justify="left",
                             wraplength=520)
        if colour is not None:
            value.configure(text_color=colour)
        value.pack(side="left", fill="x", expand=True)

    # ---- Overall ------------------------------------------------------

    def _render_overall(self, overall: dict) -> None:
        # Before the early return below: a run with no performance block is
        # exactly the kind that aborted, so its critical warnings are the most
        # worth surfacing, not the least.
        critical = [key for key, entry in self._warning_entries().items()
                    if isinstance(entry, dict) and entry.get("severity") == "critical"]
        if critical:
            count = len(critical)
            noun = "warning" if count == 1 else "warnings"
            ctk.CTkLabel(
                self._overall,
                text=f"{count} critical simulation {noun} detected.",
                anchor="w", text_color=theme.ERROR,
                font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold")).pack(
                fill="x", pady=(theme.PAD_M, 0))
            ctk.CTkLabel(
                self._overall,
                text="Go to the warnings tab to see more details.",
                anchor="w",
                font=ctk.CTkFont(size=theme.SIZE_SMALL)).pack(
                fill="x", pady=(0, theme.PAD_XS))

        if not overall:
            self.add_empty(self._overall, "No performance block in this file.")
            return

        self._render_summary_box(overall)
        self._render_performance_rest(overall)

    def _render_summary_box(self, overall: dict) -> None:
        """The dozen numbers an engineer checks first, in one bordered card.

        Deliberately neither collapsible nor filterable: it answers "how did this
        run go", and a search box able to reduce it to one row would be
        destroying the only fixed point on the page.
        """
        box = ctk.CTkFrame(self._overall, fg_color=theme.CARD_BG,
                           border_color=theme.ACCENT_SLATE, border_width=2,
                           corner_radius=8)
        box.pack(fill="x", pady=(theme.PAD_M, theme.PAD_S))

        inner = ctk.CTkFrame(box, fg_color="transparent")
        inner.pack(fill="x", padx=theme.PAD_M, pady=theme.PAD_M)

        for entry in _MAIN_ROWS:
            if entry == "__run__":
                text, colour = self._run_verdict()
                self._add_text_row(inner, "Run", text, colour)
            elif entry == "__level__":
                level = self._overall_level()
                self._add_text_row(inner, "Overall warning level",
                                   level.capitalize(), _LEVEL_COLOR.get(level))
            elif isinstance(entry, tuple):
                used_key, total_key, label = entry
                self._add_pair_row(inner, used_key, total_key, label, overall)
            else:
                value = outputs.value_of(overall, entry)
                if value is not None:
                    self.add_row(inner, entry, value, filterable=False)

    def _render_performance_rest(self, overall: dict) -> None:
        """Everything the run measured that the summary box does not show.

        Collapsed by default. The point is that no computed result is invisible,
        not that every result deserves equal billing.
        """
        rest = {key: value for key, value in overall.items()
                if outputs.canonical(key) not in _MAIN_KEYS}
        metadata = self.results.get("metadata") or {}
        if not rest and not metadata:
            return

        section = CollapsibleSection(self._overall, "Performance", start_open=False)
        section.pack(fill="x", pady=theme.PAD_XS)
        for key, value in rest.items():
            self.add_row(section.body, key, value)
        if metadata:
            self.add_heading(section.body, "Run metadata")
            for key, value in metadata.items():
                self.add_row(section.body, key, value)

    def _add_pair_row(self, parent, used_key: str, total_key, label: str,
                      overall: dict) -> None:
        """One row reading "used / available".

        One label because that is the comparison people actually make, but the
        export still carries the two numbers separately: a spreadsheet cell
        reading "14.3 / 15.5" is a string nobody can sum. With no second value
        the row degrades to an ordinary one.
        """
        used = outputs.value_of(overall, used_key)
        if used is None:
            return
        total = outputs.value_of(overall, total_key) if total_key else None
        if total is None:
            self.add_row(parent, used_key, used, filterable=False, label=label)
            return

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=1)
        name = ctk.CTkLabel(row, text="", width=340, anchor="w")
        name.pack(side="left", padx=(0, theme.PAD_S))
        value = ctk.CTkLabel(row, text="", anchor="w")
        value.pack(side="left", fill="x", expand=True)

        self.add_dynamic_label(
            name,
            lambda system, k=used_key, t=label: t + self._unit_suffix(k, system))
        self.add_dynamic_label(
            value,
            lambda system, u=used, v=total, k=used_key:
            kv_row.format_scalar(self._convert(u, k, system)[0]) + " / "
            + kv_row.format_scalar(self._convert(v, k, system)[0]))

    def _run_verdict(self) -> tuple:
        """(text, colour) for the Run row.

        A nominal run says so in one word. Anything else names the state and
        gives the reason with it, because "apogee_abort" on its own tells a
        reader nothing about what to change.
        """
        metadata = self.results.get("metadata") or {}
        state = str(metadata.get("terminal_state") or "unknown")
        label = _RUN_LABELS.get(state, state.replace("_", " ").capitalize())
        if metadata.get("completed_nominally"):
            return label, theme.SUCCESS
        reason = str(metadata.get("terminal_reason") or "").strip()
        return (f"{label}: {reason}" if reason else label), theme.ERROR

    def _overall_level(self) -> str:
        warnings = self.results.get("warnings")
        if isinstance(warnings, dict):
            level = warnings.get("overall_warning_level")
            if level:
                return str(level).lower()
        return "nominal"

    # ---- Hardware & Parameters ----------------------------------------

    def _render_hardware(self, overall: dict) -> None:
        """The rocket as the physics saw it, one collapsible block per CV.

        Values come from static.rocket_inputs, except the two averaged c*
        figures, which are performance results but belong beside the combustion
        parameters they describe. Hence the fallback lookup into `overall`.

        Sub-sections run in the order the oxidizer meets them, which is how
        anyone tracing a run reads the rocket.
        """
        inputs = (self.results.get("static") or {}).get("rocket_inputs") or {}
        if not inputs:
            self.add_empty(self._hardware, "No inputs recorded in this file.")
            return
        models = inputs.get("CV_models") or {}

        for cv_key, title, groups in _HARDWARE:
            section = CollapsibleSection(self._hardware, title, start_open=False)
            section.pack(fill="x", pady=theme.PAD_XS)

            model = models.get(cv_key)
            if model:
                self._add_text_row(section.body, "Physics model", str(model))

            if cv_key == "CV2_valve":
                self._render_valve(section.body, model, inputs)
                continue

            for heading, keys in groups:
                rendered = []
                for item in keys:
                    key, label = item if isinstance(item, tuple) else (item, None)
                    value = inputs.get(key)
                    if value is None:
                        value = outputs.value_of(overall, key)
                    if value is None:
                        continue
                    rendered.append((key, value, label))
                if not rendered:
                    continue
                if heading:
                    self.add_heading(section.body, heading)
                for key, value, label in rendered:
                    self.add_row(section.body, key, value, label=label)

    def _render_valve(self, parent, model, inputs: dict) -> None:
        """CV2 is the one block whose contents depend on which model ran.

        An instant valve has no parameters at all, and an empty section reads
        like a rendering bug, so it says what it did instead.
        """
        note = _VALVE_NOTE.get(model)
        if note:
            ctk.CTkLabel(parent, text=note, anchor="w",
                         text_color=theme.TEXT_MUTED,
                         font=ctk.CTkFont(size=theme.SIZE_SMALL,
                                          slant="italic")).pack(
                fill="x", pady=(theme.PAD_XS, 0))
            return
        for key in _VALVE_ROWS.get(model, ()):
            if key in inputs:
                self.add_row(parent, key, inputs[key])

    # ---- Per phase ----------------------------------------------------

    def _render_phases(self, by_phase: dict) -> None:
        """Phases across, quantities down, totals on the right.

        Reading along a row shows how one quantity evolved through the flight,
        which is the question people actually ask of this table. Cells with
        nothing to say show a dash: a coast phase has no chamber pressure, and
        that is not a gap in the data.
        """
        if not by_phase:
            self.add_empty(self._phases, "No per-phase breakdown in this file.")
            return

        try:
            from src.common.phases import PHASE_ORDER
            order = [p for p in PHASE_ORDER if p in by_phase]
            order += [p for p in sorted(by_phase) if p not in order]
        except Exception:                       # noqa: BLE001
            order = sorted(by_phase)

        grid = ctk.CTkFrame(self._phases, fg_color="transparent")
        grid.pack(fill="x", pady=theme.PAD_M)

        headers = ["", *[self._phase_title(p) for p in order], "Total"]
        for column, text in enumerate(headers):
            ctk.CTkLabel(grid, text=text, anchor="w",
                         font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold")).grid(
                row=0, column=column, sticky="w",
                padx=(0, theme.PAD_M), pady=(0, theme.PAD_XS))

        line = 1
        for heading, keys in _PHASE_ROW_GROUPS:
            present = [k for k in keys
                       if any(outputs.value_of(by_phase[p], k) is not None
                              for p in order)]
            if not present:
                continue
            if heading:
                ctk.CTkLabel(grid, text=heading, anchor="w",
                             text_color=theme.TEXT_MUTED,
                             font=ctk.CTkFont(size=theme.SIZE_SMALL,
                                              weight="bold")).grid(
                    row=line, column=0, sticky="w", pady=(theme.PAD_S, 0))
                line += 1
            for key in present:
                self._add_grid_row(grid, line, key, order, by_phase)
                line += 1

    def _add_grid_row(self, grid, line: int, key: str, order: list,
                      by_phase: dict) -> None:
        name = ctk.CTkLabel(grid, text="", anchor="w")
        name.grid(row=line, column=0, sticky="w", padx=(0, theme.PAD_M))
        label, _unit = kv_row.describe(key)
        self.add_dynamic_label(
            name, lambda system, k=key, t=label: t + self._unit_suffix(k, system))

        for column, phase in enumerate(order, start=1):
            self._add_grid_cell(grid, line, column, key,
                                outputs.value_of(by_phase[phase], key))

        # The totals column is what makes this table self-checking: phase
        # impulses summing to the run's total means the phase boundaries line
        # up. Rows with no meaningful total, the averages, get a dash rather
        # than a fiction, because the mean of three phase means is not the mean.
        self._add_grid_cell(grid, line, len(order) + 1, key,
                            outputs.aggregate_phases(by_phase, key))

    def _add_grid_cell(self, grid, line: int, column: int, key: str, value) -> None:
        if value is None:
            ctk.CTkLabel(grid, text="\u2014", anchor="w",
                         text_color=theme.TEXT_MUTED).grid(
                row=line, column=column, sticky="w", padx=(0, theme.PAD_M))
            return
        cell = ctk.CTkLabel(grid, text="", anchor="w")
        cell.grid(row=line, column=column, sticky="w", padx=(0, theme.PAD_M))
        self.add_dynamic_label(
            cell, lambda system, v=value, k=key:
            kv_row.format_scalar(self._convert(v, k, system)[0]))

    @staticmethod
    def _phase_title(phase: str) -> str:
        try:
            from src.common.phases import PHASE_LABELS
            return PHASE_LABELS.get(phase, phase)
        except Exception:                       # noqa: BLE001
            return phase

    def _render_events(self, events: list) -> None:
        if not events:
            self.add_empty(self._events, "No events logged.")
            return
        self.add_heading(self._events, f"Event log ({len(events)})")
        for event in events:
            if not isinstance(event, dict):
                continue
            when = outputs.value_of(event, "t")
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
        entries = self._warning_entries()

        if level:
            self.add_heading(self._warnings, f"Overall level: {level}",
                             text_color=_LEVEL_COLOR.get(str(level).lower()))

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

    def _on_generate_report(self) -> None:
        """Build the run report, then show it in the file explorer.

        Runs on the main thread and blocks: it renders every plot, which takes
        a few seconds. The status line counts them so the freeze is explained
        rather than mysterious.

        The report is drawn in whatever unit system the sidebar has selected
        right now, so what lands in the PDF matches what is on screen.
        """
        if not self.results or self.run_path is None:
            self._set_status("No run open", error=True)
            return

        from src.common.unsteady_PDF_report import generate_report

        if not self.busy("Generating PDF report…"):
            return

        def progress(done: int, total: int) -> None:
            self.pump(f"Generating PDF report…  plot {done} of {total}")

        try:
            path = generate_report(self.run_path.parent, self.results,
                                   on_progress=progress, on_stage=self.pump,
                                   system=self.system)
        except Exception as exc:                # noqa: BLE001
            self._set_status(f"Could not write the report: "
                             f"{type(exc).__name__}: {exc}", error=True)
            return
        finally:
            self.done_busy()

        self._set_status(f"Report written to {path.name}")
        os_utils.reveal_in_file_explorer(path)

    def _on_save_pngs(self) -> None:
        """Write every plot as a PNG into graphs/, then open that folder."""
        if not self.results or self.run_path is None:
            self._set_status("No run open", error=True)
            return

        from src.common.plotting import unsteady_plots

        specs = unsteady_plots.plot_specs()
        if not self.busy(f"Saving graphs…  0 of {len(specs)}"):
            return

        try:
            figures, names = [], []
            for index, spec in enumerate(specs):
                self.pump(f"Saving graphs…  {index + 1} of {len(specs)}")
                try:
                    figure = spec.builder(self.results)
                except Exception:               # noqa: BLE001
                    continue                    # one bad plot costs only itself
                if figure is not None:
                    figures.append(figure)
                    names.append(spec.name)

            if not figures:
                self._set_status("No plots could be built from this run", error=True)
                return

            out_dir = self.run_path.parent
            # Writing 15 PNGs is a second or two with no callback of its own.
            self.pump(f"Writing {len(figures)} PNGs…")
            try:
                unsteady_plots._save_figures_to_png(figures, names, out_dir)
            except Exception as exc:            # noqa: BLE001
                self._set_status(f"Could not save the PNGs: "
                                 f"{type(exc).__name__}: {exc}", error=True)
                return
        finally:
            self.done_busy()

        self._set_status(f"{len(figures)} graphs saved to graphs/")
        os_utils.reveal_in_file_explorer(out_dir / "graphs")

    def _render_graphs(self, names: list[str]) -> None:
        """Build each figure and open it in its own window."""
        if not self.busy(f"Rendering graphs…  0 of {len(names)}"):
            return

        from src.common.plotting import unsteady_plots

        def build():
            for name in names:
                try:
                    yield (unsteady_plots.label_of(name),
                           unsteady_plots.build_figure(name, self.results))
                except Exception as exc:        # noqa: BLE001
                    yield name, exc             # one bad plot costs only itself

        try:
            self.report_render(*figure_window.show_figures(
                self, build(), on_progress=self.render_progress(len(names))))
        finally:
            self.done_busy()

    def reset_to_defaults(self) -> None:
        """Close the graph windows when leaving. Figures are expensive to hold
        onto, and a window whose run is no longer open is just confusing."""
        figure_window.close_all()
