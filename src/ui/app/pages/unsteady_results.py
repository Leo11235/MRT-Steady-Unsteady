"""
UnsteadyResultsPage — landed on after an unsteady simulation finishes
(and also when the user opens a saved run from the Browse-saved-results
page).

Five tabs, each a scrollable panel:

  * Rocket inputs      — the flattened CV_inputs block
  * Metadata           — run metadata (simulation_name, timestamp, ...)
  * Overall            — performance.overall (headline numbers)
  * Phase-by-phase     — one row per phase with duration + burn-phase metrics
  * Warnings           — the triggered_warnings block from history.warnings

Sidebar buttons:

  * Copy to clipboard          → performance.overall as TSV row
  * Export to sheets (.csv)    → inputs + metadata + overall + per-phase
  * Show select graphs         → kinematics + thrust vs time
  * Show all graphs            → the full display_unsteady_results dashboard
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.ui.app import theme, results_utils, backend_bridge


# Every plot toggle understood by display_unsteady_results.  Used to
# selectively enable a subset of graphs (for "Show select graphs").
_ALL_PLOT_TOGGLES = (
    "performance_panel",
    "events_warnings_panel",
    "thrust_vs_time",
    "injector_mass_flow_vs_time",
    "rocket_kinematics",
    "of_ratio_vs_time",
    "chamber_temperature_vs_time",
    "tank_pressure_vs_time",
    "tank_temperature_vs_time",
    "chamber_pressure_vs_time",
    "oxidizer_inventory_vs_time",
    "fuel_grain_state_vs_time",
    "injector_pressure_drop_vs_time",
    "nozzle_exit_conditions_vs_time",
    "nozzle_flow_regime_vs_time",
    "combustion_properties_vs_time",
    "ambient_atmosphere_vs_time",
    "isp_vs_time",
    "rocket_total_mass_vs_time",
    "trajectory_map",
    "of_vs_port_radius",
    "thrust_vs_chamber_pressure",
    "solver_step_size",
    "nan_map",
    "mass_conservation_check",
    "thrust_with_event_markers",
    "rocket_cross_section",
    "nozzle_profile",
)


class UnsteadyResultsPage(ctk.CTkFrame):
    TITLE = "Unsteady simulation results"

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate
        self._result_path: Path | None = None
        self._result_dict: dict | None = None
        self._unit_system: str = "SI"
        self._unit_buttons: dict = {}
        self._build()

    # ===================================================================
    # Layout
    # ===================================================================

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=220)
        self.grid_rowconfigure(0, weight=1)

        self.tabs = ctk.CTkTabview(self, anchor="w")
        self.tabs.grid(row=0, column=0, sticky="nsew",
                       padx=(theme.PAD_M, theme.PAD_S), pady=theme.PAD_M)

        self._inputs_tab   = self.tabs.add("Rocket inputs")
        self._meta_tab     = self.tabs.add("Metadata")
        self._overall_tab  = self.tabs.add("Overall")
        self._phases_tab   = self.tabs.add("Phase-by-phase")
        self._warn_tab     = self.tabs.add("Warnings")

        self._inputs_scroll  = ctk.CTkScrollableFrame(self._inputs_tab, label_text="")
        self._inputs_scroll.pack(fill="both", expand=True)
        self._meta_scroll    = ctk.CTkScrollableFrame(self._meta_tab, label_text="")
        self._meta_scroll.pack(fill="both", expand=True)
        self._overall_scroll = ctk.CTkScrollableFrame(self._overall_tab, label_text="")
        self._overall_scroll.pack(fill="both", expand=True)
        self._phases_scroll  = ctk.CTkScrollableFrame(self._phases_tab, label_text="")
        self._phases_scroll.pack(fill="both", expand=True)
        self._warn_scroll    = ctk.CTkScrollableFrame(self._warn_tab, label_text="")
        self._warn_scroll.pack(fill="both", expand=True)

        # sidebar
        sidebar = ctk.CTkFrame(self, fg_color="transparent")
        sidebar.grid(row=0, column=1, sticky="ns",
                     padx=(theme.PAD_S, theme.PAD_M), pady=theme.PAD_M)
        self._build_sidebar(sidebar)

        # status line
        self.status_label = ctk.CTkLabel(
            self, text="", anchor="w",
            text_color=("gray35", "gray65"),
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
        )
        self.status_label.grid(row=1, column=0, columnspan=2, sticky="ew",
                               padx=theme.PAD_M, pady=(0, theme.PAD_S))

    def _build_sidebar(self, parent) -> None:
        ctk.CTkLabel(parent, text="Actions",
                     font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
                     anchor="w").pack(fill="x", pady=(0, theme.PAD_S))

        ctk.CTkButton(parent, text="Copy to clipboard",
                      width=200, height=36,
                      command=self._on_copy).pack(pady=theme.PAD_XS)
        ctk.CTkButton(parent, text="Export to sheets (.csv)",
                      width=200, height=36,
                      command=self._on_export).pack(pady=theme.PAD_XS)

        ctk.CTkLabel(parent, text="Graphs",
                     font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold"),
                     anchor="w").pack(fill="x", pady=(theme.PAD_L, theme.PAD_XS))

        ctk.CTkButton(parent, text="Show select graphs",
                      width=200, height=36,
                      command=self._on_select_graphs).pack(pady=theme.PAD_XS)
        ctk.CTkButton(parent, text="Show all graphs",
                      width=200, height=36,
                      command=self._on_all_graphs).pack(pady=theme.PAD_XS)

        ctk.CTkLabel(parent, text="Units",
                     font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold"),
                     anchor="w").pack(fill="x", pady=(theme.PAD_L, theme.PAD_XS))
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
        if self._result_dict is None:
            self._set_status("No results loaded yet.")

    def reset_to_defaults(self) -> None:
        self._result_path = None
        self._result_dict = None
        for f in (self._inputs_scroll, self._meta_scroll,
                  self._overall_scroll, self._phases_scroll,
                  self._warn_scroll):
            self._clear_scroll(f)
        self._unit_system = "SI"
        if self._unit_buttons:
            results_utils.refresh_unit_buttons(self._unit_buttons, self._unit_system)
        self._set_status("")

    # ===================================================================
    # Panel population
    # ===================================================================

    def _clear_scroll(self, frame) -> None:
        for w in frame.winfo_children():
            w.destroy()

    def _refresh_panels(self) -> None:
        for f in (self._inputs_scroll, self._meta_scroll,
                  self._overall_scroll, self._phases_scroll,
                  self._warn_scroll):
            self._clear_scroll(f)
        if self._result_dict is None:
            return

        # ------- Inputs tab -----------------------------------------
        ri = ((self._result_dict.get("static") or {}).get("rocket_inputs")
              or self._result_dict.get("rocket_inputs")
              or {})
        # rocket_inputs is nested: initial_conditions + CV_inputs.CV*_*
        ic = ri.get("initial_conditions") or {}
        if isinstance(ic, dict) and ic:
            self._render_dict_section(self._inputs_scroll,
                                      "Initial conditions", ic)
        cv_inputs = ri.get("CV_inputs") or {}
        if isinstance(cv_inputs, dict):
            for cv_name in _CV_ORDER:
                block = cv_inputs.get(cv_name)
                if isinstance(block, dict) and block:
                    self._render_dict_section(
                        self._inputs_scroll,
                        _CV_PRETTY.get(cv_name, cv_name),
                        block,
                    )
        # Anything at the top level of rocket_inputs that isn't nested —
        # render the rows without a section header (per user request).
        top_level = {k: v for k, v in ri.items()
                     if k not in ("initial_conditions", "CV_inputs", "metadata")
                     and not isinstance(v, dict)}
        if top_level:
            for key, value in top_level.items():
                self._render_kv_row(self._inputs_scroll, key, value)

        # ------- Metadata tab ---------------------------------------
        meta = self._result_dict.get("metadata") or {}
        if isinstance(meta, dict) and meta:
            self._render_dict_section(self._meta_scroll, "Run metadata", meta)
        rocket_meta = ri.get("metadata") or {}
        if isinstance(rocket_meta, dict) and rocket_meta:
            self._render_dict_section(self._meta_scroll,
                                      "Rocket-inputs metadata", rocket_meta)
        if self._result_path is not None:
            self._render_dict_section(
                self._meta_scroll, "File",
                {"path": str(self._result_path),
                 "size (KiB)": f"{self._result_path.stat().st_size / 1024:.1f}"
                 if self._result_path.exists() else "?"},
            )

        # ------- Overall tab ----------------------------------------
        perf = self._result_dict.get("performance") or {}
        overall = perf.get("overall") or {}
        if overall:
            self._render_dict_section(self._overall_scroll,
                                      "Overall performance", overall)
        else:
            self._empty_message(self._overall_scroll,
                                "No overall-performance block in this file.")

        # ------- Phase-by-phase tab ---------------------------------
        by_phase = perf.get("by_phase") or {}
        if by_phase:
            self._render_phase_table(self._phases_scroll, by_phase)
        else:
            self._empty_message(self._phases_scroll,
                                "No per-phase metrics in this file.")

        # ------- Warnings tab ---------------------------------------
        warnings = self._result_dict.get("warnings")
        self._render_warnings(self._warn_scroll, warnings)

    def _render_dict_section(self, parent, title: str, d: dict) -> None:
        ctk.CTkLabel(parent, text=title,
                     font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
                     anchor="w").pack(fill="x", pady=(theme.PAD_S, theme.PAD_XS))
        for key, value in d.items():
            self._render_kv_row(parent, key, value)

    def _render_kv_row(self, parent, key: str, value) -> None:
        """3-column row (name | value | unit) via shared helper — keeps
        the two results pages visually in sync and unit-aware."""
        results_utils.render_kv_row(parent, key, value, self._unit_system)

    def _set_unit_system(self, system: str) -> None:
        if system == self._unit_system:
            return
        self._unit_system = system
        results_utils.refresh_unit_buttons(self._unit_buttons, system)
        self._refresh_panels()

    def _render_phase_table(self, parent, by_phase: dict) -> None:
        # One CTk-drawn "table": one bordered row per phase, with the
        # metrics listed vertically inside.
        ctk.CTkLabel(
            parent, text="Per-phase metrics",
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(theme.PAD_S, theme.PAD_XS))
        for phase_name, entry in by_phase.items():
            if not isinstance(entry, dict):
                continue
            group = ctk.CTkFrame(parent,
                                 fg_color=("gray90", "gray18"),
                                 corner_radius=6)
            group.pack(fill="x", pady=theme.PAD_XS)
            ctk.CTkLabel(
                group, text=_prettify_phase(phase_name),
                font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold"),
                anchor="w",
            ).pack(fill="x", padx=theme.PAD_S, pady=(theme.PAD_S, 2))
            inner = ctk.CTkFrame(group, fg_color="transparent")
            inner.pack(fill="x", padx=theme.PAD_S)
            for k, v in entry.items():
                results_utils.render_kv_row(inner, k, v, self._unit_system)
            ctk.CTkFrame(group, height=6, fg_color="transparent") \
                .pack()   # bottom pad

    def _render_warnings(self, parent, warnings) -> None:
        if warnings == "disabled" or warnings is None:
            self._empty_message(parent, "Warnings system was disabled for this run.")
            return
        if isinstance(warnings, dict):
            level = warnings.get("overall_warning_level", "—")
            triggered = warnings.get("triggered_warnings") or {}
        else:
            self._empty_message(parent, f"Unrecognized warnings format: {warnings!r}")
            return

        # header
        _level_color = {
            "none":     ("#2a9d8f", "#5eead4"),
            "advisory": ("#f4a261", "#f4a261"),
            "regular":  ("#e76f51", "#ff9e7a"),
            "critical": ("#b00020", "#ff6b6b"),
        }.get(str(level).lower(), ("gray35", "gray65"))
        ctk.CTkLabel(
            parent, text=f"Overall level:  {level}",
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            text_color=_level_color, anchor="w",
        ).pack(fill="x", pady=(theme.PAD_S, theme.PAD_M))

        if not triggered:
            self._empty_message(parent, "No warnings triggered.")
            return

        for name, w in triggered.items():
            if not isinstance(w, dict):
                continue
            severity = w.get("severity", "—")
            count    = w.get("num_occurences", w.get("num_occurrences", "—"))
            message  = w.get("message", "")
            _sev_col = {
                "debug":    ("gray45", "gray65"),
                "advisory": ("#f4a261", "#f4a261"),
                "regular":  ("#e76f51", "#ff9e7a"),
                "critical": ("#b00020", "#ff6b6b"),
            }.get(str(severity).lower(), ("gray35", "gray65"))

            box = ctk.CTkFrame(parent, fg_color=("gray90", "gray18"),
                               corner_radius=6)
            box.pack(fill="x", pady=theme.PAD_XS)

            top = ctk.CTkFrame(box, fg_color="transparent")
            top.pack(fill="x", padx=theme.PAD_S, pady=(theme.PAD_S, 2))
            ctk.CTkLabel(
                top, text=str(name),
                font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold"),
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(top, text=f"[{severity}]", text_color=_sev_col,
                        font=ctk.CTkFont(size=theme.SIZE_SMALL, weight="bold"),
                        ).pack(side="left", padx=(theme.PAD_S, 0))
            ctk.CTkLabel(top, text=f"× {count}", text_color=("gray45", "gray65"),
                        ).pack(side="right")
            ctk.CTkLabel(
                box, text=str(message)[:400],
                anchor="w", justify="left",
                wraplength=800,
                text_color=("gray20", "gray80"),
                font=ctk.CTkFont(size=theme.SIZE_SMALL),
            ).pack(fill="x", padx=theme.PAD_S, pady=(0, theme.PAD_S))

    def _empty_message(self, parent, text: str) -> None:
        ctk.CTkLabel(parent, text=text,
                     text_color=("gray45", "gray60"),
                     font=ctk.CTkFont(size=theme.SIZE_BODY, slant="italic")
                    ).pack(padx=theme.PAD_L, pady=theme.PAD_L)

    # ===================================================================
    # Actions
    # ===================================================================

    def _on_copy(self) -> None:
        if self._result_dict is None:
            messagebox.showinfo("Nothing to copy", "No results loaded.")
            return
        overall = ((self._result_dict.get("performance") or {}).get("overall")
                   or {})
        flat = results_utils.flatten_dict(overall)
        if not flat:
            messagebox.showinfo("Nothing to copy",
                                "This run has no overall-performance block.")
            return
        pairs = results_utils.flat_to_display_pairs(flat, self._unit_system)
        results_utils.copy_pairs_to_clipboard(self, pairs)
        self._set_status(
            f"Copied {len(pairs)} overall-performance values "
            f"(in {self._unit_system})."
        )

    def _on_export(self) -> None:
        if self._result_dict is None:
            messagebox.showinfo("Nothing to export", "No results loaded.")
            return
        # Everything critical — inputs + metadata + performance.  Skip
        # `data` (time series, thousands of numbers) and `event_log`.
        ri = ((self._result_dict.get("static") or {}).get("rocket_inputs")
              or self._result_dict.get("rocket_inputs") or {})
        payload = {
            "metadata":       self._result_dict.get("metadata") or {},
            "rocket_inputs":  ri,
            "performance":    self._result_dict.get("performance") or {},
        }
        flat = results_utils.flatten_dict(payload, skip_keys=("data",))
        if not flat:
            messagebox.showinfo("Nothing to export",
                                "No exportable data in this result file.")
            return
        pairs = results_utils.flat_to_display_pairs(flat, self._unit_system)

        default_name = self._default_export_name()
        path = filedialog.asksaveasfilename(
            title="Export unsteady results (one-row CSV)",
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

    def _on_select_graphs(self) -> None:
        if not self._require_result_file():
            return
        # Only the kinematics + thrust plots.
        kwargs = {name: False for name in _ALL_PLOT_TOGGLES}
        kwargs["rocket_kinematics"] = True
        kwargs["thrust_vs_time"]    = True
        self._invoke_display(**kwargs)

    def _on_all_graphs(self) -> None:
        if not self._require_result_file():
            return
        # Defaults = all plots on.
        self._invoke_display()

    def _require_result_file(self) -> bool:
        if self._result_path is None or not self._result_path.exists():
            messagebox.showinfo("No results file",
                                "Can't find the results JSON on disk. "
                                "Try running the simulation again.")
            return False
        return True

    def _invoke_display(self, **kwargs) -> None:
        """Call display_unsteady_results on the current result file.
        Runs synchronously on the main thread; matplotlib windows block
        until closed (which is expected UX for this button)."""
        try:
            from src.backend.unsteady.analysis.unsteady_results import (
                display_unsteady_results,
            )
            display_unsteady_results(
                json_filename=self._result_path.name,
                json_filepath=self._result_path.parent,
                display_graphs=True,
                **kwargs,
            )
        except Exception as exc:
            messagebox.showerror("Could not display graphs",
                                 f"{type(exc).__name__}: {exc}")

    # ===================================================================
    # Utilities
    # ===================================================================

    def _default_export_name(self) -> str:
        if self._result_path is not None:
            return self._result_path.stem + ".csv"
        return f"unsteady_export_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.csv"

    def _set_status(self, text: str) -> None:
        self.status_label.configure(text=text)


# ---------------------------------------------------------------------------
# Static helpers
# ---------------------------------------------------------------------------

_CV_ORDER = (
    "CV1_tank", "CV2_valve", "CV3_injector",
    "CV4_chamber", "CV5_nozzle", "CV6_trajectory",
)
_CV_PRETTY = {
    "CV1_tank":       "Tank (CV1)",
    "CV2_valve":      "Valve (CV2)",
    "CV3_injector":   "Injector (CV3)",
    "CV4_chamber":    "Chamber (CV4)",
    "CV5_nozzle":     "Nozzle (CV5)",
    "CV6_trajectory": "Trajectory (CV6)",
}


def _prettify_phase(name: str) -> str:
    """phase_1 → 'Phase 1', phase_4a → 'Phase 4a', phase_4c → 'Phase 4c'.
    Leaves anything not matching that shape alone."""
    if not isinstance(name, str):
        return str(name)
    if name.startswith("phase_"):
        return "Phase " + name[len("phase_"):]
    return name


def _format_value(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if v == int(v):
            return f"{int(v)}"
        return f"{v:.6g}"
    if isinstance(v, dict):
        return f"({len(v)} keys — nested)"
    if isinstance(v, list):
        return f"[{len(v)} items]"
    return str(v)
