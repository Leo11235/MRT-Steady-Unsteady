"""
unsteady_results_2.py
=====================
Second-iteration post-run visualization for unsteady simulation outputs.

Differences vs. unsteady_results.py:
  - Thrust, OF, chamber temperature plots are trimmed to burn phases.
  - 22 new plots added (tank, chamber, nozzle, combustion, atmosphere,
    trajectory map, OF vs r_f, Isp, diagnostics, geometry sketches).
  - Per-phase performance table tightened.
  - Per-plot toggles via kwargs (each defaults to True).
  - Optional save_to_pdf / save_to_png modes that write into
    `simulation_results/unsteady/<json_basename>/`.
  - At most `max_concurrent_figures` (default 10) windows pop up at a
    time; the next batch shows when the user closes the previous one.
  - Performance + inputs and event/warnings panels show first.
  - `analyze_most_recent(n=...)` picks the latest (or n-th most recent) run.

Use the demo call at the bottom of this file as a template.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.patches import Patch, Rectangle, FancyBboxPatch, Polygon
from matplotlib.backends.backend_pdf import PdfPages


# =============================================================================
# Phase metadata
# =============================================================================

PHASE_ORDER = [
    "phase_1", "phase_2", "phase_3", "phase_4a", "phase_4c",
    "phase_5", "phase_6", "phase_7",
]

PHASE_COLORS = {
    "phase_1":  "#e63946",
    "phase_2":  "#f4a261",
    "phase_3":  "#f3c623",
    "phase_4a": "#9d4edd",
    "phase_4c": "#5a189a",
    "phase_5":  "#2a9d8f",
    "phase_6":  "#118ab2",
    "phase_7":  "#073b4c",
}

# colon-separated (saves space in the per-phase table)
PHASE_LABELS = {
    "phase_1":  "1: Ignition",
    "phase_2":  "2: Liquid blowdown",
    "phase_3":  "3: Gaseous blowdown",
    "phase_4a": "4a: Vapor purge",
    "phase_4c": "4c: Dry blowdown",
    "phase_5":  "5: Coast",
    "phase_6":  "6: Drogue descent",
    "phase_7":  "7: Main descent",
}

BURN_PHASES    = {"phase_1", "phase_2", "phase_3", "phase_4a", "phase_4c"}
DESCENT_PHASES = {"phase_5", "phase_6", "phase_7"}


# =============================================================================
# Public entry points
# =============================================================================

def unsteady_results(
    json_filename: str | None = None,
    json_filepath: str | Path | None = None,
    *,
    # ------------------------------------------------------------------
    # Output behaviour
    # ------------------------------------------------------------------
    display_graphs: bool = True,
    save_to_pdf: bool = False,
    save_to_png: bool = False,
    max_concurrent_figures: int = 10,
    # ------------------------------------------------------------------
    # Textual panels (always shown first when enabled)
    # ------------------------------------------------------------------
    performance_panel: bool = True,
    events_warnings_panel: bool = True,
    # ------------------------------------------------------------------
    # Original time-series plots
    # ------------------------------------------------------------------
    thrust_vs_time: bool = True,
    injector_mass_flow_vs_time: bool = True,
    rocket_kinematics: bool = True,
    of_ratio_vs_time: bool = True,
    chamber_temperature_vs_time: bool = True,
    # ------------------------------------------------------------------
    # Burn-only time-series plots
    # ------------------------------------------------------------------
    tank_pressure_vs_time: bool = True,
    tank_temperature_vs_time: bool = True,
    chamber_pressure_vs_time: bool = True,
    oxidizer_inventory_vs_time: bool = True,
    fuel_grain_state_vs_time: bool = True,
    injector_pressure_drop_vs_time: bool = True,
    nozzle_exit_conditions_vs_time: bool = True,
    nozzle_flow_regime_vs_time: bool = True,
    combustion_properties_vs_time: bool = True,
    ambient_atmosphere_vs_time: bool = True,
    isp_vs_time: bool = True,
    rocket_total_mass_vs_time: bool = True,
    # ------------------------------------------------------------------
    # Non-time-axis plots
    # ------------------------------------------------------------------
    trajectory_map: bool = True,
    of_vs_port_radius: bool = True,
    thrust_vs_chamber_pressure: bool = True,
    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    solver_step_size: bool = True,
    nan_map: bool = True,
    mass_conservation_check: bool = True,
    thrust_with_event_markers: bool = True,
    # ------------------------------------------------------------------
    # Geometry sketches
    # ------------------------------------------------------------------
    rocket_cross_section: bool = True,
    nozzle_profile: bool = True,
) -> Optional[Path]:
    """
    Master entry point. See the demo call at the bottom of this file for
    every supported argument.

    Returns
    -------
    The output directory (a Path) when `save_to_pdf` or `save_to_png` were
    enabled; otherwise None.

    Notes
    -----
    `display_graphs=False` short-circuits all matplotlib display logic — useful
    in combination with `save_to_pdf=True` or `save_to_png=True` for headless
    batch processing.

    PDF / PNG output goes into
        <project_root>/user_data/simulation_results/unsteady/<json_basename>/
    Any plot whose toggle is False is excluded from both the on-screen pop-ups
    AND the PDF / PNG outputs.
    """

    # 1. resolve and load file
    if json_filename is None:
        json_filename, json_filepath = _nth_recent_results_file(0)
    sim_results = _load_results(json_filename, json_filepath)

    # 2. build the (name, flag, builder) plan in display order
    plan: list[tuple[str, bool, Callable[[dict], Optional[Figure]]]] = [
        # textual panels first
        ("performance_panel",               performance_panel,                make_performance_panel),
        ("events_warnings_panel",           events_warnings_panel,            make_events_warnings_panel),
        # original plots
        ("thrust_vs_time",                  thrust_vs_time,                   make_thrust_plot),
        ("injector_mass_flow_vs_time",      injector_mass_flow_vs_time,       make_injector_mass_flow_plot),
        ("rocket_kinematics",               rocket_kinematics,                make_kinematics_plot),
        ("of_ratio_vs_time",                of_ratio_vs_time,                 make_of_ratio_plot),
        ("chamber_temperature_vs_time",     chamber_temperature_vs_time,      make_chamber_temperature_plot),
        # burn-only time series
        ("tank_pressure_vs_time",           tank_pressure_vs_time,            make_tank_pressure_plot),
        ("tank_temperature_vs_time",        tank_temperature_vs_time,         make_tank_temperature_plot),
        ("chamber_pressure_vs_time",        chamber_pressure_vs_time,         make_chamber_pressure_plot),
        ("oxidizer_inventory_vs_time",      oxidizer_inventory_vs_time,       make_oxidizer_inventory_plot),
        ("fuel_grain_state_vs_time",        fuel_grain_state_vs_time,         make_fuel_grain_state_plot),
        ("injector_pressure_drop_vs_time",  injector_pressure_drop_vs_time,   make_injector_dp_plot),
        ("nozzle_exit_conditions_vs_time",  nozzle_exit_conditions_vs_time,   make_nozzle_exit_plot),
        ("nozzle_flow_regime_vs_time",      nozzle_flow_regime_vs_time,       make_flow_regime_plot),
        ("combustion_properties_vs_time",   combustion_properties_vs_time,    make_combustion_properties_plot),
        ("ambient_atmosphere_vs_time",      ambient_atmosphere_vs_time,       make_ambient_atmosphere_plot),
        ("isp_vs_time",                     isp_vs_time,                      make_isp_plot),
        ("rocket_total_mass_vs_time",       rocket_total_mass_vs_time,        make_rocket_total_mass_plot),
        # non-time-axis
        ("trajectory_map",                  trajectory_map,                   make_trajectory_map),
        ("of_vs_port_radius",               of_vs_port_radius,                make_of_vs_radius_plot),
        ("thrust_vs_chamber_pressure",      thrust_vs_chamber_pressure,       make_thrust_vs_pc_plot),
        # diagnostics
        ("solver_step_size",                solver_step_size,                 make_solver_step_size_plot),
        ("nan_map",                         nan_map,                          make_nan_map_plot),
        ("mass_conservation_check",         mass_conservation_check,          make_mass_conservation_plot),
        ("thrust_with_event_markers",       thrust_with_event_markers,        make_thrust_with_events_plot),
        # geometry
        ("rocket_cross_section",            rocket_cross_section,             make_rocket_cross_section),
        ("nozzle_profile",                  nozzle_profile,                   make_nozzle_profile),
    ]

    # If display_graphs is False, the per-plot toggles still apply for
    # save_to_pdf / save_to_png — but nothing pops up on screen. If neither
    # display nor save are enabled, do nothing.
    if not display_graphs and not (save_to_pdf or save_to_png):
        print("display_unsteady_results: display_graphs=False and no save targets — nothing to do.")
        return None

    # 3. saving (if requested) — needs every figure up front
    output_dir: Optional[Path] = None
    if save_to_pdf or save_to_png:
        output_dir = _per_run_output_dir(json_filename, json_filepath)
        figures: list[Figure] = []
        names: list[str] = []
        for name, flag, builder in plan:
            if not flag:
                continue
            try:
                fig = builder(sim_results)
            except Exception as exc:
                print(f"  ! skipped {name}: {type(exc).__name__}: {exc}")
                continue
            if fig is None:
                continue
            figures.append(fig)
            names.append(name)

        if save_to_pdf:
            _save_figures_to_pdf(figures, names, output_dir)
        if save_to_png:
            _save_figures_to_png(figures, names, output_dir)

        # close the built figures so the display step below starts clean and
        # plt.show() only sees the current batch's figures.
        for fig in figures:
            plt.close(fig)
        plt.close("all")

    # 4. display (if requested) — build batch-by-batch
    if display_graphs:
        _build_and_display_in_batches(plan, sim_results, max_concurrent_figures)

    return output_dir


def analyze_most_recent(n: int = 0, **kwargs) -> Optional[Path]:
    """
    Run `display_unsteady_results` on the n-th most-recent results JSON.

    Parameters
    ----------
    n : int
        0 (default) = latest, 1 = second-latest, 2 = third-latest, etc.
    **kwargs
        Forwarded verbatim to `display_unsteady_results`.
    """
    fname, fdir = _nth_recent_results_file(n)
    print(f"Analyzing run {n} from most recent: {fname}")
    return unsteady_results(fname, fdir, **kwargs)


# =============================================================================
# IO and prep
# =============================================================================

def _load_results(json_filename: str, json_filepath=None) -> dict:
    if json_filepath is None:
        project_root = Path(__file__).resolve().parents[4]
        json_filepath = project_root / "user_data" / "simulation_results" / "unsteady"
    full_path = Path(json_filepath) / json_filename
    if not full_path.exists():
        raise FileNotFoundError(f"Results file not found: {full_path}")
    print(f"Loading: {full_path}")
    with open(full_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _nth_recent_results_file(n: int = 0) -> tuple[str, Path]:
    """Return (filename, directory) of the n-th most recent results JSON."""
    project_root = Path(__file__).resolve().parents[4]
    results_dir = project_root / "user_data" / "simulation_results" / "unsteady"
    if not results_dir.exists():
        raise FileNotFoundError(f"Results directory not found: {results_dir}")
    candidates = sorted(results_dir.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"No JSON results found in {results_dir}")
    if n < 0 or n >= len(candidates):
        raise IndexError(f"Run offset {n} out of range — only {len(candidates)} runs available")
    # newest first -> index 0 is the latest
    picked = candidates[-(n + 1)]
    return picked.name, results_dir


def _per_run_output_dir(json_filename: str, json_filepath=None) -> Path:
    """
    Create and return `<simulation_results>/unsteady/<json_basename>/`,
    where <json_basename> is the filename without the .json extension.
    """
    if json_filepath is None:
        project_root = Path(__file__).resolve().parents[4]
        base_results = project_root / "user_data" / "simulation_results" / "unsteady"
    else:
        base_results = Path(json_filepath)
    basename = Path(json_filename).stem
    out_dir = base_results / basename
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _arr(d: dict, key: str) -> np.ndarray:
    raw = d.get(key, [])
    return np.array([np.nan if v is None else v for v in raw], dtype=float)


def _phase_arr(d: dict) -> np.ndarray:
    return np.array([p if p is not None else "" for p in d.get("phase", [])], dtype=object)


def _align_to_time(values: np.ndarray, time_full: np.ndarray,
                   phases_full: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(values)
    if n == len(time_full):
        return time_full, values, phases_full
    burn_idx = np.array([i for i, p in enumerate(phases_full) if p in BURN_PHASES])
    if n == len(burn_idx):
        return time_full[burn_idx], values, phases_full[burn_idx]
    return time_full[:n], values, phases_full[:n]


def _burn_indices(phases: np.ndarray) -> np.ndarray:
    """Indices in the full time array that lie inside a burn phase."""
    return np.array([i for i, p in enumerate(phases) if p in BURN_PHASES], dtype=int)


def _trim_to_burn(values: np.ndarray, time_full: np.ndarray,
                  phases_full: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Subset (t, y, phases) to the burn-phase entries only.

    Handles two cases: arrays of full length and arrays already at burn length.
    """
    t, y, ph = _align_to_time(values, time_full, phases_full)
    burn_mask = np.array([p in BURN_PHASES for p in ph])
    return t[burn_mask], y[burn_mask], ph[burn_mask]


