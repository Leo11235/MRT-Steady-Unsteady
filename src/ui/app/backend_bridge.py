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
#
# Two roots exist depending on how the app is running:
#
#   - project_root() returns the WRITABLE root — where the app saves
#     presets, run results, and per-user UI settings.
#       * Source layout:   the git root (contains user_data/).
#       * PyInstaller:     %APPDATA%\MRT-Steady-Unsteady\   (Windows)
#                          ~/Library/Application Support/MRT-Steady-Unsteady/
#                          $XDG_DATA_HOME/MRT-Steady-Unsteady/ (Linux)
#
#   - bundled_root() returns the READ-ONLY root — where PyInstaller
#     unpacked the bundled resources (default settings, template
#     .jsonc files, image assets).  In source mode this is the same
#     as project_root().  In frozen mode this is sys._MEIPASS.
#
# On first launch of a frozen bundle, we seed the writable root with
# the templates + default settings from the bundled root so that
# 'Load preset' and 'Reset to defaults' find something meaningful.

def _is_frozen() -> bool:
    import sys
    return bool(getattr(sys, "frozen", False))


def _per_user_data_dir() -> Path:
    """Platform-appropriate writable per-user data dir."""
    import sys
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
        return Path(base) / "MRT-Steady-Unsteady"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MRT-Steady-Unsteady"
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(xdg) / "MRT-Steady-Unsteady"


def _source_layout_root() -> Path:
    """Root of the git checkout — used only in source mode."""
    here = Path(__file__).resolve()
    for candidate in [here.parent, *here.parents]:
        if (candidate / "user_data").exists():
            return candidate
    return here.parents[3]


_seeded_frozen_root = False


def _seed_frozen_writable_root(root: Path) -> None:
    """Idempotent: on first frozen launch, seed the per-user data dir
    with the templates + default settings we bundled inside the exe."""
    global _seeded_frozen_root
    if _seeded_frozen_root:
        return
    _seeded_frozen_root = True
    import sys
    import shutil
    src_root = Path(getattr(sys, "_MEIPASS", str(root)))
    # Directories the app writes into.
    for sub in (
        "user_data",
        "user_data/simulation_configs/steady",
        "user_data/simulation_configs/unsteady",
        "user_data/simulation_results/steady",
        "user_data/simulation_results/unsteady",
    ):
        (root / sub).mkdir(parents=True, exist_ok=True)
    # Files to seed if the user doesn't already have them.
    # Left = source (bundled) relative path.
    # Right = destination relative path (same names — the source repo
    # already uses `*_example.jsonc` as canonical filenames).
    to_copy = [
        ("user_data/default_ui_settings.json",
         "user_data/default_ui_settings.json"),
        ("user_data/simulation_configs/steady/steady_example.jsonc",
         "user_data/simulation_configs/steady/steady_example.jsonc"),
        ("user_data/simulation_configs/steady/steady_parametric_example.jsonc",
         "user_data/simulation_configs/steady/steady_parametric_example.jsonc"),
        ("user_data/simulation_configs/unsteady/unsteady_example.jsonc",
         "user_data/simulation_configs/unsteady/unsteady_example.jsonc"),
    ]
    for src_rel, dst_rel in to_copy:
        src = src_root / src_rel
        dst = root / dst_rel
        if src.exists() and not dst.exists():
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
            except Exception:
                # Non-fatal — the app can still run without the seeds.
                pass


def project_root() -> Path:
    """WRITABLE root.  When frozen, returns the per-user data dir (and
    seeds it once).  In source mode, returns the git root."""
    if _is_frozen():
        root = _per_user_data_dir()
        _seed_frozen_writable_root(root)
        return root
    return _source_layout_root()


def bundled_root() -> Path:
    """READ-ONLY root of bundled resources.  Frozen: sys._MEIPASS.
    Source: same as project_root()."""
    if _is_frozen():
        import sys
        return Path(sys._MEIPASS)
    return _source_layout_root()


def steady_presets_dir() -> Path:
    return project_root() / "user_data" / "simulation_configs" / "steady"


def steady_results_dir() -> Path:
    return project_root() / "user_data" / "simulation_results" / "steady"


def unsteady_presets_dir() -> Path:
    return project_root() / "user_data" / "simulation_configs" / "unsteady"


def unsteady_results_dir() -> Path:
    return project_root() / "user_data" / "simulation_results" / "unsteady"


# ---------------------------------------------------------------------------
# Post-run result reconciliation
# ---------------------------------------------------------------------------
#
# The simulator backend does its own path resolution — it walks up from
# its own __file__ looking for a user_data/ dir.  In a frozen PyInstaller
# bundle, that walk finds `_internal/user_data/` (which we bundled so the
# backend's data files load), NOT the per-user %APPDATA% location the UI
# writes/reads from.
#
# The fix isn't to change the backend (we don't want to touch it): we
# scan BOTH locations after a run and move any new result file from the
# backend's dir into the writable %APPDATA% dir.  That way the UI's
# downstream code always sees results where it expects them.

