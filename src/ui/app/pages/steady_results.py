"""
Steady results.

Two tabs, whatever the run:

    Overall               what the run produced
    Hardware & Parameters the rocket it produced it with, one block per CV

A steady run comes in three shapes and the page follows them. A HOTFIRE burns
at one operating point and never flies, so everything downstream of the nozzle
is absent: no apogee, no thrust-to-weight, no wet mass. Those rows do not
appear at all rather than appearing empty, which falls out of the layout on its
own, since a row whose key is missing is skipped. A CONVERGENCE run flies, and
its real answer is the fuel port diameter it solved for. A PARAMETRIC study is
many convergence runs, so its Overall tab ranks them, says what was swept, and
gives each one its own card.

WHERE THE NUMBERS COME FROM
---------------------------
rocket_parameters is what the run computed, rocket_inputs is what it was given,
and the page reads both: chamber pressure is an input, apogee is a result, and
a reader looking at the summary does not care which is which. Every key is
looked up with .get, so a file written before a key existed loses that row and
nothing else.

Apogee is above the launch pad. Runs written before v1.6 pt. 14 have only the
sea-level number, and rather than relabel it, the box says ASL when that is
what it is showing.

WHAT IS NOT HERE
----------------
No Inputs tab: Hardware & Parameters is the inputs, arranged the way the
oxidizer meets them instead of in file order. No Trajectory tab: the ascent is
a 455-point series that belongs in the graphs, and the two numbers worth
reading off it, peak velocity and peak acceleration, are computed in the
backend and shown under Performance.
"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from src.common import variable_conversions as vc
from src.ui.app import theme
from src.ui.app.pages.results_page import ResultsPage
from src.ui.app.widgets import figure_window, grouped_menu, summary_box
from src.ui.app.widgets.graph_picker import show_graph_picker, steady_specs
from src.ui.app.widgets.kv_row import category_of_key, describe, format_scalar
from src.ui.app.widgets.parametric_graph_dialog import show_parametric_graph_dialog
from src.ui.app.widgets.tooltip import Tooltip

_OVERALL_TAB = "Overall"
_HARDWARE_TAB = "Hardware & Parameters"

# The handful of outputs anyone actually plots against a swept variable, or
# ranks a sweep by. They go at the top of both dropdowns; everything else
# follows under a second header.
_COMMON_OUTPUTS = (
    "Isp", "thrust", "burntime", "total_impulse",
    "average_oxidizer_to_fuel_ratio", "thrust_to_weight_ratio",
)

# A swept list this long or longer is elided in the middle: three, gap, three.
_ELIDE_SWEPT_FROM = 8
# How many runs the ranking names before it stops and counts the rest.
_RANKED_SHOWN = 3
_RANK_NAMES = ("Best", "Second best", "Third best")


# =============================================================================
# Layout
# =============================================================================
#
# What appears where, as data. Every entry is a key the output registry knows,
# so the label, the unit and the radius-to-diameter handling all come from
# there and none of it is repeated here.

# Two entries are verdicts rather than measurements, and are built by hand.
_VERDICT = "__verdict__"
_SIM_TYPE = "__simtype__"

# The summary box, in reading order. A tuple is one row built from two keys,
# rendered "left / right", or from one key with a label the layout supplies.
_MAIN_ROWS: tuple = (
    _VERDICT,
    _SIM_TYPE,
    ("reached_apogee_agl", "target_apogee", "Apogee achieved / target"),
    ("initial_internal_fuel_radius", None, "Fuel initial internal diameter"),
    "burntime",
    "thrust",
    "total_impulse",
    "thrust_to_weight_ratio",
    "chamber_pressure",
    "oxidizer_mass",
    "fuel_mass",
    "average_oxidizer_to_fuel_ratio",
    "chamber_temperature",
    "Isp",
    ("nozzle_throat_radius", None, "Nozzle throat diameter"),
    ("nozzle_exit_radius", None, "Nozzle exit diameter"),
)

# A hotfire is given its port diameter rather than solving for it, so showing
# it as a headline result would be showing the user their own input back.
_CONVERGED_ONLY = frozenset({_VERDICT, "initial_internal_fuel_radius"})

_SIM_TYPE_LABELS = {
    "fuel_mass_convergence": "Fuel mass convergence",
    "hotfire": "Hotfire",
    "parametric_study": "Parametric study",
}

# Hardware & Parameters, one block per control volume, each in the order the
# oxidizer meets it. A label after a key overrides the registry's name, for
# rows whose meaning comes from the heading above them.
_HARDWARE: tuple = (
    ("CV1: Tank & Injector", (
        (None, (
            "oxidizer_mass_flow_rate",
        )),
    )),
    ("CV2: Chamber", (
        ("Fuel cell", (
            ("fuel_external_radius", "External diameter"),
            ("initial_internal_fuel_radius", "Initial internal diameter"),
            ("fuel_length", "Length"),
            ("fuel_mass", "Mass"),
            ("fuel_grain_density", "Density"),
        )),
        ("Combustion parameters", (
            "chamber_pressure",
            "regression_rate_scaling_coefficient",
            "regression_rate_exponent",
            "augmented_regression_rate_exponent",
            "chamber_temperature",
            "chamber_gas_molar_weight",
            "heat_capacity_ratio",
        )),
    )),
    ("CV3: Nozzle", (
        ("Geometry", (
            ("nozzle_throat_radius", "Throat diameter"),
            ("nozzle_exit_radius", "Exit diameter"),
            "nozzle_throat_area",
            "nozzle_exit_area",
            "nozzle_expansion_ratio",
        )),
        ("Exit conditions", (
            "nozzle_gas_exit_pressure",
            "nozzle_gas_exit_mach_number",
            "nozzle_gas_exit_temperature",
            "nozzle_gas_exit_velocity",
        )),
    )),
    ("CV4: Rocket body", (
        ("Construction", (
            "dry_mass",
            ("rocket_external_radius", "Outer diameter"),
            "wet_mass",
        )),
        ("Flight parameters", (
            "drag_coefficient",
            "launch_angle",
            "launch_site_altitude",
        )),
    )),
)


def _hardware_keys() -> frozenset:
    keys = set()
    for _title, groups in _HARDWARE:
        for _heading, items in groups:
            for item in items:
                keys.add(item[0] if isinstance(item, tuple) else item)
    return frozenset(keys)


def _main_keys() -> frozenset:
    keys = set()
    for entry in _MAIN_ROWS:
        if isinstance(entry, tuple):
            keys.add(entry[0])
            if entry[1]:
                keys.add(entry[1])
        elif not entry.startswith("__"):
            keys.add(entry)
    return frozenset(keys)


# Shown by the box without being one of its keys: the verdict row IS this
# flag, and repeating it below as "Target apogee reached: True" says nothing.
_SHOWN_ELSEWHERE = frozenset({"target_apogee_reached"})

# Everything the box or the hardware tab already shows, so the Performance
# section below the box can show the remainder without repeating anything.
_SHOWN_KEYS = _main_keys() | _hardware_keys() | _SHOWN_ELSEWHERE


class SteadyResultsPage(ResultsPage):
    TITLE = "Steady results"
    KIND = "steady"

    def _build_tabs(self) -> None:
        self._overall = self.add_tab(_OVERALL_TAB)
        self._hardware = self.add_tab(_HARDWARE_TAB)
        self._selected_plots = None
        # The ranking controls, rebuilt with each parametric run.
        self._rank_var: Optional[ctk.StringVar] = None
        self._rank_direction: Optional[ctk.StringVar] = None
        self._rank_wires: dict = {}
        self._rank_body = None

    def _build_extra_actions(self, parent) -> None:
        ctk.CTkLabel(parent, text="Graphs", anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold")).pack(
            fill="x", pady=(theme.PAD_L, theme.PAD_XS))
        # One button whose label and behaviour follow the simulation type.
        # Always present, even for a hotfire: graphs may exist there one day,
        # and a button that vanishes is harder to find than one that explains.
        self._graphs_btn = ctk.CTkButton(
            parent, text="Show graphs…", width=200, height=36,
            command=self._on_graphs)
        self._graphs_btn.pack(pady=theme.PAD_XS)
        # A greyed button with no explanation is a dead end; the tooltip says
        # why it's off.
        self._graphs_tip = Tooltip(self._graphs_btn, "")

    def _sync_graphs_button(self) -> None:
        sim_type = self._sim_type
        if sim_type == "parametric_study":
            self._graphs_btn.configure(text="Parametric graphs…", state="normal")
            self._graphs_tip.set_text(
                "Plot an output against the swept variables, as a 2D line or "
                "a 3D surface.")
        elif sim_type == "hotfire":
            # Greyed rather than hidden, so it's visibly a gap rather than a
            # feature you failed to find.
            self._graphs_btn.configure(text="Show graphs…", state="disabled")
            self._graphs_tip.set_text(
                "No hotfire graphs available. A hotfire computes performance "
                "at one operating point and produces no time series, so "
                "there's nothing to plot yet.")
            return
        else:
            self._graphs_btn.configure(text="Show graphs…", state="normal")
            self._graphs_tip.set_text(
                "Kinematics, thrust and forces over the flight.")

    @property
    def _sim_type(self) -> str:
        return ((self.results.get("simulation_settings") or {})
                .get("simulation_type", ""))

    @property
    def _is_parametric(self) -> bool:
        return self._sim_type == "parametric_study"

    # ==================================================================

    def _refresh_panels(self) -> None:
        for frame in (self._overall, self._hardware):
            self.clear(frame)
        self._rank_body = None

        # Loading a different run invalidates whatever is on screen.
        figure_window.close_all()

        if self._is_parametric:
            self._render_sweep_overall()
        else:
            self._render_single_overall()
        self._render_hardware()
        self._sync_graphs_button()

    # ==================================================================
    # The summary box
    # ==================================================================
    #
    # Built twice over, from one description. _box_entries() says what the box
    # holds; _draw_box() turns that into widgets and _index_entries() turns the
    # same thing into search entries without widgets. A parametric point uses
    # both halves separately: indexed when the file loads, drawn only if
    # someone opens that point.

    def _box_entries(self, params: dict, inputs: dict) -> list:
        """What the box shows, as (kind, ...) tuples, in reading order."""
        entries = []
        for entry in _MAIN_ROWS:
            if not isinstance(entry, tuple) and entry in _CONVERGED_ONLY \
                    and self._sim_type == "hotfire":
                continue

            if entry == _VERDICT:
                reached = params.get("target_apogee_reached")
                if reached is None:
                    continue                    # a hotfire has nothing to reach
                if reached:
                    entries.append(("text", "Run status",
                                    "Rocket successfully converged to apogee", None))
                else:
                    entries.append(("text", "Run status",
                                    "Rocket could not reach target apogee", theme.ERROR))
                continue

            if entry == _SIM_TYPE:
                # A point inside a sweep is not its own kind of run, and saying
                # "parametric study" fifteen times says nothing.
                if self._is_parametric:
                    continue
                entries.append(("text", "Simulation type",
                                _SIM_TYPE_LABELS.get(self._sim_type,
                                                     self._sim_type or "Unknown"),
                                None))
                continue

            if isinstance(entry, tuple):
                key, second, label = entry
                if self._sim_type == "hotfire" and key in _CONVERGED_ONLY:
                    continue
                value = params.get(key, inputs.get(key))
                if key == "reached_apogee_agl" and value is None:
                    # Written before the AGL key existed. Show what the file
                    # actually holds and say which datum it is.
                    value = params.get("reached_apogee")
                    if value is not None:
                        key, label = "reached_apogee", f"{label} (ASL)"
                if value is None:
                    continue
                total = inputs.get(second, params.get(second)) if second else None
                entries.append(("pair", key, value, total, label))
                continue

            value = params.get(entry, inputs.get(entry))
            if value is not None:
                entries.append(("value", entry, value, None))
        return entries

    def _draw_box(self, parent, entries: list, *, logo: bool) -> None:
        box = summary_box.SummaryBox(self, parent, logo=logo)
        for entry in entries:
            kind = entry[0]
            if kind == "text":
                box.text(entry[1], entry[2], entry[3])
            elif kind == "pair":
                _kind, key, value, total, label = entry
                box.pair(key, value, total, label)
            else:
                _kind, key, value, label = entry
                box.value(key, value, label=label)

    def _index_entries(self, entries: list) -> None:
        """The same rows, findable by search without being on screen yet."""
        for entry in entries:
            kind = entry[0]
            if kind == "text":
                self.add_searchable_text(entry[1], lambda _system, t=entry[2]: t)
            elif kind == "pair":
                _kind, key, value, total, label = entry
                if total is None:
                    self.add_searchable_value(key, value, label=label)
                else:
                    self.add_searchable_text(
                        label,
                        lambda system, u=value, v=total, k=key:
                        summary_box.pair_text(u, v, k, system, self.native_system),
                        key=key)
            else:
                _kind, key, value, label = entry
                self.add_searchable_value(key, value, label=label)

    # ==================================================================
    # Overall: convergence and hotfire
    # ==================================================================

    def _render_single_overall(self) -> None:
        params = self.results.get("rocket_parameters") or {}
        inputs = self.results.get("rocket_inputs") or {}
        if not params:
            self.add_empty(self._overall, "This run produced no results block.")
            return

        self.set_row_path(_OVERALL_TAB)
        self._draw_box(self._overall, self._box_entries(params, inputs), logo=True)
        self.set_row_path()
        self._render_rest(self._overall, params, path=(_OVERALL_TAB,), extras=True)

    def _render_rest(self, parent, params: dict, *, path: tuple,
                     extras: bool) -> None:
        """Everything the run measured that the box and Hardware do not show.

        Collapsed by default. The point is that no computed result is
        invisible, not that every result deserves equal billing. `extras` adds
        the run-level settings and metadata, which belong to the file rather
        than to any one point of a sweep.
        """
        rest = {key: value for key, value in params.items()
                if key not in _SHOWN_KEYS}
        settings = {key: value
                    for key, value in (self.results.get("simulation_settings") or {}).items()
                    if key != "parametric_study_settings"} if extras else {}
        metadata = (self.results.get("metadata") or {}) if extras else {}
        if not (rest or settings or metadata):
            return

        section = self.add_section(parent, "Performance")
        section.pack(fill="x", pady=theme.PAD_XS)
        self.set_row_path(*path, "Performance")
        for key, value in rest.items():
            self.add_row(section.body, key, value)
        if settings:
            self.add_heading(section.body, "Simulation settings")
            self.set_row_path(*path, "Performance", "Simulation settings")
            for key, value in settings.items():
                self.add_row(section.body, key, value)
        if metadata:
            self.add_heading(section.body, "Run metadata")
            self.set_row_path(*path, "Performance", "Run metadata")
            for key, value in metadata.items():
                self.add_row(section.body, key, value)
        self.set_row_path()

    def _rest_keys(self, params: dict) -> list:
        return [(key, value) for key, value in params.items()
                if key not in _SHOWN_KEYS]

    # ==================================================================
    # Overall: parametric
    # ==================================================================

    def _render_sweep_overall(self) -> None:
        sweep = self.results.get("parametric_results") or {}
        if not sweep:
            self.add_empty(self._overall,
                           "This file says it is a parametric study but holds no sweep.")
            return
        self._render_best_runs(sweep)
        self._render_swept_variables(sweep)
        self._render_points(sweep)

    # ---- best runs ----------------------------------------------------

    def _render_best_runs(self, sweep: dict) -> None:
        """Rank every point by one output, and name the top few.

        The dropdown is the one from the parametric graph dialog, headers and
        all, because "which output" is the same question in both places.
        """
        from src.common.plotting import parametric_plots

        params = sweep.get("rocket_parameters") or []
        if not params:
            return

        available = parametric_plots.available_output_variables(sweep)
        common = [wire for wire in _COMMON_OUTPUTS if wire in available]
        other = [wire for wire in available if wire not in common]
        groups = [("Common outputs", [(describe(w)[0], w) for w in common]),
                  ("All other outputs", [(describe(w)[0], w) for w in other])]
        values = grouped_menu.grouped_values(groups)
        self._rank_wires = {label: wire
                            for _name, pairs in groups for label, wire in pairs}
        if not self._rank_wires:
            return

        self.add_heading(self._overall, "Best run")

        preferred = describe("Isp")[0] if "Isp" in available else ""
        self._rank_var = ctk.StringVar(
            value=grouped_menu.first_selectable(values, preferred))
        self._rank_direction = ctk.StringVar(value="highest")
        grouped_menu.guard_headers(self._rank_var, values)

        row = ctk.CTkFrame(self._overall, fg_color="transparent")
        row.pack(fill="x", pady=(0, theme.PAD_S))
        ctk.CTkLabel(row, text="Rank runs based on", anchor="w").pack(side="left")
        ctk.CTkOptionMenu(row, variable=self._rank_direction,
                          values=["highest", "lowest"], width=110,
                          dynamic_resizing=False,
                          command=lambda _v: self._refresh_ranking()).pack(
            side="left", padx=theme.PAD_XS)
        ctk.CTkOptionMenu(row, variable=self._rank_var, values=values, width=280,
                          dynamic_resizing=False,
                          command=lambda _v: self._refresh_ranking()).pack(
            side="left", padx=(0, theme.PAD_XS))
        ctk.CTkLabel(row, text="performance", anchor="w").pack(side="left")

        self._rank_body = ctk.CTkFrame(self._overall, fg_color="transparent")
        self._rank_body.pack(fill="x", pady=(0, theme.PAD_M))
        self._refresh_ranking()

    def _refresh_ranking(self) -> None:
        """Rebuild the ranked list. Cheap: at most four lines."""
        if self._rank_body is None or self._rank_var is None:
            return
        # Resolved before anything is destroyed. Clicking a group header is a
        # selection the guard is about to undo, and blanking the list on the
        # way through would make the menu flicker for no reason.
        wire = self._rank_wires.get(self._rank_var.get())
        if not wire:
            return

        for child in list(self._rank_body.winfo_children()):
            child.destroy()
        self._dynamic_labels = [(widget, build) for widget, build in self._dynamic_labels
                                if widget.winfo_exists()]

        sweep = self.results.get("parametric_results") or {}
        params = sweep.get("rocket_parameters") or []
        combinations = sweep.get("combinations") or []
        variables = list((sweep.get("variable_ranges") or {}).keys())

        scored = [(index, point.get(wire)) for index, point in enumerate(params)
                  if isinstance(point, dict)
                  and isinstance(point.get(wire), (int, float))]
        if not scored:
            summary_box.add_text_row(
                self._rank_body, "", "No run reports that output.")
            return
        scored.sort(key=lambda pair: pair[1],
                    reverse=self._rank_direction.get() != "lowest")

        native = self.native_system
        for rank, (index, value) in enumerate(scored[:_RANKED_SHOWN]):
            coords = combinations[index] if index < len(combinations) else []
            coords = coords if isinstance(coords, (list, tuple)) else [coords]
            failed = params[index].get("target_apogee_reached") is False
            label = ctk.CTkLabel(self._rank_body, anchor="w", justify="left",
                                 wraplength=900,
                                 text_color=theme.ERROR if failed else None)
            label.pack(fill="x", pady=1)
            self.add_dynamic_label(
                label, self._ranked_text(_RANK_NAMES[rank], variables, coords,
                                         wire, value, native))

        remaining = len(scored) - _RANKED_SHOWN
        if remaining > 0:
            plural = "s" if remaining != 1 else ""
            ctk.CTkLabel(self._rank_body, anchor="w",
                         text=f"… and {remaining} more run{plural}.",
                         text_color=theme.TEXT_MUTED).pack(fill="x", pady=1)

    @staticmethod
    def _ranked_text(rank_name: str, variables, coords, wire: str, value,
                     native: str):
        """"Best: Oxidizer mass flow rate = 5 kg/s; …  ·  Isp = 239.3 s"."""
        def build(system: str) -> str:
            parts = []
            for name, coordinate in zip(variables, coords):
                shown, unit = summary_box.convert(coordinate, name, system, native)
                parts.append(f"{describe(name)[0]} = {format_scalar(shown)}"
                             + (f" {unit}" if unit else ""))
            shown, unit = summary_box.convert(value, wire, system, native)
            scored = (f"{describe(wire)[0]} = {format_scalar(shown)}"
                      + (f" {unit}" if unit else ""))
            return f"{rank_name}: " + "; ".join(parts) + f"   ·   {scored}"

        return build

    # ---- what was swept -----------------------------------------------

    def _render_swept_variables(self, sweep: dict) -> None:
        ranges = sweep.get("variable_ranges") or {}
        combinations = sweep.get("combinations") or []
        if not ranges:
            return

        self.add_heading(self._overall, "Swept variables")
        native = self.native_system
        for name, values in ranges.items():
            # Each swept range is a list of stored numbers. Rendering it as a
            # string would freeze it in one unit system, so build the text from
            # a callback the unit toggle can re-run.
            label = ctk.CTkLabel(self._overall, anchor="w", justify="left",
                                 wraplength=900)
            label.pack(fill="x", pady=1)
            self.add_dynamic_label(label, self._range_text(name, values, native))

        total = len(combinations)
        plural = "s" if total != 1 else ""
        ctk.CTkLabel(self._overall, anchor="w",
                     text=f"Total combinations: {total} point{plural}").pack(
            fill="x", pady=(theme.PAD_XS, theme.PAD_M))

    @staticmethod
    def _range_text(name: str, values, native: str = "SI"):
        """A builder for "<label>: 1, 2, 3 kg/s (3 points)".

        A long sweep is elided in the middle. Twenty numbers on one line is not
        a list anyone reads; the ends are what say where the sweep starts and
        stops.
        """
        label, si_unit = describe(name)
        # Explicit category: metres are both "length" and "distance", and only
        # the key knows which.
        category = category_of_key(name)

        def build(system: str) -> str:
            shown, unit = [], ""
            for value in values:
                if isinstance(value, (int, float)) and si_unit:
                    try:
                        resolved = category or vc.category_of(si_unit)
                        source = vc.storage_unit(resolved, native)
                        unit = vc.unit_for_system(resolved, system)
                        value = vc.convert(float(value), source, unit)
                    except (ValueError, KeyError):
                        pass
                shown.append(format_scalar(value))
            if len(shown) >= _ELIDE_SWEPT_FROM:
                shown = shown[:3] + ["…"] + shown[-3:]
            plural = "s" if len(values) != 1 else ""
            listed = ", ".join(shown) + (f" {unit}" if unit else "")
            return f"{label}: {listed} ({len(values)} point{plural})"

        return build

    # ---- one card per point -------------------------------------------

    def _render_points(self, sweep: dict) -> None:
        """A collapsible per point, built when it is opened and not before.

        A hundred-point sweep is a hundred summary boxes and two thousand rows;
        building them all at load costs seconds and a great many widgets, and
        nobody reads more than a few. The values are indexed for search up
        front, though, so searching still finds a point you have never opened.
        """
        params = sweep.get("rocket_parameters") or []
        inputs = sweep.get("rocket_inputs") or []
        combinations = sweep.get("combinations") or []
        if not params:
            return

        self.add_heading(self._overall, "Results by simulation")
        variables = list((sweep.get("variable_ranges") or {}).keys())
        native = self.native_system

        for index, point in enumerate(combinations):
            if index >= len(params):
                break
            coords = point if isinstance(point, (list, tuple)) else [point]
            section = self.add_section(self._overall, f"Point {index + 1}")
            section.pack(fill="x", pady=2)
            # The subtitle carries the swept coordinates, converted with
            # everything else.
            self.add_dynamic_label(section._subtitle,          # noqa: SLF001
                                   self._coords_text(variables, coords, native))

            # A point that never hit the target apogee has to say so from the
            # collapsed row. Every point looks identical from the outside, and
            # opening fifteen of them to find the failures is not a workflow.
            #
            # The key is target_apogee_reached, NOT reached_apogee: the latter
            # is the altitude actually achieved, which the tests check
            # numerically.
            if params[index].get("target_apogee_reached") is False:
                section.set_flagged("Did not reach target apogee")

            point_inputs = inputs[index] if index < len(inputs) else {}
            entries = self._box_entries(params[index], point_inputs)
            path = (_OVERALL_TAB, f"Point {index + 1}")
            self.set_row_path(*path)
            self._index_entries(entries)
            self.set_row_path(*path, "Performance")
            for key, value in self._rest_keys(params[index]):
                self.add_searchable_value(key, value)
            self.set_row_path()

            section.set_on_toggle(
                self._point_builder(section, entries, params[index], path))

    def _point_builder(self, section, entries: list, params: dict, path: tuple):
        """Build this point's rows the first time it is opened."""
        state = {"built": False}

        def build(is_open: bool) -> None:
            if not is_open or state["built"]:
                return
            state["built"] = True
            # Already indexed, above. Registering again would show every hit
            # from this point twice.
            with self.suspend_search_index():
                self._draw_box(section.body, entries, logo=False)
                self._render_rest(section.body, params, path=path, extras=False)

        return build

    @staticmethod
    def _coords_text(variables, coords, native: str = "SI"):
        """A builder for the "ṁ = 3 kg/s · pc = 400 psi" subtitle on a point."""
        def build(system: str) -> str:
            parts = []
            for name, value in zip(variables, coords):
                shown, unit = summary_box.convert(value, name, system, native)
                parts.append(f"{describe(name)[0]} = {format_scalar(shown)}"
                             + (f" {unit}" if unit else ""))
            return "   ·   ".join(parts)

        return build

    # ==================================================================
    # Hardware & Parameters
    # ==================================================================

    def _render_hardware(self) -> None:
        """The rocket as the physics saw it, one collapsible block per CV.

        Values come from rocket_inputs where they were given and from
        rocket_parameters where they were computed, because a reader tracing
        the rocket does not care which the nozzle throat was.

        A sweep has neither: its inputs differ point by point in the swept
        variables, and everything computed differs in all of them. So a swept
        variable says so and points at the list, and the computed rows are left
        to the per-point cards, with a note saying where they went.
        """
        if self._is_parametric:
            sweep = self.results.get("parametric_results") or {}
            points = sweep.get("rocket_inputs") or []
            inputs = points[0] if points else {}
            params: dict = {}
            swept = set((sweep.get("variable_ranges") or {}).keys())
        else:
            inputs = self.results.get("rocket_inputs") or {}
            params = self.results.get("rocket_parameters") or {}
            swept = set()

        if not inputs:
            self.add_empty(self._hardware, "No inputs recorded in this file.")
            return

        for title, groups in _HARDWARE:
            section = self.add_section(self._hardware, title)
            section.pack(fill="x", pady=theme.PAD_XS)
            varies = False

            for heading, items in groups:
                rendered = []
                for item in items:
                    key, label = item if isinstance(item, tuple) else (item, None)
                    if key in swept:
                        rendered.append((key, None, label))
                        continue
                    if key in inputs:
                        rendered.append((key, inputs[key], label))
                    elif key in params:
                        rendered.append((key, params[key], label))
                    elif self._is_parametric:
                        # Computed, and computed differently for every point.
                        varies = True
                if not rendered:
                    continue
                if heading:
                    self.add_heading(section.body, heading)
                self.set_row_path(_HARDWARE_TAB, title, heading)
                for key, value, label in rendered:
                    if value is None:
                        summary_box.add_text_row(
                            section.body, label or describe(key)[0],
                            "swept, see Swept variables")
                    else:
                        self.add_row(section.body, key, value, label=label)
                self.set_row_path()

            if varies:
                ctk.CTkLabel(
                    section.body,
                    text="Computed values differ for every point in the sweep. "
                         "They are on each point's card, under Results by simulation.",
                    anchor="w", text_color=theme.TEXT_MUTED, justify="left",
                    wraplength=760,
                    font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic")).pack(
                    fill="x", pady=(theme.PAD_XS, 0))

    # ==================================================================
    # Graphs
    # ==================================================================

    def _on_graphs(self) -> None:
        if not self.results:
            self._set_status("No run open", error=True)
            return
        if self._is_parametric:
            self._open_parametric_dialog()
        else:
            self._open_flight_picker()

    # ---- convergence: flight plots -----------------------------------

    def _open_flight_picker(self) -> None:
        from src.common.plotting import steady_plots

        if not (self.results.get("flight_dict") or {}).get("time"):
            self._set_status("This run has no trajectory to plot", error=True)
            return

        chosen = show_graph_picker(
            self, steady_specs(), preselected=self._selected_plots,
            defaults=list(steady_plots.DEFAULT_SELECTION))
        if chosen is None:
            return
        self._selected_plots = chosen
        if not chosen:
            figure_window.close_all()
            self._set_status("No graphs selected")
            return

        if not self.busy(f"Rendering graphs…  0 of {len(chosen)}"):
            return

        def build():
            for name in chosen:
                try:
                    yield (steady_plots.label_of(name),
                           steady_plots.build_figure(name, self.results))
                except Exception as exc:        # noqa: BLE001
                    yield name, exc

        try:
            self.report_render(*figure_window.show_figures(
                self, build(), on_progress=self.render_progress(len(chosen))))
        finally:
            self.done_busy()

    # ---- parametric: the axis builder --------------------------------

    def _open_parametric_dialog(self) -> None:
        from src.common.plotting import parametric_plots

        sweep = self.results.get("parametric_results") or {}
        swept = parametric_plots.swept_variables(sweep)
        outputs_available = parametric_plots.available_output_variables(sweep)
        if not swept:
            self._set_status("This sweep lists no swept variables", error=True)
            return
        if not outputs_available:
            self._set_status("This sweep contains no output values", error=True)
            return

        def label_of(wire: str) -> str:
            return describe(wire)[0]

        swept_pairs = [(label_of(w), w) for w in swept]
        common = [w for w in _COMMON_OUTPUTS if w in outputs_available]
        other = [w for w in outputs_available if w not in common]
        output_groups = [
            ("Common outputs", [(label_of(w), w) for w in common]),
            ("All other outputs", [(label_of(w), w) for w in other]),
        ]

        # Hold values come from the grid the solver actually ran, formatted in
        # the page's current unit system. Offering anything off-grid would
        # promise data that doesn't exist.
        ranges = sweep.get("variable_ranges") or {}
        hold_options = {}
        for wire in swept:
            options = []
            for value in ranges.get(wire, []):
                shown, unit = summary_box.convert(value, wire, self.system,
                                                  self.native_system)
                display = format_scalar(shown) + (f" {unit}" if unit else "")
                options.append((display, value))     # keep the stored value
            hold_options[wire] = options

        spec_2d, spec_3d = show_parametric_graph_dialog(
            self, swept_pairs=swept_pairs, output_groups=output_groups,
            hold_options=hold_options, label_of=label_of)
        if spec_2d is None and spec_3d is None:
            return

        if not self.busy("Drawing parametric graphs…"):
            return
        try:
            self._render_parametric(sweep, spec_2d, spec_3d)
        finally:
            self.done_busy()

    def _render_parametric(self, sweep: dict, spec_2d, spec_3d) -> None:
        from src.common.plotting import parametric_plots

        def axis(wire: str):
            """(label with unit, stored->display transform) for one axis."""
            label, si_unit = describe(wire)
            if not si_unit:
                return label, None
            try:
                resolved = category_of_key(wire) or vc.category_of(si_unit)
                source = vc.storage_unit(resolved, self.native_system)
                target = vc.unit_for_system(resolved, self.system)
            except (ValueError, KeyError):
                return label, None
            labelled = f"{label} ({target})"
            if target == source:
                return labelled, None
            return labelled, (lambda v, _s=source, _t=target:
                              vc.convert(float(v), _s, _t))

        def hold_label(wire: str, value) -> str:
            label, transform = axis(wire)
            shown = transform(value) if transform else value
            return f"{label} = {format_scalar(shown)}"

        def build():
            if spec_2d:
                x_label, x_fn = axis(spec_2d["x"])
                y_label, y_fn = axis(spec_2d["y"])
                try:
                    yield f"{y_label} vs {x_label}", parametric_plots.plot_parametric_2d(
                        sweep, spec_2d["x"], spec_2d["y"],
                        holds=spec_2d.get("holds"),
                        x_label=x_label, y_label=y_label,
                        x_transform=x_fn, y_transform=y_fn,
                        hold_label_fn=hold_label)
                except Exception as exc:        # noqa: BLE001
                    yield "2D plot", exc
            if spec_3d:
                x_label, x_fn = axis(spec_3d["x"])
                y_label, y_fn = axis(spec_3d["y"])
                z_label, z_fn = axis(spec_3d["z"])
                try:
                    yield f"{z_label} vs {x_label}, {y_label}", parametric_plots.plot_parametric_3d(
                        sweep, spec_3d["x"], spec_3d["y"], spec_3d["z"],
                        holds=spec_3d.get("holds"),
                        x_label=x_label, y_label=y_label, z_label=z_label,
                        x_transform=x_fn, y_transform=y_fn, z_transform=z_fn,
                        hold_label_fn=hold_label)
                except Exception as exc:        # noqa: BLE001
                    yield "3D surface", exc

        # one 2D and one 3D at most, whichever the user asked for
        total = int(bool(spec_2d)) + int(bool(spec_3d))
        self.report_render(*figure_window.show_figures(
            self, build(), on_progress=self.render_progress(total)))

    def reset_to_defaults(self) -> None:
        # Leaving the page closes the graph windows; they hold figures, and a
        # window whose run is no longer open is just confusing.
        figure_window.close_all()