def _present_phases(phases: np.ndarray) -> set:
    return {p for p in phases if p in PHASE_COLORS}


# =============================================================================
# Plotting primitives
# =============================================================================

def _plot_colored_by_phase(ax, t, y, phases, linewidth=1.8):
    finite = np.isfinite(y)
    if not finite.any():
        return
    pts = np.column_stack([t, y]).reshape(-1, 1, 2)
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
    seg_colors = [PHASE_COLORS.get(p, "#bdbdbd") for p in phases[:-1]]
    valid = finite[:-1] & finite[1:]
    seg_colors = ["none" if not v else c for v, c in zip(valid, seg_colors)]
    lc = LineCollection(segs, colors=seg_colors, linewidths=linewidth)
    ax.add_collection(lc)
    finite_t = t[finite]
    finite_y = y[finite]
    ax.set_xlim(float(np.min(finite_t)), float(np.max(finite_t)))
    pad = 0.05 * (float(np.max(finite_y)) - float(np.min(finite_y)) + 1e-9)
    ax.set_ylim(float(np.min(finite_y)) - pad, float(np.max(finite_y)) + pad)


def _phase_legend_patches(phases_present: set) -> list:
    return [
        Patch(color=PHASE_COLORS[p], label=PHASE_LABELS[p])
        for p in PHASE_ORDER if p in phases_present
    ]


def _shade_phase_bands(ax, t, phases, alpha=0.08):
    if len(phases) == 0:
        return
    starts = [0]
    for i in range(1, len(phases)):
        if phases[i] != phases[i - 1]:
            starts.append(i)
    starts.append(len(phases))
    for k in range(len(starts) - 1):
        i0, i1 = starts[k], starts[k + 1]
        p = phases[i0]
        color = PHASE_COLORS.get(p)
        if color is None:
            continue
        ax.axvspan(t[i0], t[min(i1, len(t) - 1)], color=color, alpha=alpha, lw=0)


def _open_axes(title: str, window_title: str | None = None,
               figsize=(11, 6)) -> tuple[Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=figsize)
    fig.canvas.manager.set_window_title(window_title or title) if fig.canvas.manager else None
    fig.suptitle(title, fontsize=14, fontweight="bold")
    ax.grid(True, which="both", linestyle="--", alpha=0.5)
    ax.set_xlabel("Time [s]")
    return fig, ax


# =============================================================================
# Formatting helpers
# =============================================================================

def _fmt(value, unit="", precision=2):
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "—"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:,.{precision}f}{(' ' + unit) if unit else ''}"
    return str(value)


def _pa_to_bar(p):
    return None if p is None else p / 1e5


def _n_to_kn(f):
    return None if f is None else f / 1e3


def _flatten_inputs(rocket_inputs: dict) -> dict:
    out = {}
    for k, v in rocket_inputs.items():
        if not isinstance(v, dict):
            out[k] = v
    ic = rocket_inputs.get("initial_conditions", {})
    if isinstance(ic, dict):
        out.update(ic)
    cv_inputs = rocket_inputs.get("CV_inputs", {})
    if isinstance(cv_inputs, dict):
        for cv_name, block in cv_inputs.items():
            if isinstance(block, dict):
                for k, v in block.items():
                    if not isinstance(v, dict):
                        out[k] = v
    return out


# =============================================================================
# Panel 1 — performance + inputs
# =============================================================================

def make_performance_panel(sim_results: dict) -> Figure:
    perf     = sim_results.get("performance", {})
    overall  = perf.get("overall", {})
    by_phase = perf.get("by_phase", {})
    rocket_inputs = sim_results.get("static", {}).get("rocket_inputs", {})
    meta = sim_results.get("metadata", {})

    fig = plt.figure(figsize=(15, 10))
    if fig.canvas.manager:
        fig.canvas.manager.set_window_title("Performance + Inputs")
    fig.suptitle("Unsteady Simulation — Performance & Inputs", fontsize=15, fontweight="bold")

    gs = fig.add_gridspec(2, 2, width_ratios=[1.25, 1.0], height_ratios=[1.0, 1.1],
                          left=0.04, right=0.98, top=0.92, bottom=0.04,
                          hspace=0.32, wspace=0.10)
    ax_scorecard = fig.add_subplot(gs[0, 0])
    ax_inputs    = fig.add_subplot(gs[:, 1])
    ax_byphase   = fig.add_subplot(gs[1, 0])
    for ax in (ax_scorecard, ax_inputs, ax_byphase):
        ax.set_axis_off()

    _draw_scorecard(ax_scorecard, overall, meta)
    _draw_inputs_table(ax_inputs, rocket_inputs)
    _draw_by_phase_table(ax_byphase, by_phase)
    return fig


def _draw_scorecard(ax, overall: dict, meta: dict):
    ax.set_title("Overall performance", fontsize=13, fontweight="bold", loc="left")
    cells = [
        ("Apogee (AGL)",    overall.get("apogee_m_agl"),                       "m",   1),
        ("Apogee (ASL)",    overall.get("apogee_m_asl"),                       "m",   1),
        ("Burn time",       overall.get("burntime_s"),                         "s",   2),
        ("Total impulse",   overall.get("total_impulse_Ns"),                   "N·s", 0),
        ("Peak thrust",     _n_to_kn(overall.get("peak_thrust_N")),            "kN",  2),
        ("Average thrust",  _n_to_kn(overall.get("average_thrust_N")),         "kN",  2),
        ("Pad T/W",         overall.get("pad_thrust_to_weight"),               "",    2),
        ("Peak chamber p",  _pa_to_bar(overall.get("peak_chamber_pressure_Pa")),"bar",1),
        ("Peak chamber T",  overall.get("peak_chamber_temperature_K"),         "K",   0),
        ("Average O/F",     overall.get("average_OF_ratio"),                   "",    2),
        ("Oxidizer used",   overall.get("ox_mass_consumed_kg"),                "kg",  2),
        ("Fuel used",       overall.get("fuel_mass_consumed_kg"),              "kg",  2),
        ("Oxidizer left",   overall.get("ox_mass_remaining_kg"),               "kg",  2),
        ("Fuel left",       overall.get("fuel_mass_remaining_kg"),             "kg",  2),
        ("Sim wall clock",  meta.get("total_simulation_time"),                 "s",   2),
        ("Total timesteps", meta.get("total_timesteps"),                       "",    0),
    ]
    n_cols = 4
    n_rows = math.ceil(len(cells) / n_cols)
    for i, (label, value, unit, prec) in enumerate(cells):
        col = i % n_cols
        row = i // n_cols
        x = (col + 0.5) / n_cols
        y_top, y_bottom = 0.88, 0.05
        y = (y_top + y_bottom) / 2 if n_rows == 1 else y_top - row * (y_top - y_bottom) / (n_rows - 1)
        ax.text(x, y + 0.05, label, ha="center", va="bottom",
                fontsize=9.5, color="#555555", transform=ax.transAxes)
        ax.text(x, y - 0.01, _fmt(value, unit, prec), ha="center", va="top",
                fontsize=12.5, fontweight="bold", color="#1d3557", transform=ax.transAxes)


