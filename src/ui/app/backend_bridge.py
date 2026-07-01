"""
Thin wrappers around the simulator's existing analysis tools.

Keeping all backend calls behind this module means:
  - the UI never touches sys.path / module imports directly,
  - swapping implementations later (subprocess, threading, etc.) is a one-file change.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


# =============================================================================
# Path discovery
# =============================================================================

def project_root() -> Path:
    """
    Walk up from this file until we find the project root.

    Project root is identified by having a `user_data/` directory.
    Works for both source layout (running .py) and PyInstaller bundles when
    we ship `user_data/` alongside the executable.
    """
    here = Path(__file__).resolve()
    for candidate in [here.parent, *here.parents]:
        if (candidate / "user_data").exists():
            return candidate
    # Fallback: assume the conventional layout (src/ui/app/backend_bridge.py)
    return here.parents[3]


def steady_presets_dir() -> Path:
    return project_root() / "user_data" / "simulation_configs" / "steady"


def steady_results_dir() -> Path:
    return project_root() / "user_data" / "simulation_results" / "steady"


def unsteady_presets_dir() -> Path:
    return project_root() / "user_data" / "simulation_configs" / "unsteady"


def unsteady_results_dir() -> Path:
    return project_root() / "user_data" / "simulation_results" / "unsteady"


# =============================================================================
# JSONC helpers (matches what variable_initialization.py uses)
# =============================================================================

def load_jsonc(path: Path) -> dict:
    """
    Read a JSON-with-comments file.

    Mirrors the regex-strip approach the simulator backend already uses, so
    we accept exactly the same files (including line comments and block
    comments).
    """
    text = Path(path).read_text(encoding="utf-8")
    text = re.sub(r"//.*?$|/\*.*?\*/", "", text, flags=re.MULTILINE | re.DOTALL)
    return json.loads(text)


def save_jsonc(path: Path, data: dict) -> None:
    """Write a dict as JSON (with .jsonc extension by convention)."""
    Path(path).write_text(
        json.dumps(data, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )


# =============================================================================
# Unsteady — list & visualize saved results
# =============================================================================

def list_unsteady_results() -> list[Path]:
    """All saved unsteady result JSONs, newest first."""
    d = unsteady_results_dir()
    if not d.exists():
        return []
    return sorted(d.glob("*.json"), reverse=True)


def show_unsteady_results(results_file: Path) -> None:
    """
    Call display_unsteady_results on a saved file.

    Note: matplotlib's plt.show() blocks until the user closes every figure.
    """
    from src.backend.unsteady.analysis.unsteady_results import display_unsteady_results
    display_unsteady_results(
        json_filename=results_file.name,
        json_filepath=results_file.parent,
    )


# =============================================================================
# Steady — presets
# =============================================================================

def list_steady_presets() -> list[Path]:
    """All saved steady-input presets, newest first."""
    d = steady_presets_dir()
    if not d.exists():
        return []
    return sorted(d.glob("*.jsonc")) + sorted(d.glob("*.json"))


# =============================================================================
# Steady — validation
# =============================================================================

# These are the rocket_inputs keys required for every sim type.
STEADY_BASE_REQUIRED = (
    "oxidizer_mass_flow_rate",
    "chamber_pressure",
    "fuel_external_radius",
    "fuel_length",
    "liquid_oxidizer_type",
    "solid_fuel_type",
    "fuel_grain_density",
    "regression_rate_scaling_coefficient",
    "regression_rate_exponent",
)

# Additionally required for fuel_mass_convergence and parametric_study (kinematics).
STEADY_KINEMATICS_REQUIRED = (
    "target_apogee",
    "launch_site_altitude",
    "dry_mass",
    "rocket_external_radius",
    "drag_coefficient",
    "launch_angle",
)


def validate_steady_config(config: dict) -> list[str]:
    """
    Return a list of human-readable validation errors.  Empty list = valid.

    Parametric-study note: any variable listed in
    simulation_settings.parametric_study_settings is *provided by the sweep*
    and does not need a static value in rocket_inputs.  We treat those
    keys as satisfied for required-field checks.
    """
    errors: list[str] = []

    sim = config.get("simulation_settings", {}) or {}
    ri  = config.get("rocket_inputs", {}) or {}

    sim_type = (sim.get("simulation_type") or "").lower()
    if sim_type not in ("hotfire", "fuel_mass_convergence", "parametric_study"):
        errors.append(f"simulation_type must be one of: "
                      f"hotfire, fuel_mass_convergence, parametric_study  "
                      f"(got {sim_type!r})")

    # Which rocket_inputs keys are being provided by the parametric sweep?
    parametrized: set[str] = set()
    if sim_type == "parametric_study":
        ps = sim.get("parametric_study_settings") or {}
        if isinstance(ps, dict):
            parametrized = set(ps.keys())

    # base inputs
    for key in STEADY_BASE_REQUIRED:
        if key in parametrized:
            continue
        if ri.get(key) in (None, ""):
            errors.append(f"missing required: {key}")

    # kinematics inputs — for everything except plain hotfire
    if sim_type in ("fuel_mass_convergence", "parametric_study"):
        for key in STEADY_KINEMATICS_REQUIRED:
            if key in parametrized:
                continue
            if ri.get(key) in (None, ""):
                errors.append(f"missing required (kinematics): {key}")

    # hotfire needs either initial_internal_fuel_radius OR fuel_mass
    if sim_type == "hotfire":
        if not (ri.get("initial_internal_fuel_radius") or ri.get("fuel_mass")):
            errors.append("hotfire requires one of: "
                          "initial_internal_fuel_radius, fuel_mass")

    # parametric study needs at least one parametric variable
    if sim_type == "parametric_study":
        ps = sim.get("parametric_study_settings") or {}
        if not isinstance(ps, dict) or not ps:
            errors.append("parametric_study requires at least one variable in "
                          "simulation_settings.parametric_study_settings")
        else:
            for var_name, spec in ps.items():
                if not isinstance(spec, dict):
                    errors.append(f"parametric '{var_name}' must be an object")
                    continue
                for f in ("low_end", "high_end", "step_size"):
                    if spec.get(f) in (None, ""):
                        errors.append(f"parametric '{var_name}' is missing '{f}'")

    return errors


# =============================================================================
# Steady — run
# =============================================================================

def run_steady(config: dict, config_file_path: Path | None = None) -> tuple[Path, dict]:
    """
    Run a steady simulation from an in-memory config dict.

    Parameters
    ----------
    config : dict
        The in-memory configuration.
    config_file_path : Path or None
        If provided, the simulator is called with this existing file
        instead of writing a temp file.  Used when the page knows the
        current form contents exactly match a saved preset, so we don't
        clutter the configs directory.

    Returns
    -------
    (results_file_path, results_dict)
    """
    presets = steady_presets_dir()
    presets.mkdir(parents=True, exist_ok=True)

    # `cleanup_after` is only true when we created the file ourselves as a
    # throwaway (auto-save unchecked on the page side).  In that case we
    # write to the OS's temp dir so nothing lingers in user_data/.
    cleanup_after = False
    if config_file_path is None:
        fd, tmp_str = tempfile.mkstemp(suffix=".jsonc", prefix="mrt_steady_")
        os.close(fd)
        temp_path = Path(tmp_str)
        save_jsonc(temp_path, config)
        cleanup_after = True
    else:
        temp_path = Path(config_file_path)
    temp_name = temp_path.name

    # 2. snapshot existing results so we can pick out the new one
    results = steady_results_dir()
    before = set(results.glob("*.json")) if results.exists() else set()

    try:
        # 3. invoke the simulator (use the temp file's actual parent — it
        # may be OS temp dir when the page didn't hand us a preset path).
        from src.backend.steady.steady_main import run_steady as _run_steady
        _run_steady(temp_name, rocket_inputs_filepath=temp_path.parent)

        # 4. find the newly-produced result JSON
        if not results.exists():
            raise RuntimeError(
                f"Simulation ran but no results directory exists at {results}"
            )
        after = set(results.glob("*.json"))
        new_files = sorted(after - before, key=lambda p: p.stat().st_mtime, reverse=True)
        if not new_files:
            candidates = sorted(after, key=lambda p: p.stat().st_mtime, reverse=True)
            if not candidates:
                raise RuntimeError("Simulation ran but produced no result file")
            result_path = candidates[0]
        else:
            result_path = new_files[0]

        # 5. load & return
        with open(result_path, "r", encoding="utf-8") as f:
            results_dict = json.load(f)
        return result_path, results_dict

    finally:
        # Only delete files we created in OS temp; never touch a user preset.
        if cleanup_after:
            try:
                temp_path.unlink()
            except Exception:
                pass


# =============================================================================
# Unsteady — presets, validation, run
# =============================================================================

def list_unsteady_presets() -> list[Path]:
    """All saved unsteady-input presets."""
    d = unsteady_presets_dir()
    if not d.exists():
        return []
    return sorted(d.glob("*.jsonc")) + sorted(d.glob("*.json"))


# Minimum-required CVs for any unsteady run.
_UNSTEADY_REQUIRED_CVS = (
    "CV1_tank", "CV2_valve", "CV3_injector",
    "CV4_chamber", "CV5_nozzle", "CV6_trajectory",
)


def validate_unsteady_config(config: dict) -> list[str]:
    """
    Return a list of human-readable validation errors.  Empty list = valid.

    Only checks the broad shape — that every CV block exists and the
    required-key set for each CV has values.  The simulator itself does
    the deeper unit / range validation when it runs.
    """
    errors: list[str] = []
    ri = (config.get("rocket_inputs") or {})
    cvs = (ri.get("CV_inputs") or {})

    for cv in _UNSTEADY_REQUIRED_CVS:
        block = cvs.get(cv)
        if not isinstance(block, dict):
            errors.append(f"missing CV block: {cv}")
            continue
        if not block.get("model"):
            errors.append(f"{cv}: missing model")

    # Tank: must have ONE of ullage_fraction / internal_length_m
    tank = cvs.get("CV1_tank") or {}
    if (not tank.get("tank_ullage_fraction")
            and not tank.get("tank_internal_length_m")):
        errors.append("CV1_tank: provide one of "
                      "tank_ullage_fraction or tank_internal_length_m")

    # Chamber: must have ONE of fuel_mass_kg / fuel_internal_radius_m
    chamber = cvs.get("CV4_chamber") or {}
    if (not chamber.get("chamber_fuel_mass_kg")
            and not chamber.get("chamber_fuel_internal_radius_m")):
        errors.append("CV4_chamber: provide one of "
                      "chamber_fuel_mass_kg or chamber_fuel_internal_radius_m")

    return errors


def run_unsteady(config: dict, config_file_path: Path | None = None) -> tuple[Path, dict]:
    """
    Run an unsteady simulation from an in-memory config dict.

    See run_steady for the full contract.  If `config_file_path` is given,
    that file is reused instead of writing a temp one — UI pages set this
    when the form contents still match an already-saved preset.
    """
    presets = unsteady_presets_dir()
    presets.mkdir(parents=True, exist_ok=True)

    cleanup_after = False
    if config_file_path is None:
        fd, tmp_str = tempfile.mkstemp(suffix=".jsonc", prefix="mrt_unsteady_")
        os.close(fd)
        temp_path = Path(tmp_str)
        save_jsonc(temp_path, config)
        cleanup_after = True
    else:
        temp_path = Path(config_file_path)
    temp_name = temp_path.name

    results = unsteady_results_dir()
    before = set(results.glob("*.json")) if results.exists() else set()

    try:
        from src.backend.unsteady.engine.phase_runner import run_unsteady as _run_unsteady
        _run_unsteady(temp_name, rocket_inputs_filepath=temp_path.parent)

        if not results.exists():
            raise RuntimeError(
                f"Simulation ran but no results directory exists at {results}"
            )
        after = set(results.glob("*.json"))
        new_files = sorted(after - before, key=lambda p: p.stat().st_mtime, reverse=True)
        if new_files:
            result_path = new_files[0]
        else:
            candidates = sorted(after, key=lambda p: p.stat().st_mtime, reverse=True)
            if not candidates:
                raise RuntimeError("Simulation ran but produced no result file")
            result_path = candidates[0]

        with open(result_path, "r", encoding="utf-8") as f:
            results_dict = json.load(f)
        return result_path, results_dict

    finally:
        if cleanup_after:
            try:
                temp_path.unlink()
            except Exception:
                pass