def _reconcile_backend_output(kind: str, before_writable: set) -> Path | None:
    """After the backend runs, find where the result JSON actually
    landed (either in the writable user_data or in the bundled
    _internal/user_data) and return its canonical location under the
    writable dir.  Moves the file if the backend wrote it elsewhere.

    `kind` is "steady" or "unsteady".
    `before_writable` is the set of .json files present in the writable
    results dir before the run started.

    Returns None if no new file appeared anywhere.
    """
    import shutil

    writable_dir = (unsteady_results_dir() if kind == "unsteady"
                    else steady_results_dir())
    writable_dir.mkdir(parents=True, exist_ok=True)

    # 1. Any new file in the writable dir? — happy path, source mode.
    after_writable = set(writable_dir.glob("*.json"))
    new_writable = sorted(after_writable - before_writable,
                          key=lambda p: p.stat().st_mtime, reverse=True)
    if new_writable:
        return new_writable[0]

    # 2. Frozen mode: the backend wrote inside _internal/user_data/...
    #    Look for a fresh .json there and move it.
    if _is_frozen():
        bundled_dir = (bundled_root() / "user_data" / "simulation_results"
                       / kind)
        if bundled_dir.exists():
            candidates = sorted(bundled_dir.glob("*.json"),
                                key=lambda p: p.stat().st_mtime,
                                reverse=True)
            # Only files newer than ~120 s ago count as "just produced".
            # (Prevents grabbing stale test fixtures on repeat runs.)
            import time
            cutoff = time.time() - 120
            for p in candidates:
                if p.stat().st_mtime < cutoff:
                    break
                # Move it to the writable dir under the same name.
                dst = writable_dir / p.name
                try:
                    shutil.move(str(p), str(dst))
                except Exception:
                    # If move fails (permission, cross-device), fall
                    # back to copy — the source stays in _internal but
                    # at least the UI can read the writable copy.
                    try:
                        shutil.copyfile(str(p), str(dst))
                    except Exception:
                        continue
                # Also try to move any adjacent per-run output folder
                # (PDF/PNG bundle, sibling of the .json).
                sibling = p.with_suffix("")
                if sibling.is_dir():
                    try:
                        shutil.move(str(sibling), str(writable_dir / sibling.name))
                    except Exception:
                        pass
                return dst
    return None


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


def list_steady_results() -> list[Path]:
    """All saved steady result JSONs, newest first.  Filters out the
    `_ui_run_*.jsonc` temp configs; keeps only the actual result JSONs
    the simulator produces."""
    d = steady_results_dir()
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
# NOTE: the UI now writes diameter-flavoured keys (fuel_external_diameter,
# rocket_external_diameter, initial_internal_fuel_diameter) and the backend
# normalizer converts them to the radius keys the physics loop needs.
# We check the DIAMETER key here because that's what the UI form writes;
# the normalizer runs only inside the backend.
STEADY_BASE_REQUIRED = (
    "oxidizer_mass_flow_rate",
    "chamber_pressure",
    "fuel_external_diameter",
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
    "rocket_external_diameter",
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

    # 2. snapshot the WRITABLE results dir so we can spot the new file
    results = steady_results_dir()
    results.mkdir(parents=True, exist_ok=True)
    before = set(results.glob("*.json"))

    try:
        # 3. invoke the simulator.
        from src.backend.steady.steady_main import run_steady as _run_steady
        _run_steady(temp_name, rocket_inputs_filepath=temp_path.parent)

        # 4. Reconcile: in source mode the backend wrote to the writable
        # dir directly; in frozen mode it wrote to _internal/user_data/
        # and this call moves it into the writable dir.
        result_path = _reconcile_backend_output("steady", before)
        if result_path is None:
            raise RuntimeError("Simulation ran but produced no result file")

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
    results.mkdir(parents=True, exist_ok=True)
    before = set(results.glob("*.json"))

    try:
        from src.backend.unsteady.engine.phase_runner import run_unsteady as _run_unsteady
        _run_unsteady(temp_name, rocket_inputs_filepath=temp_path.parent)

        # See run_steady comment: in frozen mode the backend wrote into
        # _internal/user_data/... and we move it into the writable dir.
        result_path = _reconcile_backend_output("unsteady", before)
        if result_path is None:
            raise RuntimeError("Simulation ran but produced no result file")

        with open(result_path, "r", encoding="utf-8") as f:
            results_dict = json.load(f)
        return result_path, results_dict

    finally:
        if cleanup_after:
            try:
                temp_path.unlink()
            except Exception:
                pass