_INPUT_GROUPS = [
    ("Launch site", [
        ("launch_site_altitude_asl_m", "Altitude ASL", "m", 1),
    ]),
    ("Tank (CV1)", [
        ("tank_internal_radius_m",          "Internal radius",   "m",     4),
        ("tank_internal_shell_length_m",    "Shell length",      "m",     3),
        ("tank_internal_volume_m3",         "Volume",            "m³",    5),
        ("tank_temperature_K",              "Initial temp",      "K",     2),
        ("tank_oxidizer_mass_kg",           "Ox mass loaded",    "kg",    3),
        ("tank_ullage_fraction",            "Ullage fraction",   "",      3),
        ("dip_tube_external_radius_m",      "Dip tube OD/2",     "m",     5),
        ("dip_tube_internal_radius_m",      "Dip tube ID/2",     "m",     5),
        ("dip_tube_length_m",               "Dip tube length",   "m",     3),
    ]),
    ("Valve (CV2)", [
        ("valve_time_constant_s",   "Time constant",  "s",   3),
        ("sigmoid_half_time_s",     "Sigmoid t½",     "s",   3),
        ("sigmoid_steepness",       "Sigmoid k",      "",    2),
    ]),
    ("Injector (CV3)", [
        ("injector_discharge_coefficient", "Cd",            "",   3),
        ("injector_number_of_holes",       "Number holes",  "",   0),
        ("injector_hole_area_m2",          "Hole area",     "m²", 8),
        ("feed_pressure_loss_Pa",          "Feed Δp",       "Pa", 0),
    ]),
    ("Chamber (CV4)", [
        ("chamber_fuel_length_m",                    "Fuel length",        "m",      3),
        ("chamber_fuel_density_kgm3",                "Fuel density",       "kg/m³",  1),
        ("chamber_fuel_external_radius_m",           "Fuel OR",            "m",      4),
        ("chamber_fuel_mass_kg",                     "Fuel mass loaded",   "kg",     3),
        ("chamber_regression_rate_scaling_constant", "Regression a",       "",       7),
        ("chamber_regression_rate_exponent",         "Regression n",       "",       3),
        ("pre_chamber_volume_m3",                    "Pre-chamber V",      "m³",     6),
        ("post_chamber_volume_m3",                   "Post-chamber V",     "m³",     6),
    ]),
    ("Nozzle (CV5)", [
        ("nozzle_throat_radius_m", "Throat radius", "m", 4),
        ("nozzle_exit_radius_m",   "Exit radius",   "m", 4),
    ]),
    ("Trajectory (CV6)", [
        ("rocket_dry_mass_kg",                       "Dry mass",         "kg", 2),
        ("rocket_drag_coefficient",                  "Cd",               "",   3),
        ("rocket_frontal_area_m2",                   "Frontal area",     "m²", 5),
        ("rocket_launch_angle_deg",                  "Launch angle",     "°",  1),
        ("drogue_parachute_drag_coefficient",        "Drogue Cd",        "",   2),
        ("drogue_parachute_frontal_area_m2",         "Drogue area",      "m²", 2),
        ("main_parachute_deployment_altitude_agl_m", "Main deploy AGL",  "m",  1),
        ("main_parachute_drag_coefficient",          "Main Cd",          "",   2),
        ("main_parachute_frontal_area_m2",           "Main area",        "m²", 2),
    ]),
]


def _draw_inputs_table(ax, rocket_inputs: dict):
    # nudged the title slightly lower (y=0.96) so it sits cleanly under the
    # figure suptitle without pushing the table down.
    ax.set_title("Rocket inputs", fontsize=13, fontweight="bold", loc="left", y=0.96)
    flat = _flatten_inputs(rocket_inputs)

    rows, row_colors = [], []
    for group_title, fields in _INPUT_GROUPS:
        rows.append([group_title, ""])
        row_colors.append(("#eef2f7", "bold"))
        for key, label, unit, prec in fields:
            if key in flat:
                rows.append([f"  {label}", _fmt(flat[key], unit, prec)])
                row_colors.append(("white", "normal"))

    if not rows:
        ax.text(0.5, 0.5, "No rocket inputs in results file.",
                ha="center", va="center", transform=ax.transAxes, color="#888888")
        return

    table = ax.table(cellText=rows, colWidths=[0.6, 0.4], cellLoc="left",
                     loc="upper left", bbox=[0.0, 0.0, 1.0, 0.92])
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    for (r, c), cell in table.get_celld().items():
        bg, weight = row_colors[r]
        cell.set_facecolor(bg)
        cell.set_edgecolor("#e6e6e6")
        cell.PAD = 0.04
        if weight == "bold":
            cell.set_text_props(fontweight="bold", color="#1d3557")


def _draw_by_phase_table(ax, by_phase: dict):
    ax.set_title("Per-phase performance", fontsize=13, fontweight="bold", loc="left")
    if not by_phase:
        ax.text(0.5, 0.5, "No per-phase data available.",
                ha="center", va="center", transform=ax.transAxes, color="#888888")
        return

    # tightened: dropped Start, End, Ox used, Fuel used columns
    headers = ["Phase", "Dur [s]", "Impulse [Ns]", "Peak F [kN]", "Avg O/F", "Peak Pc [bar]"]

    rows, cell_colors = [], []
    for phase_name in PHASE_ORDER:
        entry = by_phase.get(phase_name)
        if entry is None:
            continue
        is_burn = phase_name in BURN_PHASES
        row = [PHASE_LABELS[phase_name], _fmt(entry.get("duration_s"), "", 2)]
        if is_burn:
            row += [
                _fmt(entry.get("total_impulse_Ns"), "", 0),
                _fmt(_n_to_kn(entry.get("peak_thrust_N")), "", 2),
                _fmt(entry.get("average_OF_ratio"), "", 2),
                _fmt(_pa_to_bar(entry.get("peak_chamber_pressure_Pa")), "", 1),
            ]
        else:
            peak_v = entry.get("peak_velocity_ms")
            term_v = entry.get("terminal_velocity_ms")
            descent = f"peak {_fmt(peak_v, 'm/s', 1)}, term {_fmt(term_v, 'm/s', 1)}"
            row += [descent, "", "", ""]
        rows.append(row)
        cell_colors.append([PHASE_COLORS.get(phase_name, "#cccccc")] + ["#ffffff"] * (len(headers) - 1))

    table = ax.table(cellText=rows, colLabels=headers, cellColours=cell_colors,
                     cellLoc="center", loc="upper left", bbox=[0.0, 0.0, 1.0, 0.94])
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#e6e6e6")
        if r == 0:
            cell.set_facecolor("#1d3557")
            cell.set_text_props(color="white", fontweight="bold")
        else:
            if c == 0:
                cell.set_text_props(color="white", fontweight="bold")
            else:
                cell.set_facecolor("white")


# =============================================================================
# Panel 2 — events + warnings
# =============================================================================

def make_events_warnings_panel(sim_results: dict) -> Figure:
    event_log = sim_results.get("event_log", [])
    warnings  = sim_results.get("warnings", {})

    fig = plt.figure(figsize=(14, 9))
    if fig.canvas.manager:
        fig.canvas.manager.set_window_title("Events + Warnings")
    fig.suptitle("Event Log & Warnings", fontsize=15, fontweight="bold")

    gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.2],
                          left=0.04, right=0.98, top=0.92, bottom=0.04, hspace=0.20)
    ax_events = fig.add_subplot(gs[0, 0]); ax_events.set_axis_off()
    ax_warns  = fig.add_subplot(gs[1, 0]); ax_warns.set_axis_off()
    _draw_events_table(ax_events, event_log)
    _draw_warnings_table(ax_warns, warnings)
    return fig


def _draw_events_table(ax, event_log):
    ax.set_title(f"Event log ({len(event_log)} events)",
                 fontsize=13, fontweight="bold", loc="left")
    if not event_log:
        ax.text(0.5, 0.5, "No events recorded.", ha="center", va="center",
                transform=ax.transAxes, color="#888888")
        return
    headers = ["t [s]", "Type", "Message"]
    rows = [
        [_fmt(ev.get("t_s"), "", 3), ev.get("event_type", ""), ev.get("message", "")]
        for ev in event_log
    ]
    table = ax.table(cellText=rows, colLabels=headers, colWidths=[0.10, 0.18, 0.72],
                     cellLoc="left", loc="upper left", bbox=[0.0, 0.0, 1.0, 0.94])
    table.auto_set_font_size(False); table.set_fontsize(9)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#e6e6e6")
        if r == 0:
            cell.set_facecolor("#1d3557"); cell.set_text_props(color="white", fontweight="bold")
        else:
            cell.set_facecolor("white" if r % 2 == 1 else "#f7f9fc")


_SEVERITY_COLORS = {
    "debug":    "#9aa5b1",
    "advisory": "#f4a261",
    "regular":  "#e76f51",
    "critical": "#b00020",
}
_LEVEL_COLORS = {
    "none":     "#2a9d8f",
    "advisory": "#f4a261",
    "regular":  "#e76f51",
    "critical": "#b00020",
}


