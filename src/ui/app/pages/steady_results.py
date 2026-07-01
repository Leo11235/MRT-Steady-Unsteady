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


class SteadyResultsPage(ctk.CTkFrame):
    TITLE = "Steady simulation results"

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate
        self._result_path: Path | None = None
        self._result_dict: dict | None = None
        self._unit_system: str = "SI"     # SI / IMP / MRT
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

        self._inputs_tab  = self.tabs.add("Rocket inputs")
        self._outputs_tab = self.tabs.add("Sim outputs")

        # scrollable frames inside each tab, refilled by _refresh_panels
        self._inputs_scroll  = ctk.CTkScrollableFrame(self._inputs_tab, label_text="")
        self._inputs_scroll.pack(fill="both", expand=True)
        self._outputs_scroll = ctk.CTkScrollableFrame(self._outputs_tab, label_text="")
        self._outputs_scroll.pack(fill="both", expand=True)

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
        # If we've been navigated to without load_results having been
        # called, keep whatever was previously shown.
        if self._result_dict is None:
            self._set_status("No results loaded yet.")

    def reset_to_defaults(self) -> None:
        self._result_path = None
        self._result_dict = None
        self._clear_scroll(self._inputs_scroll)
        self._clear_scroll(self._outputs_scroll)
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
        self._clear_scroll(self._inputs_scroll)
        self._clear_scroll(self._outputs_scroll)
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
        if isinstance(param, dict):
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
        system) | unit label.  Delegates to the shared helper so the two
        results pages stay in sync."""
        results_utils.render_kv_row(parent, key, value, self._unit_system)

    def _set_unit_system(self, system: str) -> None:
        if system == self._unit_system:
            return
        self._unit_system = system
        results_utils.refresh_unit_buttons(self._unit_buttons, system)
        self._refresh_panels()

    # ===================================================================
    # Actions
    # ===================================================================

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

    def _on_select_graphs(self) -> None:
        self._show_flight_plots(only_selected=True)

    def _on_all_graphs(self) -> None:
        self._show_flight_plots(only_selected=False)

    def _show_flight_plots(self, *, only_selected: bool) -> None:
        if self._result_dict is None:
            messagebox.showinfo("No results", "No results loaded.")
            return
        fd = self._result_dict.get("flight_dict")
        if not isinstance(fd, dict) or not fd.get("time"):
            messagebox.showinfo(
                "No time-series available",
                "This simulation type (probably hotfire) doesn't produce a "
                "trajectory time series — nothing to plot.",
            )
            return
        # Lazy-import matplotlib so app startup isn't slower for users who
        # never open the results page.
        import matplotlib.pyplot as plt

        t   = fd.get("time", [])
        alt = fd.get("altitude", [])
        vel = fd.get("velocity", [])
        acc = fd.get("acceleration", [])
        thr = fd.get("thrust", [])
        drag= fd.get("drag_force", [])
        grv = fd.get("grav_force", [])

        if only_selected:
            # Kinematics (three subplots) + thrust curve
            fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True,
                                     num="Kinematics")
            axes[0].plot(t, alt); axes[0].set_ylabel("Altitude [m]")
            axes[1].plot(t, vel); axes[1].set_ylabel("Velocity [m/s]")
            axes[2].plot(t, acc); axes[2].set_ylabel("Accel [m/s²]"); axes[2].set_xlabel("Time [s]")
            for a in axes:
                a.grid(True, linestyle="--", alpha=0.5)
            fig.suptitle("Rocket kinematics", fontweight="bold")
            fig.tight_layout(rect=[0, 0, 1, 0.96])

            fig2, ax2 = plt.subplots(figsize=(10, 5), num="Thrust curve")
            ax2.plot(t, thr, color="#e63946")
            ax2.set_xlabel("Time [s]"); ax2.set_ylabel("Thrust [N]")
            ax2.grid(True, linestyle="--", alpha=0.5)
            fig2.suptitle("Thrust curve", fontweight="bold")
            fig2.tight_layout(rect=[0, 0, 1, 0.96])
        else:
            # All available graphs: kinematics + thrust + forces breakdown
            fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True,
                                     num="Kinematics")
            axes[0].plot(t, alt); axes[0].set_ylabel("Altitude [m]")
            axes[1].plot(t, vel); axes[1].set_ylabel("Velocity [m/s]")
            axes[2].plot(t, acc); axes[2].set_ylabel("Accel [m/s²]"); axes[2].set_xlabel("Time [s]")
            for a in axes: a.grid(True, linestyle="--", alpha=0.5)
            fig.suptitle("Rocket kinematics", fontweight="bold")
            fig.tight_layout(rect=[0, 0, 1, 0.96])

            fig2, ax2 = plt.subplots(figsize=(10, 5), num="Thrust curve")
            ax2.plot(t, thr, color="#e63946")
            ax2.set_xlabel("Time [s]"); ax2.set_ylabel("Thrust [N]")
            ax2.grid(True, linestyle="--", alpha=0.5)
            fig2.suptitle("Thrust curve", fontweight="bold")
            fig2.tight_layout(rect=[0, 0, 1, 0.96])

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

        plt.show()

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
