"""
SteadyResultsPage — the page users land on after a steady simulation
finishes.

Two tabs on the left (Rocket inputs, Sim outputs), a sidebar on the
right with four buttons:

    - Copy to clipboard         → overall performance as one TSV row
    - Export to sheets (.csv)   → all critical data as one CSV row
    - Show select graphs        → altitude / velocity / thrust vs time
    - Show all graphs           → same as above for now — steady only has
                                  the flight_dict time series to work with

For hotfire (no flight_dict) the graph buttons fall back to a "no
time-series available" message.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.ui.app import theme, results_utils
from src.ui.app.services import i18n
from src.ui.app.widgets.graph_picker import GraphPicker
from src.ui.app.widgets.search_entry import SearchEntry
from src.ui.app.widgets.help_icon import HelpIcon


class SteadyResultsPage(ctk.CTkFrame):
    TITLE = "Steady simulation results"

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate
        self._result_path: Path | None = None
        self._result_dict: dict | None = None
        self._unit_system: str = "SI"     # SI / IMP / MRT
        self._unit_buttons: dict = {}
        # Cached row widgets — populated by _refresh_panels(), iterated by
        # _set_unit_system() so we can update in place instead of rebuilding.
        self._rows: list = []
        self._build()

    # ===================================================================
    # Layout
    # ===================================================================

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=220)
        self.grid_rowconfigure(1, weight=1)   # tabview row expands

        # ---- filter bar (row 0, spans both columns) ---------------------
        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.grid(row=0, column=0, columnspan=2, sticky="ew",
                        padx=theme.PAD_M, pady=(theme.PAD_M, 0))
        self._filter_var = ctk.StringVar()
        SearchEntry(
            filter_row, textvariable=self._filter_var,
            placeholder=i18n.t("filter.placeholder"),
        ).pack(fill="x", expand=True)
        self._filter_var.trace_add("write", lambda *_: self._apply_filter())

        self.tabs = ctk.CTkTabview(self, anchor="w")
        self.tabs.grid(row=1, column=0, sticky="nsew",
                       padx=(theme.PAD_M, theme.PAD_S), pady=theme.PAD_M)

        self._inputs_tab  = self.tabs.add("Rocket inputs")
        self._outputs_tab = self.tabs.add("Sim outputs")

        # scrollable frames inside each tab, refilled by _refresh_panels
        self._inputs_scroll  = ctk.CTkScrollableFrame(self._inputs_tab, label_text="")
        self._inputs_scroll.pack(fill="both", expand=True)
        self._outputs_scroll = ctk.CTkScrollableFrame(self._outputs_tab, label_text="")
        self._outputs_scroll.pack(fill="both", expand=True)

        # sidebar
        sidebar = ctk.CTkFrame(self, fg_color="transparent")
        sidebar.grid(row=1, column=1, sticky="ns",
                     padx=(theme.PAD_S, theme.PAD_M), pady=theme.PAD_M)
        self._build_sidebar(sidebar)

        # status line
        self.status_label = ctk.CTkLabel(
            self, text="", anchor="w",
            text_color=("gray35", "gray65"),
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
        )
        self.status_label.grid(row=2, column=0, columnspan=2, sticky="ew",
                               padx=theme.PAD_M, pady=(0, theme.PAD_S))

    def _build_sidebar(self, parent) -> None:
        ctk.CTkLabel(parent, text=i18n.t("action.actions"),
                     font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
                     anchor="w").pack(fill="x", pady=(0, theme.PAD_S))

        ctk.CTkButton(parent, text=i18n.t("action.copy"),
                      width=200, height=36,
                      command=self._on_copy).pack(pady=theme.PAD_XS)
        ctk.CTkButton(parent, text=i18n.t("action.export_csv"),
                      width=200, height=36,
                      command=self._on_export).pack(pady=theme.PAD_XS)
        ctk.CTkButton(parent, text="Show in folder",
                      width=200, height=36,
                      command=self._on_show_in_folder).pack(pady=theme.PAD_XS)

        ctk.CTkLabel(parent, text=i18n.t("action.graphs"),
                     font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold"),
                     anchor="w").pack(fill="x", pady=(theme.PAD_L, theme.PAD_XS))

        ctk.CTkButton(parent, text=i18n.t("action.show_graphs"),
                      width=200, height=36,
                      command=self._on_open_graph_picker).pack(pady=theme.PAD_XS)

        # Parametric graph — built once, packed only when the loaded
        # result actually contains a parametric_results block.
        self._parametric_btn = ctk.CTkButton(
            parent, text="Parametric graph",
            width=200, height=36,
            command=self._on_open_parametric_dialog,
        )
        # NOT packed here; _refresh_panels controls visibility.

        # Units header + inline help-icon.  Saved as an attribute so
        # dynamically-shown buttons (like the Parametric graph button)
        # can pack themselves BEFORE it and land in the right slot.
        units_row = ctk.CTkFrame(parent, fg_color="transparent")
        self._sidebar_units_row = units_row
        units_row.pack(fill="x", pady=(theme.PAD_L, theme.PAD_XS))
        ctk.CTkLabel(units_row, text=i18n.t("action.units"),
                     font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold"),
                     anchor="w").pack(side="left")
        HelpIcon(units_row, i18n.t("help.units")).pack(side="left",
                                                       padx=(theme.PAD_XS, 0))
        self._unit_buttons = results_utils.build_unit_buttons(
            parent, self._unit_system, on_change=self._set_unit_system,
        )

    # ===================================================================
    # Data-in
    # ===================================================================

    def load_results(self, path: Path, result_dict: dict) -> None:
        self._result_path = path
        self._result_dict = result_dict
        self._refresh_panels()
        self._set_status(f"Loaded results from {path.name}")

    def on_show(self) -> None:
        # If we've been navigated to without load_results having been
        # called, keep whatever was previously shown.
        if self._result_dict is None:
            self._set_status("No results loaded yet.")

    def reset_to_defaults(self) -> None:
        self._result_path = None
        self._result_dict = None
        self._clear_scroll(self._inputs_scroll)
        self._clear_scroll(self._outputs_scroll)
        self._rows = []
        self._unit_system = "SI"
        if self._unit_buttons:
            results_utils.refresh_unit_buttons(self._unit_buttons, self._unit_system)
        # Hide the Parametric graph button until a parametric result
        # is loaded again.
        if hasattr(self, "_parametric_btn") and self._parametric_btn.winfo_ismapped():
            self._parametric_btn.pack_forget()
        self._set_status("")

    # ===================================================================
    # Panel population
    # ===================================================================

    def _clear_scroll(self, frame) -> None:
        for w in frame.winfo_children():
            w.destroy()

    def _refresh_panels(self) -> None:
        self._clear_scroll(self._inputs_scroll)
        self._clear_scroll(self._outputs_scroll)
        self._rows = []
        if self._result_dict is None:
            return

        # Inputs tab
        self._render_dict_section(
            self._inputs_scroll, "Rocket inputs",
            self._result_dict.get("rocket_inputs") or {},
        )
        self._render_dict_section(
            self._inputs_scroll, "Simulation settings",
            self._result_dict.get("simulation_settings") or {},
        )

        # Outputs tab
        rp = self._result_dict.get("rocket_parameters")
        if isinstance(rp, dict):
            self._render_dict_section(
                self._outputs_scroll, "Simulation outputs (rocket_parameters)",
                rp,
            )
        fd = self._result_dict.get("flight_dict")
        if isinstance(fd, dict) and fd.get("altitude"):
            # Only show summary numbers, not the full time series.
            alts   = fd.get("altitude", [])
            times  = fd.get("time", [])
            vels   = fd.get("velocity", [])
            self._render_dict_section(
                self._outputs_scroll, "Ascent summary",
                {
                    "apogee (m)":         max(alts) if alts else None,
                    "time to apogee (s)": times[-1] if times else None,
                    "peak velocity (m/s)": max(vels) if vels else None,
                    "trajectory samples":  len(times),
                },
            )
        param = self._result_dict.get("parametric_results")
        is_parametric = isinstance(param, dict)
        if is_parametric:
            combos = param.get("combinations") or []
            self._render_dict_section(
                self._outputs_scroll, "Parametric study summary",
                {
                    "combinations simulated": len(combos),
                    "variables swept":        ";".join(
                        list((param.get("variable_ranges") or {}).keys())
                    ),
                },
            )

        # Show / hide the Parametric graph button depending on whether
        # this run is a parametric study.  pack_forget when non-parametric
        # so the button vanishes cleanly; pack when it is.
        if is_parametric:
            if not self._parametric_btn.winfo_ismapped():
                # Pack BEFORE the units row so it lands right under the
                # "Show graphs..." button instead of at the bottom.
                self._parametric_btn.pack(
                    pady=theme.PAD_XS,
                    before=self._sidebar_units_row,
                )
        else:
            if self._parametric_btn.winfo_ismapped():
                self._parametric_btn.pack_forget()

    def _render_dict_section(self, parent, title: str, d: dict) -> None:
        """A titled section with a two-column label:value grid."""
        if not d:
            return
        ctk.CTkLabel(parent, text=title,
                     font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
                     anchor="w").pack(fill="x", pady=(theme.PAD_S, theme.PAD_XS))
        for key, value in d.items():
            self._render_kv_row(parent, key, value)

    def _render_kv_row(self, parent, key: str, value) -> None:
        """3-column row: pretty-name | value (converted to current unit
        system) | unit label.  Delegates to the shared helper and caches
        the widget so unit-system toggles can update it in place."""
        row = results_utils.render_kv_row(parent, key, value, self._unit_system)
        self._rows.append(row)

    def _set_unit_system(self, system: str) -> None:
        if system == self._unit_system:
            return
        self._unit_system = system
        results_utils.refresh_unit_buttons(self._unit_buttons, system)
        # Fast path: iterate the cached KVRow widgets and re-configure
        # their value/unit labels rather than destroying and rebuilding
        # every panel.  Roughly 10× faster than _refresh_panels() and
        # eliminates the visible relayout flicker.
        for row in self._rows:
            try:
                row.update_system(system)
            except AttributeError:
                # non-KVRow row (shouldn't happen, but stay safe)
                pass
        # Unit-label text just changed — re-apply the filter so rows
        # containing e.g. "psi" still match after switching to IMP.
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Show/hide cached KVRow widgets based on the current filter
        query.  Two passes: first pack_forget everything, then re-pack
        matching rows in original creation order.  Full re-pack keeps
        the sibling ordering correct as the filter narrows and widens."""
        try:
            query = self._filter_var.get()
        except AttributeError:
            return
        # Pass 1 — hide everything (cheap, just pack manager state).
        for row in self._rows:
            try:
                if row.winfo_manager() == "pack":
                    row.pack_forget()
            except AttributeError:
                pass
        # Pass 2 — re-pack matches in creation order.
        for row in self._rows:
            try:
                if row.matches(query):
                    row.pack(fill="x", pady=1)
            except AttributeError:
                pass

    # ===================================================================
    # Actions
    # ===================================================================

    def _on_show_in_folder(self) -> None:
        if self._result_path is None or not self._result_path.exists():
            messagebox.showinfo(
                "No file to show",
                "There's no saved file for this run yet.",
            )
            return
        from src.ui.app.services.os_utils import reveal_in_file_explorer
        reveal_in_file_explorer(self._result_path)

    def _on_copy(self) -> None:
        if self._result_dict is None:
            messagebox.showinfo("Nothing to copy", "No results loaded.")
            return
        rp = self._result_dict.get("rocket_parameters") or {}
        flat = results_utils.flatten_dict(rp)
        if not flat:
            messagebox.showinfo("Nothing to copy",
                                "This run has no rocket_parameters block.")
            return
        pairs = results_utils.flat_to_display_pairs(flat, self._unit_system)
        results_utils.copy_pairs_to_clipboard(self, pairs)
        self._set_status(
            f"Copied {len(pairs)} performance values "
            f"(in {self._unit_system}) to clipboard."
        )

    def _on_export(self) -> None:
        if self._result_dict is None:
            messagebox.showinfo("Nothing to export", "No results loaded.")
            return
        payload = {
            "rocket_inputs":        self._result_dict.get("rocket_inputs")        or {},
            "simulation_settings":  self._result_dict.get("simulation_settings")  or {},
            "rocket_parameters":    self._result_dict.get("rocket_parameters")    or {},
        }
        flat = results_utils.flatten_dict(payload)
        if not flat:
            messagebox.showinfo("Nothing to export",
                                "No exportable data in this result file.")
            return
        pairs = results_utils.flat_to_display_pairs(flat, self._unit_system)

        default_name = self._default_export_name()
        path = filedialog.asksaveasfilename(
            title="Export steady results (one-row CSV)",
            initialfile=default_name,
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            results_utils.export_pairs_to_csv(Path(path), pairs)
            self._set_status(f"Exported to {Path(path).name} (in {self._unit_system})")
        except Exception as exc:
            messagebox.showerror("Export failed",
                                 f"{type(exc).__name__}: {exc}")

    def _on_open_graph_picker(self) -> None:
        if self._result_dict is None:
            messagebox.showinfo("No results", "No results loaded.")
            return
        fd = self._result_dict.get("flight_dict")
        if not isinstance(fd, dict) or not fd.get("time"):
            messagebox.showinfo(
                "No time-series available",
                "This simulation type doesn't produce a "
                "trajectory time series. Nothing to plot.",
            )
            return
        # (pretty_label, wire_key, default_checked)
        items = [
            (i18n.t("graph.st.kinematics"), "kinematics", True),
            (i18n.t("graph.st.thrust"),     "thrust",     True),
            (i18n.t("graph.st.forces"),     "forces",     False),
        ]
        GraphPicker(self, items=items, on_confirm=self._render_steady_graphs)

    def _render_steady_graphs(self, selected: list[str]) -> None:
        if not selected:
            return
        fd = self._result_dict.get("flight_dict") or {}
        # Lazy-import matplotlib so cold startup stays fast.
        import matplotlib.pyplot as plt
        from src.ui.app.services.mpl_bringup import lift_all_figures

        t   = fd.get("time", [])
        alt = fd.get("altitude", [])
        vel = fd.get("velocity", [])
        acc = fd.get("acceleration", [])
        thr = fd.get("thrust", [])
        drag= fd.get("drag_force", [])
        grv = fd.get("grav_force", [])

        if "kinematics" in selected:
            fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True,
                                     num="Kinematics")
            axes[0].plot(t, alt); axes[0].set_ylabel("Altitude [m]")
            axes[1].plot(t, vel); axes[1].set_ylabel("Velocity [m/s]")
            axes[2].plot(t, acc); axes[2].set_ylabel("Accel [m/s²]")
            axes[2].set_xlabel("Time [s]")
            for a in axes:
                a.grid(True, linestyle="--", alpha=0.5)
            fig.suptitle("Rocket kinematics", fontweight="bold")
            fig.tight_layout(rect=[0, 0, 1, 0.96])

        if "thrust" in selected:
            fig2, ax2 = plt.subplots(figsize=(10, 5), num="Thrust curve")
            ax2.plot(t, thr, color="#e63946")
            ax2.set_xlabel("Time [s]"); ax2.set_ylabel("Thrust [N]")
            ax2.grid(True, linestyle="--", alpha=0.5)
            fig2.suptitle("Thrust curve", fontweight="bold")
            fig2.tight_layout(rect=[0, 0, 1, 0.96])

        if "forces" in selected:
            fig3, ax3 = plt.subplots(figsize=(10, 5), num="Forces")
            if thr:  ax3.plot(t, thr,  label="Thrust",  color="#e63946")
            if drag: ax3.plot(t, drag, label="Drag",    color="#118ab2")
            if grv:  ax3.plot(t, grv,  label="Gravity", color="#2a9d8f")
            ax3.axhline(0, color="black", linewidth=0.5)
            ax3.set_xlabel("Time [s]"); ax3.set_ylabel("Force [N]")
            ax3.grid(True, linestyle="--", alpha=0.5)
            ax3.legend(loc="best")
            fig3.suptitle("Forces vs. time", fontweight="bold")
            fig3.tight_layout(rect=[0, 0, 1, 0.96])

        # `plt.show(block=False)` returns immediately so we can lift the
        # freshly-created windows to the front (Windows sometimes lets
        # them slip behind the main UI during initial paint).
        plt.show(block=False)
        lift_all_figures()

    # ===================================================================
    # Parametric graph
    # ===================================================================

    # Output wire keys we consider "common" / most likely to be plotted.
    # These bubble to the top of the output-variable dropdown.  Any other
    # output variable falls into the second group.
    _COMMON_OUTPUT_WIRES = (
        "Isp",
        "average_oxidizer_to_fuel_ratio",
        "burntime",
        "thrust",
        "total_impulse",
        "thrust_to_weight_ratio",
    )

    def _on_open_parametric_dialog(self) -> None:
        """Open the modal for building 2D / 3D parametric graphs."""
        if self._result_dict is None:
            messagebox.showinfo("No results", "No results loaded.")
            return
        param = self._result_dict.get("parametric_results")
        if not isinstance(param, dict):
            messagebox.showinfo(
                "Not a parametric run",
                "This isn't a parametric-study result, so there's nothing "
                "to plot.",
            )
            return

        # Lazy imports so cold startup isn't slowed by matplotlib.
        from src.backend.steady.parametric_plots import (
            swept_variables, available_output_variables,
        )
        from src.ui.app.services.pretty_names import get_field_info
        from src.ui.app.widgets.parametric_graph_dialog import (
            ParametricGraphDialog,
        )

        swept_wire = swept_variables(param)
        if not swept_wire:
            messagebox.showinfo(
                "No swept variables",
                "The parametric result doesn't list any swept variables.",
            )
            return

        output_wire = available_output_variables(param)
        if not output_wire:
            messagebox.showinfo(
                "No output variables",
                "The parametric result doesn't contain any output values.",
            )
            return

        def _pretty(wire: str) -> str:
            try:
                pretty, _kind, _si = get_field_info(wire)
                return pretty or wire
            except Exception:
                return wire

        swept_pairs = [(_pretty(w), w) for w in swept_wire]

        # Split output vars into the two dropdown groups, preserving the
        # order defined in _COMMON_OUTPUT_WIRES for the top group.
        common_wires = [w for w in self._COMMON_OUTPUT_WIRES if w in output_wire]
        other_wires  = [w for w in output_wire if w not in self._COMMON_OUTPUT_WIRES]
        output_var_groups = [
            ("Common outputs",    [(_pretty(w), w) for w in common_wires]),
            ("All other outputs", [(_pretty(w), w) for w in other_wires]),
        ]

        # Build the hold picker's per-var data: for each swept variable,
        # a list of (display_string, si_value) pairs drawn from the actual
        # grid the sim ran on, formatted in the current unit system.
        from src.ui.app.services.pretty_names import (
            unit_for_system, format_unit_label,
        )
        from src.ui.app import display as display_mod
        variable_ranges = param.get("variable_ranges") or {}
        system = self._unit_system

        def _format_grid_value(v):
            if isinstance(v, float) and v == int(v) and abs(v) < 1e15:
                return str(int(v))
            try:
                return f"{float(v):.6g}"
            except Exception:
                return str(v)

        hold_value_options: dict[str, list] = {}
        hold_unit_labels:   dict[str, str]  = {}
        for wire in swept_wire:
            raw_values = list(variable_ranges.get(wire) or [])
            try:
                _p, kind, si_unit = get_field_info(wire)
            except Exception:
                kind, si_unit = None, None
            if kind and si_unit:
                target = unit_for_system(wire, kind, system)
                hold_unit_labels[wire] = format_unit_label(target)
                pairs = []
                for raw in raw_values:
                    try:
                        display_val = display_mod.convert(
                            float(raw), si_unit, target, kind,
                        )
                    except Exception:
                        display_val = raw
                    pairs.append((_format_grid_value(display_val), float(raw)))
                hold_value_options[wire] = pairs
            else:
                # Unitless swept var — display raw values, no unit label.
                hold_unit_labels[wire] = ""
                hold_value_options[wire] = [
                    (_format_grid_value(v), float(v)) for v in raw_values
                ]

        ParametricGraphDialog(
            self,
            swept_vars=swept_pairs,
            output_var_groups=output_var_groups,
            default_output="Isp",
            hold_value_options=hold_value_options,
            hold_unit_labels=hold_unit_labels,
            on_confirm=self._render_parametric_graphs,
        )

    def _render_parametric_graphs(self, spec_2d, spec_3d) -> None:
        """Callback from the parametric dialog.  Opens each requested
        graph in its own matplotlib window (with values + axis labels
        converted into the results page's current SI/IMP/MRT system)
        and lifts them to the front."""
        if spec_2d is None and spec_3d is None:
            return
        param = (self._result_dict or {}).get("parametric_results") or {}
        if not param:
            return

        from src.backend.steady.parametric_plots import (
            plot_parametric_2d, plot_parametric_3d,
        )
        from src.ui.app.services.pretty_names import (
            get_field_info, unit_for_system, format_unit_label,
        )
        from src.ui.app import display as display_mod
        from src.ui.app.services.mpl_bringup import lift_all_figures

        system = self._unit_system

        def _axis_info(wire: str):
            """Return (labeled_axis_string, transform_callable) for a
            given wire key, honouring the current unit system.
            Transform is identity when the field is unitless."""
            try:
                pretty, kind, si_unit = get_field_info(wire)
            except Exception:
                return (wire, lambda v: v)
            pretty = pretty or wire
            if not kind or not si_unit:
                return (pretty, lambda v: v)
            target = unit_for_system(wire, kind, system)
            unit_display = format_unit_label(target)
            label = f"{pretty} ({unit_display})"
            if target == si_unit:
                return (label, lambda v: v)
            def _fn(v, _kind=kind, _si=si_unit, _t=target):
                try:
                    return display_mod.convert(float(v), _si, _t, _kind)
                except Exception:
                    return v
            return (label, _fn)

        def _hold_label(wire: str, si_value) -> str:
            """Format a held value with pretty name + display unit."""
            try:
                pretty, kind, si_unit = get_field_info(wire)
            except Exception:
                return f"{wire} = {si_value}"
            pretty = pretty or wire
            if not kind or not si_unit:
                return f"{pretty} = {si_value}"
            target = unit_for_system(wire, kind, system)
            unit_display = format_unit_label(target)
            try:
                display_val = display_mod.convert(
                    float(si_value), si_unit, target, kind,
                )
            except Exception:
                display_val = si_value
            if isinstance(display_val, float) and display_val == int(display_val):
                num_str = str(int(display_val))
            else:
                try:
                    num_str = f"{float(display_val):.6g}"
                except Exception:
                    num_str = str(display_val)
            return f"{pretty} = {num_str} {unit_display}"

        errors = []
        if spec_2d is not None:
            x_lbl, x_tf = _axis_info(spec_2d["x"])
            y_lbl, y_tf = _axis_info(spec_2d["y"])
            try:
                plot_parametric_2d(
                    param,
                    x_var=spec_2d["x"], y_var=spec_2d["y"],
                    holds=spec_2d.get("holds") or None,
                    x_label=x_lbl, y_label=y_lbl,
                    x_transform=x_tf, y_transform=y_tf,
                    hold_label_fn=_hold_label,
                )
            except Exception as exc:
                errors.append(f"2D plot: {type(exc).__name__}: {exc}")

        if spec_3d is not None:
            x_lbl, x_tf = _axis_info(spec_3d["x"])
            y_lbl, y_tf = _axis_info(spec_3d["y"])
            z_lbl, z_tf = _axis_info(spec_3d["z"])
            try:
                plot_parametric_3d(
                    param,
                    x_var=spec_3d["x"], y_var=spec_3d["y"],
                    z_var=spec_3d["z"],
                    holds=spec_3d.get("holds") or None,
                    x_label=x_lbl, y_label=y_lbl, z_label=z_lbl,
                    x_transform=x_tf, y_transform=y_tf, z_transform=z_tf,
                    hold_label_fn=_hold_label,
                )
            except Exception as exc:
                errors.append(f"3D plot: {type(exc).__name__}: {exc}")

        lift_all_figures()

        if errors:
            messagebox.showerror(
                "Couldn't build one or more graphs",
                "\n".join(errors),
            )

    # ===================================================================
    # Utilities
    # ===================================================================

    def _default_export_name(self) -> str:
        if self._result_path is not None:
            return self._result_path.stem + ".csv"
        return f"steady_export_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.csv"

    def _set_status(self, text: str) -> None:
        self.status_label.configure(text=text)


# ---------------------------------------------------------------------------

def _format_value(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        if v == int(v):
            return f"{int(v)}"
        return f"{v:.6g}"
    if isinstance(v, dict):
        return f"({len(v)} keys — nested)"
    if isinstance(v, list):
        return f"[{len(v)} items]"
    return str(v)