def _draw_warnings_table(ax, warnings):
    if warnings == "disabled" or not warnings:
        ax.set_title("Warnings — disabled / none triggered",
                     fontsize=13, fontweight="bold", loc="left")
        ax.text(0.5, 0.5,
                "The warnings system is currently disabled or no warnings were triggered.",
                ha="center", va="center", transform=ax.transAxes, color="#888888")
        return
    if isinstance(warnings, dict):
        level = warnings.get("overall_warning_level", "—")
        triggered = warnings.get("triggered_warnings", {})
    else:
        level, triggered = "—", {}
    level_color = _LEVEL_COLORS.get(str(level).lower(), "#1d3557")
    ax.set_title(f"Warnings  —  overall level: {level}",
                 fontsize=13, fontweight="bold", loc="left", color=level_color)
    if not triggered:
        ax.text(0.5, 0.5, "No warnings triggered.", ha="center", va="center",
                transform=ax.transAxes, color="#888888")
        return
    headers = ["Warning", "Severity", "Occurrences", "Message"]
    rows, severities = [], []
    for warning_name, w in triggered.items():
        severities.append(w.get("severity", "—"))
        rows.append([warning_name, severities[-1],
                     _fmt(w.get("num_occurences"), "", 0),
                     (w.get("message") or "")[:200]])
    table = ax.table(cellText=rows, colLabels=headers, colWidths=[0.22, 0.10, 0.10, 0.58],
                     cellLoc="left", loc="upper left", bbox=[0.0, 0.0, 1.0, 0.94])
    table.auto_set_font_size(False); table.set_fontsize(9)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#e6e6e6")
        if r == 0:
            cell.set_facecolor("#1d3557"); cell.set_text_props(color="white", fontweight="bold")
        else:
            sev = severities[r - 1].lower() if r - 1 < len(severities) else "debug"
            cell.set_facecolor("white" if r % 2 == 1 else "#f7f9fc")
            if c == 1:
                cell.set_facecolor(_SEVERITY_COLORS.get(sev, "#9aa5b1"))
                cell.set_text_props(color="white", fontweight="bold")


# =============================================================================
# Original time-series plots
# =============================================================================

def make_thrust_plot(sim_results: dict) -> Figure:
    """Thrust vs time — restricted to burn phases per v2 feedback."""
    data = sim_results.get("data", {})
    t_full = _arr(data, "time")
    F_full = _arr(data, "F_thrust")
    phases_full = _phase_arr(data)

    t, F, phases = _trim_to_burn(F_full, t_full, phases_full)

    fig, ax = _open_axes("Thrust vs. time (burn only)", "Thrust")
    ax.set_ylabel("Thrust [N]")
    _shade_phase_bands(ax, t, phases)
    _plot_colored_by_phase(ax, t, F, phases)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.legend(handles=_phase_legend_patches(_present_phases(phases)),
              loc="upper right", fontsize=9, frameon=True)
    fig.tight_layout()
    return fig


def make_injector_mass_flow_plot(sim_results: dict) -> Figure:
    data = sim_results.get("data", {})
    t_full = _arr(data, "time")
    phases_full = _phase_arr(data)

    raw, label = None, "m_dot_o_in [kg/s]"
    if "m_dot_o_in" in data:
        raw = _arr(data, "m_dot_o_in")
    elif "n_dot_ox" in data:
        n_dot = _arr(data, "n_dot_ox")
        flat = _flatten_inputs(sim_results.get("static", {}).get("rocket_inputs", {}))
        n_v0 = _arr(data, "n_v")[0] if len(_arr(data, "n_v")) else 0.0
        n_l0 = _arr(data, "n_l")[0] if len(_arr(data, "n_l")) else 0.0
        ox_mass0 = flat.get("tank_oxidizer_mass_kg", 0.0)
        n_ox0 = n_v0 + n_l0
        W_o = ox_mass0 / n_ox0 if n_ox0 > 0 else 0.044013
        raw = n_dot * W_o
        label = "n_dot_ox · W_o [kg/s]"

    fig, ax = _open_axes("Injector mass flow vs. time", "Injector mass flow")
    ax.set_ylabel(label)
    if raw is None:
        ax.text(0.5, 0.5, "No injector mass flow data found.",
                ha="center", va="center", transform=ax.transAxes, color="#888888")
        return fig

    t, y, phases = _align_to_time(raw, t_full, phases_full)
    _shade_phase_bands(ax, t_full, phases_full)
    _plot_colored_by_phase(ax, t, y, phases)
    if len(t_full) > 0:
        ax.set_xlim(float(np.min(t_full)), float(np.max(t_full)))
    ax.axhline(0, color="black", linewidth=0.6)
    ax.legend(handles=_phase_legend_patches(_present_phases(phases_full)),
              loc="upper right", fontsize=9, frameon=True)
    fig.tight_layout()
    return fig


def make_kinematics_plot(sim_results: dict) -> Figure:
    data = sim_results.get("data", {})
    flat = _flatten_inputs(sim_results.get("static", {}).get("rocket_inputs", {}))
    launch_alt = flat.get("launch_site_altitude_asl_m", 0.0)

    t  = _arr(data, "time")
    sy = _arr(data, "sy_R")
    vx = _arr(data, "vx_R"); vy = _arr(data, "vy_R")
    ax_R = _arr(data, "ax_R"); ay_R = _arr(data, "ay_R")
    phases = _phase_arr(data)

    altitude_agl = sy - launch_alt
    v_mag = np.sqrt(vx**2 + vy**2)
    a_mag = np.sqrt(ax_R**2 + ay_R**2)

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
    if fig.canvas.manager:
        fig.canvas.manager.set_window_title("Kinematics")
    fig.suptitle("Rocket kinematics", fontsize=14, fontweight="bold")
    for ax in axes:
        ax.grid(True, which="both", linestyle="--", alpha=0.5)
        _shade_phase_bands(ax, t, phases)

    axes[0].set_ylabel("Altitude AGL [m]"); _plot_colored_by_phase(axes[0], t, altitude_agl, phases)
    axes[1].set_ylabel("Velocity |v| [m/s]"); _plot_colored_by_phase(axes[1], t, v_mag, phases)
    axes[2].set_ylabel("Acceleration |a| [m/s²]"); _plot_colored_by_phase(axes[2], t, a_mag, phases)
    axes[2].set_xlabel("Time [s]")

    if np.isfinite(altitude_agl).any():
        idx_apo = int(np.nanargmax(altitude_agl))
        ymax = float(altitude_agl[idx_apo])
        axes[0].annotate(f"Apogee: {ymax:,.0f} m AGL  @ t = {t[idx_apo]:.1f} s",
                         xy=(t[idx_apo], ymax),
                         xytext=(t[idx_apo] + 1.0, ymax * 0.92),
                         fontsize=9, color="#1d3557",
                         arrowprops=dict(arrowstyle="->", color="#1d3557", lw=0.8))

    axes[0].legend(handles=_phase_legend_patches(_present_phases(phases)),
                   loc="upper right", fontsize=8.5, frameon=True, ncol=2)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    return fig


def make_of_ratio_plot(sim_results: dict) -> Figure:
    data = sim_results.get("data", {})
    t_full = _arr(data, "time")
    of_full = _arr(data, "OF")
    phases_full = _phase_arr(data)
    t, of, phases = _trim_to_burn(of_full, t_full, phases_full)

    fig, ax = _open_axes("O/F ratio vs. time (burn only)", "O/F ratio")
    ax.set_ylabel("O/F [—]")
    _shade_phase_bands(ax, t, phases)
    _plot_colored_by_phase(ax, t, of, phases)
    ax.axhline(7.0, color="#888888", linestyle=":", linewidth=0.9)
    ax.legend(handles=_phase_legend_patches(_present_phases(phases))
              + [Patch(color="#888888", label="≈ stoichiometric (paraffin / N2O)")],
              loc="upper right", fontsize=9, frameon=True)
    fig.tight_layout()
    return fig


def make_chamber_temperature_plot(sim_results: dict) -> Figure:
    data = sim_results.get("data", {})
    t_full = _arr(data, "time")
    Tc_full = _arr(data, "T_c")
    phases_full = _phase_arr(data)
    t, Tc, phases = _trim_to_burn(Tc_full, t_full, phases_full)

    fig, ax = _open_axes("Chamber temperature vs. time (burn only)", "Chamber temperature")
    ax.set_ylabel("T_c [K]")
    _shade_phase_bands(ax, t, phases)
    _plot_colored_by_phase(ax, t, Tc, phases)
    ax.legend(handles=_phase_legend_patches(_present_phases(phases)),
              loc="lower right", fontsize=9, frameon=True)
    fig.tight_layout()
    return fig


# =============================================================================
# New burn-only time-series plots (A1, A2, A3, A4, A5, A7, A8, A9, A10, A12)
# =============================================================================

def _make_simple_burn_plot(sim_results: dict, key: str,
                           y_label: str, title: str,
                           transform=None) -> Optional[Figure]:
    data = sim_results.get("data", {})
    if key not in data:
        return None
    t_full = _arr(data, "time")
    phases_full = _phase_arr(data)
    raw = _arr(data, key)
    if transform is not None:
        raw = transform(raw)
    # align (handles burn-length arrays automatically)
    t, y, phases = _align_to_time(raw, t_full, phases_full)
    # trim to burn-phase entries
    burn_mask = np.array([p in BURN_PHASES for p in phases])
    if not burn_mask.any():
        return None
    t, y, phases = t[burn_mask], y[burn_mask], phases[burn_mask]

    fig, ax = _open_axes(f"{title} (burn only)", title)
    ax.set_ylabel(y_label)
    _shade_phase_bands(ax, t, phases)
    _plot_colored_by_phase(ax, t, y, phases)
    ax.legend(handles=_phase_legend_patches(_present_phases(phases)),
              loc="best", fontsize=9, frameon=True)
    fig.tight_layout()
    return fig


def make_tank_pressure_plot(sim_results: dict) -> Optional[Figure]:
    return _make_simple_burn_plot(sim_results, "p_T", "Tank pressure [bar]",
                                  "Tank pressure vs. time",
                                  transform=lambda a: a / 1e5)


def make_tank_temperature_plot(sim_results: dict) -> Optional[Figure]:
    return _make_simple_burn_plot(sim_results, "T_T", "Tank temperature [K]",
                                  "Tank temperature vs. time")


def make_chamber_pressure_plot(sim_results: dict) -> Optional[Figure]:
    return _make_simple_burn_plot(sim_results, "p_C", "Chamber pressure [bar]",
                                  "Chamber pressure vs. time",
                                  transform=lambda a: a / 1e5)


