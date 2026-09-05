"""
Steady results.

Four tabs, but only the ones that apply to the run are shown:

    Performance         computed outputs. Hotfire and convergence.
    Inputs              what was fed in, echoed back. Always.
    Trajectory          flight summary. Convergence only.
    Parametric sweep    one collapsible block per swept point. Parametric only.

A parametric study produces one performance block and one trajectory PER
POINT, so there is no single one of either; those tabs are hidden rather than
left to say "look in the sweep tab". Conversely the sweep tab is hidden for
everything else. See ResultsPage.set_tab_visible.

Points that never reached the target apogee are flagged red on their collapsed
header, from the target_apogee_reached flag the steady engine sets.
"""

from __future__ import annotations

import customtkinter as ctk

from src.common import variable_conversions as vc
from src.ui.app import theme
from src.ui.app import field_registry as registry
from src.ui.app.pages.results_page import ResultsPage
from src.ui.app.widgets.graph_picker import show_graph_picker, steady_specs
from src.ui.app.widgets.kv_row import category_of_key, describe, format_scalar
from src.ui.app.widgets import figure_window
from src.ui.app.widgets.parametric_graph_dialog import show_parametric_graph_dialog
from src.ui.app.widgets.section import CollapsibleSection
from src.ui.app.widgets.tooltip import Tooltip

# The handful of outputs anyone actually plots against a swept variable. They
# go at the top of the parametric dialog's output dropdown; everything else
# follows under a second header.
_COMMON_OUTPUTS = (
    "Isp", "thrust", "burntime", "total_impulse",
    "average_oxidizer_to_fuel_ratio", "thrust_to_weight_ratio",
)