def make_oxidizer_inventory_plot(sim_results: dict) -> Optional[Figure]:
    """Stacked area showing oxidizer remaining as liquid mass vs. vapor mass."""
    data = sim_results.get("data", {})
    if "n_v" not in data or "n_l" not in data:
        return None
    flat = _flatten_inputs(sim_results.get("static", {}).get("rocket_inputs", {}))
    n_v_full = _arr(data, "n_v"); n_l_full = _arr(data, "n_l")
    ox_mass0 = flat.get("tank_oxidizer_mass_kg", 0.0)
    n_ox0 = float(n_v_full[0] + n_l_full[0])
    W_o = ox_mass0 / n_ox0 if n_ox0 > 0 else 0.044013

    t_full = _arr(data, "time"); phases_full = _phase_arr(data)
    burn_mask = np.array([p in BURN_PHASES for p in phases_full])
    if not burn_mask.any():
        return None
    t = t_full[burn_mask]
    m_liquid = n_l_full[burn_mask] * W_o
    m_vapor  = n_v_full[burn_mask] * W_o

    fig, ax = _open_axes("Oxidizer remaining vs. time (burn only)", "Oxidizer inventory")
    ax.set_ylabel("Mass [kg]")
    ax.stackplot(t, m_liquid, m_vapor,
                 labels=["Liquid", "Vapor"],
                 colors=["#1d3557", "#a8dadc"], alpha=0.85)
    ax.set_ylim(0, max(float(np.nanmax(m_liquid + m_vapor)) * 1.05, 1e-9))
    ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    return fig


def make_fuel_grain_state_plot(sim_results: dict) -> Optional[Figure]:
    """Port radius (left axis) and fuel mass remaining (right axis)."""
    data = sim_results.get("data", {})
    if "r_f" not in data:
        return None
    flat = _flatten_inputs(sim_results.get("static", {}).get("rocket_inputs", {}))
    R_f   = flat.get("chamber_fuel_external_radius_m", 0.0)
    rho_f = flat.get("chamber_fuel_density_kgm3", 900.0)
    L_f   = flat.get("chamber_fuel_length_m", 0.0)

    t_full = _arr(data, "time")
    r_full = _arr(data, "r_f")
    phases_full = _phase_arr(data)
    burn_mask = np.array([p in BURN_PHASES for p in phases_full])
    if not burn_mask.any():
        return None
    t = t_full[burn_mask]; r = r_full[burn_mask]; phases = phases_full[burn_mask]
    fuel_mass = math.pi * rho_f * L_f * (R_f**2 - r**2)

    fig, ax = _open_axes("Fuel grain state vs. time (burn only)", "Fuel grain state")
    ax.set_ylabel("Port radius r_f [m]", color="#1d3557")
    _shade_phase_bands(ax, t, phases)
    _plot_colored_by_phase(ax, t, r, phases)
    ax.tick_params(axis="y", labelcolor="#1d3557")
    ax.axhline(R_f, color="#888888", linestyle=":", linewidth=0.9, label=f"Fuel OR = {R_f:.4f} m")

    ax2 = ax.twinx()
    ax2.set_ylabel("Fuel mass remaining [kg]", color="#e76f51")
    ax2.plot(t, fuel_mass, color="#e76f51", linewidth=1.5, linestyle="--",
             label="Fuel mass remaining")
    ax2.tick_params(axis="y", labelcolor="#e76f51")

    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines + lines2, labels + labels2, loc="upper right", fontsize=9, frameon=True)
    fig.tight_layout()
    return fig


def make_injector_dp_plot(sim_results: dict) -> Optional[Figure]:
    """Δp across the injector vs. time, overlaid with chamber pressure for context."""
    data = sim_results.get("data", {})
    if "delta_p" not in data or "p_C" not in data:
        return None
    t_full = _arr(data, "time"); phases_full = _phase_arr(data)
    burn_mask = np.array([p in BURN_PHASES for p in phases_full])
    if not burn_mask.any():
        return None

    dp_raw = _arr(data, "delta_p"); pc_raw = _arr(data, "p_C")
    t1, dp, ph1 = _align_to_time(dp_raw, t_full, phases_full)
    t2, pc, _   = _align_to_time(pc_raw, t_full, phases_full)
    burn_m1 = np.array([p in BURN_PHASES for p in ph1])
    burn_m2 = np.array([p in BURN_PHASES for p in _phase_arr(data)[:len(pc_raw)]])

    fig, ax = _open_axes("Injector Δp & chamber pressure vs. time (burn only)",
                         "Injector Δp")
    ax.set_ylabel("Pressure [bar]")
    ax.plot(t1[burn_m1], dp[burn_m1] / 1e5, color="#e63946", linewidth=1.7,
            label="Injector Δp")
    ax.plot(t2[burn_m2], pc[burn_m2] / 1e5, color="#1d3557", linewidth=1.7,
            label="Chamber p_C", linestyle="--")
    ax.axhline(0, color="black", linewidth=0.6)
    ax.legend(loc="upper right", fontsize=9, frameon=True)
    fig.tight_layout()
    return fig


def make_nozzle_exit_plot(sim_results: dict) -> Optional[Figure]:
    """Nozzle exit Mach (left axis) and exit pressure (right axis)."""
    data = sim_results.get("data", {})
    has_M = "M_e" in data
    has_p = "p_e" in data
    if not (has_M or has_p):
        return None

    t_full = _arr(data, "time"); phases_full = _phase_arr(data)
    fig, ax = _open_axes("Nozzle exit conditions vs. time (burn only)",
                         "Nozzle exit conditions")

    if has_M:
        M_e = _arr(data, "M_e")
        t1, M, ph1 = _align_to_time(M_e, t_full, phases_full)
        burn_m1 = np.array([p in BURN_PHASES for p in ph1])
        ax.plot(t1[burn_m1], M[burn_m1], color="#1d3557", linewidth=1.7, label="Exit Mach M_e")
        ax.set_ylabel("Exit Mach M_e [—]", color="#1d3557")
        ax.tick_params(axis="y", labelcolor="#1d3557")

    if has_p:
        p_e = _arr(data, "p_e")
        t2, p, ph2 = _align_to_time(p_e, t_full, phases_full)
        burn_m2 = np.array([p_ in BURN_PHASES for p_ in ph2])
        axR = ax.twinx()
        axR.plot(t2[burn_m2], p[burn_m2] / 1e5, color="#e76f51", linewidth=1.5,
                 linestyle="--", label="Exit pressure p_e")
        axR.set_ylabel("Exit pressure [bar]", color="#e76f51")
        axR.tick_params(axis="y", labelcolor="#e76f51")

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = (ax.figure.axes[-1].get_legend_handles_labels() if has_p else ([], []))
    if h1 or h2:
        ax.legend(h1 + h2, l1 + l2, loc="best", fontsize=9, frameon=True)
    fig.tight_layout()
    return fig


def make_flow_regime_plot(sim_results: dict) -> Optional[Figure]:
    """Categorical strip showing nozzle flow regime over the burn."""
    data = sim_results.get("data", {})
    if "flow_regime" not in data:
        return None
    regime_raw = data["flow_regime"]
    t_full = _arr(data, "time"); phases_full = _phase_arr(data)
    n = len(regime_raw)
    t = t_full[:n] if n <= len(t_full) else t_full
    phases = phases_full[:n] if n <= len(phases_full) else phases_full
    burn_mask = np.array([p in BURN_PHASES for p in phases])
    if not burn_mask.any():
        return None
    t = t[burn_mask]
    regime = [r if r is not None else "?" for r in np.array(regime_raw)[burn_mask]]

    fig, ax = _open_axes("Nozzle flow regime vs. time (burn only)", "Flow regime")
    ax.set_ylabel("Regime")
    unique = list(dict.fromkeys(regime))  # preserve order
    y_pos = {name: i for i, name in enumerate(unique)}
    colors = plt.get_cmap("tab10")
    for i, name in enumerate(unique):
        mask = np.array([r == name for r in regime])
        ax.scatter(t[mask], np.full(mask.sum(), y_pos[name]),
                   s=12, color=colors(i % 10), label=name)
    ax.set_yticks(list(y_pos.values()))
    ax.set_yticklabels(list(y_pos.keys()))
    ax.legend(loc="upper right", fontsize=9, frameon=True)
    fig.tight_layout()
    return fig


def make_combustion_properties_plot(sim_results: dict) -> Optional[Figure]:
    """gamma, W_c, c_star on three stacked subplots, burn only."""
    data = sim_results.get("data", {})
    keys = [("gamma",  "γ [—]"),
            ("W_c",    "W_c [kg/mol]"),
            ("cstar",  "c* [m/s]")]
    available = [(k, lbl) for k, lbl in keys if k in data]
    if not available:
        return None

    t_full = _arr(data, "time"); phases_full = _phase_arr(data)

    fig, axes = plt.subplots(len(available), 1, figsize=(11, 2.6 * len(available) + 1),
                             sharex=True)
    if len(available) == 1:
        axes = [axes]
    if fig.canvas.manager:
        fig.canvas.manager.set_window_title("Combustion properties")
    fig.suptitle("Combustion properties vs. time (burn only)", fontsize=14, fontweight="bold")

    for ax_i, (k, lbl) in zip(axes, available):
        y_raw = _arr(data, k)
        t, y, ph = _align_to_time(y_raw, t_full, phases_full)
        burn_mask = np.array([p in BURN_PHASES for p in ph])
        if not burn_mask.any():
            continue
        ax_i.grid(True, linestyle="--", alpha=0.5)
        ax_i.set_ylabel(lbl)
        _shade_phase_bands(ax_i, t[burn_mask], ph[burn_mask])
        _plot_colored_by_phase(ax_i, t[burn_mask], y[burn_mask], ph[burn_mask])
    axes[-1].set_xlabel("Time [s]")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    return fig


def make_ambient_atmosphere_plot(sim_results: dict) -> Optional[Figure]:
    """T_amb, p_amb, rho_amb on three stacked subplots, burn only."""
    data = sim_results.get("data", {})
    spec = [("T_amb",   "T_amb [K]",         None),
            ("p_amb",   "p_amb [bar]",       lambda a: a / 1e5),
            ("rho_amb", "ρ_amb [kg/m³]",     None)]
    available = [(k, lbl, tx) for k, lbl, tx in spec if k in data]
    if not available:
        return None

    t_full = _arr(data, "time"); phases_full = _phase_arr(data)
    burn_mask_full = np.array([p in BURN_PHASES for p in phases_full])
    if not burn_mask_full.any():
        return None

    fig, axes = plt.subplots(len(available), 1, figsize=(11, 2.6 * len(available) + 1),
                             sharex=True)
    if len(available) == 1:
        axes = [axes]
    if fig.canvas.manager:
        fig.canvas.manager.set_window_title("Ambient atmosphere")
    fig.suptitle("Ambient atmosphere vs. time (burn only)", fontsize=14, fontweight="bold")

    for ax_i, (k, lbl, tx) in zip(axes, available):
        y = _arr(data, k)[burn_mask_full]
        if tx is not None:
            y = tx(y)
        ax_i.grid(True, linestyle="--", alpha=0.5)
        ax_i.set_ylabel(lbl)
        _shade_phase_bands(ax_i, t_full[burn_mask_full], phases_full[burn_mask_full])
        _plot_colored_by_phase(ax_i, t_full[burn_mask_full], y, phases_full[burn_mask_full])
    axes[-1].set_xlabel("Time [s]")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    return fig


def make_isp_plot(sim_results: dict) -> Optional[Figure]:
    """Isp = F / (ṁ_total · g0) vs. time, burn only."""
    data = sim_results.get("data", {})
    if "F_thrust" not in data:
        return None
    t_full = _arr(data, "time"); phases_full = _phase_arr(data)
    F_full = _arr(data, "F_thrust")

    # mass flow from m_dot_n if present, else from m_dot_o_in + m_dot_f_in
    if "m_dot_n" in data:
        mdot_raw = _arr(data, "m_dot_n")
        t_m, mdot, ph_m = _align_to_time(mdot_raw, t_full, phases_full)
    elif "m_dot_o_in" in data and "m_dot_f_in" in data:
        ox = _arr(data, "m_dot_o_in"); fu = _arr(data, "m_dot_f_in")
        n = min(len(ox), len(fu))
        mdot_raw = ox[:n] + fu[:n]
        t_m, mdot, ph_m = _align_to_time(mdot_raw, t_full, phases_full)
    else:
        return None

    # align F to the mass-flow timebase
    if len(F_full) == len(t_full):
        F = np.interp(t_m, t_full, F_full)
    else:
        F = F_full[:len(t_m)]

    g0 = 9.80665
    with np.errstate(divide="ignore", invalid="ignore"):
        Isp = np.where(mdot > 0, F / (mdot * g0), np.nan)

    burn_mask = np.array([p in BURN_PHASES for p in ph_m])
    if not burn_mask.any():
        return None
    t = t_m[burn_mask]; y = Isp[burn_mask]; phases = ph_m[burn_mask]

    fig, ax = _open_axes("Specific impulse vs. time (burn only)", "Isp")
    ax.set_ylabel("Isp [s]")
    _shade_phase_bands(ax, t, phases)
    _plot_colored_by_phase(ax, t, y, phases)
    ax.legend(handles=_phase_legend_patches(_present_phases(phases)),
              loc="lower right", fontsize=9, frameon=True)
    fig.tight_layout()
    return fig


def make_rocket_total_mass_plot(sim_results: dict) -> Optional[Figure]:
    """Rocket total mass vs. time, if (and only if) CV6 logged it.

    Per design note: this plot is skipped when the saved data doesn't include
    a total-mass series. Recognized keys: `m_total`, `rocket_mass_kg`,
    `m_rocket`.
    """
    data = sim_results.get("data", {})
    for key in ("m_total", "rocket_mass_kg", "m_rocket"):
        if key in data:
            return _make_simple_burn_plot(sim_results, key, "Rocket mass [kg]",
                                          "Rocket total mass vs. time")
    return None


# =============================================================================
# Non-time-axis plots (B1, B2, B3)
# =============================================================================

def make_trajectory_map(sim_results: dict) -> Figure:
    """Altitude AGL vs downrange (sy_R vs sx_R), colored by phase."""
    data = sim_results.get("data", {})
    flat = _flatten_inputs(sim_results.get("static", {}).get("rocket_inputs", {}))
    launch_alt = flat.get("launch_site_altitude_asl_m", 0.0)
    sx = _arr(data, "sx_R"); sy = _arr(data, "sy_R"); phases = _phase_arr(data)
    agl = sy - launch_alt

    fig = plt.figure(figsize=(11, 7))
    if fig.canvas.manager:
        fig.canvas.manager.set_window_title("Trajectory map")
    fig.suptitle("Trajectory — altitude vs. downrange", fontsize=14, fontweight="bold")
    ax = fig.add_subplot(111)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.set_xlabel("Downrange [m]")
    ax.set_ylabel("Altitude AGL [m]")

    _plot_colored_by_phase(ax, sx, agl, phases)

    # apogee marker
    if np.isfinite(agl).any():
        idx_apo = int(np.nanargmax(agl))
        ax.scatter([sx[idx_apo]], [agl[idx_apo]], s=80, marker="*",
                   color="#1d3557", zorder=5, label="Apogee")
        ax.annotate(f"  apogee {agl[idx_apo]:,.0f} m",
                    (sx[idx_apo], agl[idx_apo]),
                    fontsize=9, color="#1d3557")
    ax.scatter([sx[0]], [agl[0]], s=60, marker="o", color="#2a9d8f",
               zorder=5, label="Launch")
    ax.legend(handles=_phase_legend_patches(_present_phases(phases))
              + [Patch(color="#1d3557", label="Apogee"),
                 Patch(color="#2a9d8f", label="Launch")],
              loc="best", fontsize=8.5, frameon=True, ncol=2)
    ax.set_aspect("auto")
    fig.tight_layout()
    return fig