class SteadyResultsPage(ResultsPage):
    TITLE = "Steady results"
    KIND = "steady"

    def _build_tabs(self) -> None:
        self._performance = self.add_tab("Performance")
        self._inputs = self.add_tab("Inputs")
        self._trajectory = self.add_tab("Trajectory")
        self._sweep = self.add_tab("Parametric sweep")
        self._selected_plots = None

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

    # ==================================================================

    def _refresh_panels(self) -> None:
        for frame in (self._performance, self._inputs,
                      self._trajectory, self._sweep):
            self.clear(frame)

        # Loading a different run invalidates whatever is on screen.
        figure_window.close_all()

        # A parametric study computes one result set per point, so there is no
        # single performance block and no single trajectory. Those two tabs
        # could only ever say "look in the sweep tab", so hide them instead.
        parametric = self._sim_type == "parametric_study"
        self.set_tab_visible("Performance", not parametric)
        self.set_tab_visible("Trajectory", not parametric)
        self.set_tab_visible("Parametric sweep", parametric)

        if not parametric:
            self._render_performance()
            self._render_trajectory()
        self._render_inputs()
        self._render_sweep()
        self._sync_graphs_button()

    def _render_performance(self) -> None:
        params = self.results.get("rocket_parameters") or {}
        if params:
            self.add_dict(self._performance, "Rocket parameters", params)
            return
        if self._sim_type == "parametric_study":
            self.add_empty(
                self._performance,
                "A parametric study computes one set of results per swept "
                "point, so there's no single performance block.\n\n"
                "Open the Parametric sweep tab.")
        else:
            self.add_empty(self._performance,
                           "This run produced no performance block.")

    def _render_inputs(self) -> None:
        inputs = self.results.get("rocket_inputs") or {}
        settings = dict(self.results.get("simulation_settings") or {})
        metadata = self.results.get("metadata") or {}

        # Pull the sweep definition out and render it under its own heading.
        # Left in place it inherits the chained title and comes out as
        # "Simulation settings — parametric_study_settings — chamber_pressure",
        # which is a mouthful for what is just "chamber pressure".
        sweep_settings = settings.pop("parametric_study_settings", None)

        if metadata:
            self.add_dict(self._inputs, "Metadata", metadata)
        if inputs:
            # Post-conversion, so radii rather than the diameters that were
            # typed. The registry labels both, so they read the same either way.
            self.add_dict(self._inputs, "Rocket inputs", inputs)
        if settings:
            self.add_dict(self._inputs, "Simulation settings", settings)
        if isinstance(sweep_settings, dict) and sweep_settings:
            self.add_dict(self._inputs, "Parametric settings", sweep_settings,
                          child_title=lambda _parent, key: registry.label(key)
                          if registry.has(key) else key)
        if not (inputs or settings or metadata or sweep_settings):
            self.add_empty(self._inputs, "No inputs recorded in this file.")

    def _render_trajectory(self) -> None:
        flight = self.results.get("flight_dict") or {}
        if flight:
            self.add_heading(self._trajectory, "Flight summary")
            # Arrays, one per quantity. Several hundred numbers per row helps
            # nobody, so summarise here and leave the full series to the CSV.
            for name, series in flight.items():
                if not isinstance(series, (list, tuple)) or not series:
                    self.add_row(self._trajectory, name, series)
                    continue
                numeric = [v for v in series if isinstance(v, (int, float))]
                if not numeric:
                    continue
                self.add_row(self._trajectory, f"{name}_max", max(numeric))
                self.add_row(self._trajectory, f"{name}_final", numeric[-1])
            return

        if self._sim_type == "parametric_study":
            self.add_empty(
                self._trajectory,
                "A parametric study flies once per swept point, so there's no "
                "single trajectory here.\n\n"
                "Open the Parametric sweep tab.")
        else:
            self.add_empty(
                self._trajectory,
                "A hotfire computes performance at one operating point and "
                "never flies, so there's no trajectory.")

    # ==================================================================
    # The sweep
    # ==================================================================

    def _render_sweep(self) -> None:
        sweep = self.results.get("parametric_results") or {}
        if not sweep:
            self.add_empty(self._sweep,
                           "Not a parametric study. Run one to see a sweep here.")
            return

        ranges = sweep.get("variable_ranges") or {}
        combinations = sweep.get("combinations") or []
        params = sweep.get("rocket_parameters") or []
        flights = sweep.get("flight_data") or []

        native = self.native_system
        self.add_heading(self._sweep, "What was swept")
        for name, values in ranges.items():
            # Each swept range is a list of SI numbers. Rendering it as a
            # string would freeze it in SI, so build the text from a callback
            # the unit toggle can re-run.
            label = ctk.CTkLabel(self._sweep, anchor="w", justify="left",
                                 wraplength=760)
            label.pack(fill="x", pady=1)
            self.add_dynamic_label(label, self._range_text(name, values, native))

        self.add_row(self._sweep, "total_combinations", len(combinations))

        # One collapsed block per point. A sweep of 15 points times 20
        # parameters is 300 rows; collapsed headers make it possible to find
        # the point you want without scrolling through all of them.
        self.add_heading(self._sweep, f"Results by point ({len(combinations)})")
        variables = list(ranges.keys())
        for index, point in enumerate(combinations):
            if index >= len(params):
                break
            coords = point if isinstance(point, (list, tuple)) else [point]
            section = CollapsibleSection(self._sweep, f"Point {index + 1}",
                                         start_open=False)
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
            # is the altitude actually achieved, in metres, which the tests
            # check numerically.
            if params[index].get("target_apogee_reached") is False:
                section.set_flagged("Did not reach target apogee")

            self.add_dict(section.body, "Rocket parameters", params[index])
            if index < len(flights) and isinstance(flights[index], dict):
                self._render_flight_summary(section.body, flights[index])

    def _render_flight_summary(self, parent, flight: dict) -> None:
        self.add_heading(parent, "Flight")
        for name, series in flight.items():
            if not isinstance(series, (list, tuple)) or not series:
                continue
            numeric = [v for v in series if isinstance(v, (int, float))]
            if numeric:
                self.add_row(parent, f"{name}_max", max(numeric))

    # ---- unit-aware text builders ------------------------------------

    @staticmethod
    def _range_text(name: str, values, native: str = "SI"):
        """A builder for '<label> (unit): v1, v2, v3', re-run on unit change."""
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
            heading = f"{label} ({unit})" if unit else label
            return f"{heading}:  {len(values)} points — {', '.join(shown)}"

        return build

    @staticmethod
    def _coords_text(variables, coords, native: str = "SI"):
        """A builder for the 'ṁ = 3 kg/s, pc = 400 psi' subtitle on a point."""
        def build(system: str) -> str:
            parts = []
            for name, value in zip(variables, coords):
                label, si_unit = describe(name)
                unit = ""
                if isinstance(value, (int, float)) and si_unit:
                    try:
                        resolved = (category_of_key(name)
                                    or vc.category_of(si_unit))
                        source = vc.storage_unit(resolved, native)
                        unit = vc.unit_for_system(resolved, system)
                        value = vc.convert(float(value), source, unit)
                    except (ValueError, KeyError):
                        pass
                parts.append(f"{label} = {format_scalar(value)}"
                             + (f" {unit}" if unit else ""))
            return "   ·   ".join(parts)

        return build

    # ==================================================================
    # Graphs
    # ==================================================================

    def _on_graphs(self) -> None:
        if not self.results:
            self._set_status("No run open", error=True)
            return
        if self._sim_type == "parametric_study":
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

        self._set_status(f"Rendering graphs…  0 of {len(chosen)}")
        self.update_idletasks()

        def build():
            for name in chosen:
                try:
                    yield (steady_plots.label_of(name),
                           steady_plots.build_figure(name, self.results))
                except Exception as exc:        # noqa: BLE001
                    yield name, exc

        self.report_render(*figure_window.show_figures(
            self, build(), on_progress=self.render_progress(len(chosen))))

    # ---- parametric: the axis builder --------------------------------

    def _open_parametric_dialog(self) -> None:
        from src.common.plotting import parametric_plots

        sweep = self.results.get("parametric_results") or {}
        swept = parametric_plots.swept_variables(sweep)
        outputs = parametric_plots.available_output_variables(sweep)
        if not swept:
            self._set_status("This sweep lists no swept variables", error=True)
            return
        if not outputs:
            self._set_status("This sweep contains no output values", error=True)
            return

        def label_of(wire: str) -> str:
            return describe(wire)[0]

        swept_pairs = [(label_of(w), w) for w in swept]
        common = [w for w in _COMMON_OUTPUTS if w in outputs]
        other = [w for w in outputs if w not in common]
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
            _label, si_unit = describe(wire)
            options = []
            for value in ranges.get(wire, []):
                shown, unit = value, ""
                if isinstance(value, (int, float)) and si_unit:
                    try:
                        resolved = (category_of_key(wire)
                                    or vc.category_of(si_unit))
                        source = vc.storage_unit(resolved, self.native_system)
                        unit = vc.unit_for_system(resolved, self.system)
                        shown = vc.convert(float(value), source, unit)
                    except (ValueError, KeyError):
                        pass
                display = format_scalar(shown) + (f" {unit}" if unit else "")
                options.append((display, value))     # keep the SI value
            hold_options[wire] = options

        spec_2d, spec_3d = show_parametric_graph_dialog(
            self, swept_pairs=swept_pairs, output_groups=output_groups,
            hold_options=hold_options, label_of=label_of)
        if spec_2d is None and spec_3d is None:
            return

        self._set_status("Drawing parametric graphs…")
        self.update_idletasks()
        self._render_parametric(sweep, spec_2d, spec_3d)

    def _render_parametric(self, sweep: dict, spec_2d, spec_3d) -> None:
        from src.common.plotting import parametric_plots

        def axis(wire: str):
            """(label with unit, SI->display transform) for one axis."""
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