def make_of_vs_radius_plot(sim_results: dict) -> Optional[Figure]:
    data = sim_results.get("data", {})
    if "OF" not in data or "r_f" not in data:
        return None
    t_full = _arr(data, "time"); phases_full = _phase_arr(data)
    of_full = _arr(data, "OF"); r_full = _arr(data, "r_f")
    burn_mask = np.array([p in BURN_PHASES for p in phases_full])
    if not burn_mask.any():
        return None
    of = of_full[burn_mask]; r = r_full[burn_mask]; phases = phases_full[burn_mask]

    fig, ax = plt.subplots(figsize=(11, 6))
    if fig.canvas.manager:
        fig.canvas.manager.set_window_title("O/F vs. port radius")
    fig.suptitle("O/F ratio vs. fuel port radius (burn only)", fontsize=14, fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.set_xlabel("Port radius r_f [m]")
    ax.set_ylabel("O/F [—]")

    finite = np.isfinite(of) & np.isfinite(r)
    cs = [PHASE_COLORS.get(p, "#bdbdbd") for p in phases[finite]]
    ax.scatter(r[finite], of[finite], s=8, c=cs, alpha=0.8)
    ax.axhline(7.0, color="#888888", linestyle=":", linewidth=0.9,
               label="≈ stoichiometric")
    ax.legend(handles=_phase_legend_patches(_present_phases(phases))
              + [Patch(color="#888888", label="≈ stoichiometric")],
              loc="best", fontsize=9, frameon=True)
    fig.tight_layout()
    return fig


def make_thrust_vs_pc_plot(sim_results: dict) -> Optional[Figure]:
    data = sim_results.get("data", {})
    if "F_thrust" not in data or "p_C" not in data:
        return None
    t_full = _arr(data, "time"); phases_full = _phase_arr(data)
    F = _arr(data, "F_thrust"); pc = _arr(data, "p_C")
    burn_mask = np.array([p in BURN_PHASES for p in phases_full])
    if not burn_mask.any():
        return None
    F = F[burn_mask]; pc = pc[burn_mask]; phases = phases_full[burn_mask]

    fig, ax = plt.subplots(figsize=(11, 6))
    if fig.canvas.manager:
        fig.canvas.manager.set_window_title("Thrust vs Pc")
    fig.suptitle("Thrust vs. chamber pressure (burn only)", fontsize=14, fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.set_xlabel("Chamber pressure p_C [bar]")
    ax.set_ylabel("Thrust [N]")

    finite = np.isfinite(F) & np.isfinite(pc)
    cs = [PHASE_COLORS.get(p, "#bdbdbd") for p in phases[finite]]
    ax.scatter(pc[finite] / 1e5, F[finite], s=10, c=cs, alpha=0.8)
    ax.legend(handles=_phase_legend_patches(_present_phases(phases)),
              loc="best", fontsize=9, frameon=True)
    fig.tight_layout()
    return fig


# =============================================================================
# Diagnostics (D1, D2, D3, D4)
# =============================================================================

def make_solver_step_size_plot(sim_results: dict) -> Optional[Figure]:
    data = sim_results.get("data", {})
    t = _arr(data, "time")
    if len(t) < 2:
        return None
    dt = np.diff(t)
    phases = _phase_arr(data)
    fig, ax = _open_axes("Solver step size dt vs. time", "Solver dt")
    ax.set_ylabel("dt [s]")
    ax.set_yscale("log")
    _shade_phase_bands(ax, t, phases)
    ax.plot(t[:-1], dt, color="#1d3557", linewidth=0.9, drawstyle="steps-post")
    ax.legend(handles=_phase_legend_patches(_present_phases(phases)),
              loc="upper right", fontsize=9, frameon=True)
    fig.tight_layout()
    return fig


def make_nan_map_plot(sim_results: dict) -> Optional[Figure]:
    """For each derived variable that has any NaN, show where in time they occur."""
    data = sim_results.get("data", {})
    if "time" not in data:
        return None
    t_full = _arr(data, "time")
    if len(t_full) == 0:
        return None

    bad: list[tuple[str, np.ndarray, np.ndarray]] = []
    for k, v in data.items():
        if k in ("time", "phase", "flow_regime"):
            continue
        if not isinstance(v, list):
            continue
        y = _arr(data, k)
        nan_mask = ~np.isfinite(y)
        if not nan_mask.any():
            continue
        if len(y) == len(t_full):
            t_local = t_full
        else:
            t_local = t_full[:len(y)]
        bad.append((k, t_local, nan_mask))

    fig = plt.figure(figsize=(11, max(2.5, 0.30 * (len(bad) + 1) + 1.5)))
    if fig.canvas.manager:
        fig.canvas.manager.set_window_title("NaN map")
    fig.suptitle(f"NaN map — variables with NaN values ({len(bad)})",
                 fontsize=14, fontweight="bold")
    ax = fig.add_subplot(111)

    if not bad:
        ax.text(0.5, 0.5, "No NaNs in any logged variable. 🎉",
                ha="center", va="center", transform=ax.transAxes, color="#2a9d8f",
                fontsize=12)
        ax.set_axis_off()
        fig.tight_layout()
        return fig

    ax.set_xlim(float(np.min(t_full)), float(np.max(t_full)))
    ax.set_ylim(-0.5, len(bad) - 0.5)
    ax.set_yticks(range(len(bad)))
    ax.set_yticklabels([k for k, _, _ in bad])
    ax.set_xlabel("Time [s]")
    ax.grid(True, axis="x", linestyle="--", alpha=0.5)

    for i, (name, t_local, mask) in enumerate(bad):
        ax.scatter(t_local[mask], np.full(mask.sum(), i),
                   marker="|", s=40, color="#e63946")

    fig.tight_layout()
    return fig


def make_mass_conservation_plot(sim_results: dict) -> Optional[Figure]:
    """Check ∫m_dot_n dt against (initial − current) propellant inventory."""
    data = sim_results.get("data", {})
    flat = _flatten_inputs(sim_results.get("static", {}).get("rocket_inputs", {}))
    if "m_dot_n" not in data or "n_v" not in data or "n_l" not in data or "r_f" not in data:
        return None
    t_full = _arr(data, "time"); phases_full = _phase_arr(data)
    n_v = _arr(data, "n_v"); n_l = _arr(data, "n_l"); r_f = _arr(data, "r_f")
    ox_mass_initial = flat.get("tank_oxidizer_mass_kg", 0.0)
    R_f = flat.get("chamber_fuel_external_radius_m", 0.0)
    rho_f = flat.get("chamber_fuel_density_kgm3", 900.0)
    L_f = flat.get("chamber_fuel_length_m", 0.0)
    n_ox0 = float(n_v[0] + n_l[0])
    W_o = ox_mass_initial / n_ox0 if n_ox0 > 0 else 0.044013

    burn_mask = np.array([p in BURN_PHASES for p in phases_full])
    if not burn_mask.any():
        return None

    # propellant remaining over time (tank + grain), burn-only slice
    ox_remaining = (n_v + n_l) * W_o
    fuel_initial = math.pi * rho_f * L_f * (R_f**2 - float(r_f[0])**2)
    fuel_remaining = math.pi * rho_f * L_f * (R_f**2 - r_f**2)
    total_remaining = ox_remaining + fuel_remaining
    consumed_inventory = (ox_mass_initial + fuel_initial) - total_remaining

    # cumulative ∫m_dot_n dt (aligned to its own timebase)
    mdot_n = _arr(data, "m_dot_n")
    t_m, mdot, ph_m = _align_to_time(mdot_n, t_full, phases_full)
    burn_m = np.array([p in BURN_PHASES for p in ph_m])
    t_m_b = t_m[burn_m]; mdot_b = mdot[burn_m]
    if len(t_m_b) < 2:
        return None
    consumed_nozzle = np.concatenate(([0.0], np.cumsum(0.5 * (mdot_b[:-1] + mdot_b[1:])
                                                       * np.diff(t_m_b))))

    fig, ax = _open_axes("Mass conservation check (burn only)", "Mass conservation")
    ax.set_ylabel("Cumulative mass consumed [kg]")
    ax.plot(t_full[burn_mask], consumed_inventory[burn_mask],
            color="#1d3557", linewidth=1.8, label="Inventory drop (tank + grain)")
    ax.plot(t_m_b, consumed_nozzle, color="#e76f51", linewidth=1.5, linestyle="--",
            label="∫ m_dot_n dt")
    ax.legend(loc="upper left", fontsize=9, frameon=True)
    # residual on twin axis
    if len(t_full[burn_mask]) > 1:
        # interpolate the nozzle integral onto the inventory timebase
        cn_interp = np.interp(t_full[burn_mask], t_m_b, consumed_nozzle)
        residual = consumed_inventory[burn_mask] - cn_interp
        ax2 = ax.twinx()
        ax2.plot(t_full[burn_mask], residual, color="#9aa5b1",
                 linewidth=0.9, label="Residual")
        ax2.axhline(0, color="black", linewidth=0.5)
        ax2.set_ylabel("Residual [kg]", color="#9aa5b1")
        ax2.tick_params(axis="y", labelcolor="#9aa5b1")
    fig.tight_layout()
    return fig


def make_thrust_with_events_plot(sim_results: dict) -> Figure:
    data = sim_results.get("data", {})
    event_log = sim_results.get("event_log", [])
    t_full = _arr(data, "time"); F_full = _arr(data, "F_thrust")
    phases_full = _phase_arr(data)
    t, F, phases = _trim_to_burn(F_full, t_full, phases_full)

    fig, ax = _open_axes("Thrust with event markers (burn only)",
                         "Thrust + events")
    ax.set_ylabel("Thrust [N]")
    _shade_phase_bands(ax, t, phases)
    _plot_colored_by_phase(ax, t, F, phases)
    # event vertical lines
    if len(t) > 0:
        t_max = float(np.max(t))
        for ev in event_log:
            t_ev = ev.get("t_s")
            if t_ev is None or t_ev > t_max:
                continue
            ax.axvline(t_ev, color="#1d3557", linestyle="--", linewidth=0.9)
            short = ev.get("message", "")
            short = short.split("Exiting")[-1].strip() if "Exiting" in short else short[:60]
            ax.text(t_ev, ax.get_ylim()[1] * 0.95, f"  {short}",
                    fontsize=8, color="#1d3557", rotation=90, va="top")
    ax.legend(handles=_phase_legend_patches(_present_phases(phases)),
              loc="upper right", fontsize=9, frameon=True)
    fig.tight_layout()
    return fig


# =============================================================================
# Geometry sketches (H1, H2)
# =============================================================================

def make_rocket_cross_section(sim_results: dict) -> Optional[Figure]:
    """A scale side-view sketch built from the static rocket_inputs."""
    flat = _flatten_inputs(sim_results.get("static", {}).get("rocket_inputs", {}))

    # tank dimensions
    R_tank   = flat.get("tank_internal_radius_m")
    L_tank   = flat.get("tank_internal_shell_length_m")
    # chamber / grain dimensions
    R_grain  = flat.get("chamber_fuel_external_radius_m")
    L_grain  = flat.get("chamber_fuel_length_m")
    V_pre    = flat.get("pre_chamber_volume_m3", 0.0)
    V_post   = flat.get("post_chamber_volume_m3", 0.0)
    # initial port radius (best estimate)
    if "data" in sim_results and "r_f" in sim_results["data"]:
        r0 = float(_arr(sim_results["data"], "r_f")[0])
    else:
        r0 = 0.0
    # nozzle
    R_throat = flat.get("nozzle_throat_radius_m")
    R_exit   = flat.get("nozzle_exit_radius_m")
    # external rocket OR (from frontal area)
    A_ref = flat.get("rocket_frontal_area_m2")
    R_ext = math.sqrt(A_ref / math.pi) if A_ref else None

    if R_tank is None or L_tank is None or R_grain is None or L_grain is None:
        return None  # not enough geometry

    # derive pre/post chamber lengths from volumes assuming chamber OR
    R_chmb = R_grain  # the chamber radius matches the fuel OR
    L_pre  = (V_pre  / (math.pi * R_chmb**2)) if V_pre  else 0.05
    L_post = (V_post / (math.pi * R_chmb**2)) if V_post else 0.05
    L_nozzle = 0.6 * (R_exit or 0.0)  # purely cosmetic length

    # x layout
    x0 = 0.0
    x_tank_end    = x0 + L_tank
    x_pre_start   = x_tank_end + 0.05         # small gap = valve + injector
    x_pre_end     = x_pre_start + L_pre
    x_grain_end   = x_pre_end + L_grain
    x_post_end    = x_grain_end + L_post
    x_nozzle_end  = x_post_end + L_nozzle
    total_L       = x_nozzle_end - x0

    fig, ax = plt.subplots(figsize=(14, 5))
    if fig.canvas.manager:
        fig.canvas.manager.set_window_title("Rocket cross-section")
    fig.suptitle("Rocket cross-section (axisymmetric side view, axial-to-radial NOT to scale)",
                 fontsize=14, fontweight="bold")
    ax.set_xlabel("Axial position [m]")
    ax.set_ylabel("Radius [m]")
    # equal aspect makes the radial dimension invisible since a rocket is much
    # longer than it is wide; use proportional axes instead.

    # external hull (top + bottom) if R_ext is known
    if R_ext is not None:
        ax.add_patch(Rectangle((x0, -R_ext), total_L, 2 * R_ext,
                               facecolor="#f1faee", edgecolor="#999", linewidth=0.8))
    # tank
    ax.add_patch(Rectangle((x0, -R_tank), L_tank, 2 * R_tank,
                           facecolor="#a8dadc", edgecolor="#1d3557", linewidth=1.2,
                           label="Tank"))
    # pre-chamber
    ax.add_patch(Rectangle((x_pre_start, -R_chmb), L_pre, 2 * R_chmb,
                           facecolor="#e9c46a", edgecolor="#1d3557", linewidth=1.0,
                           label="Pre-chamber"))
    # fuel grain (outer shaded, inner port white)
    ax.add_patch(Rectangle((x_pre_end, -R_grain), L_grain, 2 * R_grain,
                           facecolor="#f4a261", edgecolor="#1d3557", linewidth=1.2,
                           label="Fuel grain"))
    if r0 > 0:
        ax.add_patch(Rectangle((x_pre_end, -r0), L_grain, 2 * r0,
                               facecolor="white", edgecolor="#1d3557",
                               linewidth=0.8, label="Initial port"))
    # post-chamber
    ax.add_patch(Rectangle((x_grain_end, -R_chmb), L_post, 2 * R_chmb,
                           facecolor="#e9c46a", edgecolor="#1d3557", linewidth=1.0))
    # nozzle (converging-diverging)
    if R_throat and R_exit:
        # converging cone from R_chmb to R_throat over half of L_nozzle
        L_conv = 0.35 * L_nozzle
        x_throat = x_post_end + L_conv
        ax.add_patch(Polygon([
            (x_post_end, R_chmb), (x_throat, R_throat),
            (x_nozzle_end, R_exit), (x_nozzle_end, -R_exit),
            (x_throat, -R_throat), (x_post_end, -R_chmb)
        ], facecolor="#e76f51", edgecolor="#1d3557", linewidth=1.2, label="Nozzle"))
        # annotate
        ax.annotate(f"throat r = {R_throat*1000:.1f} mm",
                    xy=(x_throat, R_throat), xytext=(x_throat, R_throat + 0.05),
                    fontsize=8, ha="center", color="#1d3557",
                    arrowprops=dict(arrowstyle="->", lw=0.7, color="#1d3557"))
        ax.annotate(f"exit r = {R_exit*1000:.1f} mm",
                    xy=(x_nozzle_end, R_exit), xytext=(x_nozzle_end, R_exit + 0.05),
                    fontsize=8, ha="center", color="#1d3557",
                    arrowprops=dict(arrowstyle="->", lw=0.7, color="#1d3557"))

    # dimension annotations
    pad = 0.04
    y_dim = -(R_ext or R_grain) - 0.04
    ax.annotate("", xy=(x0, y_dim), xytext=(x_tank_end, y_dim),
                arrowprops=dict(arrowstyle="<->", color="#666"))
    ax.text((x0 + x_tank_end) / 2, y_dim - pad, f"L_tank = {L_tank*1000:.0f} mm",
            ha="center", va="top", fontsize=9, color="#444")
    ax.annotate("", xy=(x_pre_end, y_dim), xytext=(x_grain_end, y_dim),
                arrowprops=dict(arrowstyle="<->", color="#666"))
    ax.text((x_pre_end + x_grain_end) / 2, y_dim - pad,
            f"L_grain = {L_grain*1000:.0f} mm",
            ha="center", va="top", fontsize=9, color="#444")

    # legend
    ax.legend(loc="upper left", fontsize=8.5, frameon=True)
    # explicit limits so equal-aspect doesn't crop the nozzle
    x_margin = 0.05 * total_L
    ax.set_xlim(x0 - x_margin, x_nozzle_end + x_margin)
    y_range = max((R_ext or R_grain) * 1.6, (R_exit or R_grain) * 2.0)
    ax.set_ylim(-y_range, y_range)
    fig.tight_layout()
    return fig


def make_nozzle_profile(sim_results: dict) -> Optional[Figure]:
    flat = _flatten_inputs(sim_results.get("static", {}).get("rocket_inputs", {}))
    R_throat = flat.get("nozzle_throat_radius_m")
    R_exit   = flat.get("nozzle_exit_radius_m")
    if R_throat is None or R_exit is None:
        return None
    eps = (R_exit / R_throat) ** 2

    # smooth bell using a half-cosine-style profile between throat and exit
    L_conv = 1.5 * R_throat
    L_div  = 3.0 * R_exit
    x_conv = np.linspace(-L_conv, 0.0, 50)
    R_conv = R_throat + (1.5 * R_throat) * (x_conv / -L_conv) ** 2
    x_div = np.linspace(0.0, L_div, 60)
    # rao-style 80% bell approximation
    R_div = R_throat + (R_exit - R_throat) * (1 - (1 - x_div / L_div) ** 2)

    x = np.concatenate([x_conv, x_div])
    R = np.concatenate([R_conv, R_div])

    fig, ax = plt.subplots(figsize=(11, 6))
    if fig.canvas.manager:
        fig.canvas.manager.set_window_title("Nozzle profile")
    fig.suptitle(f"Nozzle profile  —  ε = Ae/At = {eps:.2f}",
                 fontsize=14, fontweight="bold")
    ax.set_xlabel("Axial position [m]")
    ax.set_ylabel("Radius [m]")
    ax.set_aspect("equal")
    ax.grid(True, linestyle="--", alpha=0.5)

    ax.fill_between(x, -R,  R, color="#f1faee", edgecolor="none")
    ax.plot(x,  R, color="#1d3557", linewidth=1.5)
    ax.plot(x, -R, color="#1d3557", linewidth=1.5)

    # throat + exit annotations
    ax.axvline(0.0, color="#888", linestyle=":", linewidth=0.8)
    ax.annotate(f"throat r_t = {R_throat*1000:.1f} mm",
                xy=(0.0, R_throat), xytext=(-0.5 * L_conv, R_exit + 0.01),
                fontsize=9, color="#1d3557",
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#1d3557"))
    ax.annotate(f"exit r_e = {R_exit*1000:.1f} mm",
                xy=(L_div, R_exit), xytext=(0.6 * L_div, R_exit + 0.03),
                fontsize=9, color="#1d3557",
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#1d3557"))
    fig.tight_layout()
    return fig


# =============================================================================
# Output drivers
# =============================================================================

def _build_and_display_in_batches(plan: list, sim_results: dict,
                                  batch_size: int) -> None:
    """
    Build figures one batch at a time and show that batch with plt.show().

    plt.show() blocks until the user closes every window in the current batch;
    plt.close("all") then clears them before we build the next batch. This is
    the only reliable way to cap on-screen windows, because plt.show() shows
    every figure pyplot currently manages — there is no "show subset" API.
    """
    batch_size = max(1, int(batch_size))
    selected = [(name, builder) for (name, flag, builder) in plan if flag]
    if not selected:
        return

    i = 0
    batch_num = 0
    while i < len(selected):
        batch_num += 1
        end = min(i + batch_size, len(selected))
        print(f"Showing batch {batch_num}: items {i + 1}–{end} of {len(selected)}…")
        for name, builder in selected[i:end]:
            try:
                fig = builder(sim_results)
                if fig is None:
                    continue
            except Exception as exc:
                print(f"  ! skipped {name}: {type(exc).__name__}: {exc}")
                continue
        plt.show()        # blocks until user closes the batch's windows
        plt.close("all")  # clean slate for the next batch
        i = end


def _save_figures_to_pdf(figures: list[Figure], names: list[str],
                         out_dir: Path) -> Path:
    """Save all figures to a single PDF; returns the PDF path."""
    pdf_path = out_dir / "unsteady_results.pdf"
    with PdfPages(pdf_path) as pdf:
        for fig, name in zip(figures, names):
            pdf.savefig(fig, bbox_inches="tight")
    print(f"  PDF saved -> {pdf_path}")
    return pdf_path


def _save_figures_to_png(figures: list[Figure], names: list[str],
                         out_dir: Path) -> Path:
    """Save each figure as its own PNG inside out_dir."""
    for i, (fig, name) in enumerate(zip(figures, names), start=1):
        png_path = out_dir / f"{i:02d}_{name}.png"
        fig.savefig(png_path, dpi=140, bbox_inches="tight")
    print(f"  PNGs saved -> {out_dir}/ ({len(figures)} files)")
    return out_dir


# =============================================================================
# Module-runnable convenience
# =============================================================================

if __name__ == "__main__":
    # ------------------------------------------------------------------
    # FULL DEMO CALL — copy/paste and adjust as needed.
    # All boolean toggles below show their defaults explicitly. Set any to
    # False to skip that plot in both the on-screen pop-ups AND the
    # PDF / PNG outputs.
    # ------------------------------------------------------------------
    unsteady_results(
        json_filename=None,                 # None -> auto-pick most recent
        json_filepath=None,                 # None -> default results directory

        # ----- output behaviour -----
        display_graphs=True,                # False = headless (no windows)
        save_to_pdf=False,                  # True  = also write one multipage PDF
        save_to_png=False,                  # True  = also write one PNG per plot
        max_concurrent_figures=10,          # batch size for on-screen display (max. number of graphs you will see at once)

        # ----- textual panels (always rendered first) -----
        performance_panel=True,
        events_warnings_panel=True,

        # ----- original time-series plots -----
        thrust_vs_time=True,
        injector_mass_flow_vs_time=True,
        rocket_kinematics=True,
        of_ratio_vs_time=True,
        chamber_temperature_vs_time=True,

        # ----- burn-only time-series plots -----
        tank_pressure_vs_time=True,
        tank_temperature_vs_time=True,
        chamber_pressure_vs_time=True,
        oxidizer_inventory_vs_time=True,
        fuel_grain_state_vs_time=True,
        injector_pressure_drop_vs_time=True,
        nozzle_exit_conditions_vs_time=True,
        nozzle_flow_regime_vs_time=True,
        combustion_properties_vs_time=True,
        ambient_atmosphere_vs_time=True,
        isp_vs_time=True,
        rocket_total_mass_vs_time=True,     # skipped automatically if not saved

        # ----- non-time-axis plots -----
        trajectory_map=True,
        of_vs_port_radius=True,
        thrust_vs_chamber_pressure=True,

        # ----- diagnostics -----
        solver_step_size=True,
        nan_map=True,
        mass_conservation_check=True,
        thrust_with_event_markers=True,

        # ----- geometry sketches -----
        rocket_cross_section=True,
        nozzle_profile=True,
    )