"""
The one module allowed to touch the backend.

Everything else in the UI goes through here.  That keeps the seam narrow: if
the backend moves, only this file changes, and the pages above it can be
restructured freely as long as this interface holds.

WHAT IT PROVIDES
----------------
  path helpers        where presets, results and user data live
  load_jsonc/save     reading and writing config files
  validators          human-readable error lists for a config dict
  preflight_*         input-range warnings, before committing to a run
  run_steady/unsteady the actual invocation
  run listing         enumerating and naming saved results

WHY IT'S SMALLER THAN IT USED TO BE
-----------------------------------
The previous version carried a `_reconcile_backend_output` step that ran a
simulation, scanned two directories, and moved whatever appeared from the
bundled tree into the writable one.  That existed because the backend picked
its own output location by walking up from its __file__, which in a frozen
build landed inside the exe's resources rather than in %APPDATA%.

Both run_steady and run_unsteady now take an explicit `output_dir_filepath` and
return the path they wrote.  So we hand them the writable directory and use
what they give back.  The whole reconciliation dance is gone.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


# =============================================================================
# Roots
# =============================================================================
#
# Two of them, and the difference matters in a frozen build:
#
#   project_root()  WRITABLE.  Presets, results, settings.  Source mode: the
#                   git checkout.  Frozen: a per-user application-data folder,
#                   because the install directory may be read-only.
#
#   bundled_root()  READ-ONLY.  Default settings, example configs, images.
#                   Source mode: the same checkout.  Frozen: sys._MEIPASS,
#                   where PyInstaller unpacked the bundle.
#
# On first frozen launch the writable root is seeded from the bundled one, so
# "Load preset" and "Reset to defaults" find something.

def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _per_user_data_dir() -> Path:
    """Platform-appropriate writable per-user directory."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
        return Path(base) / "MRT-Steady-Unsteady"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MRT-Steady-Unsteady"
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(xdg) / "MRT-Steady-Unsteady"


def _source_layout_root() -> Path:
    """Root of the git checkout, found by walking up for user_data/."""
    here = Path(__file__).resolve()
    for candidate in [here.parent, *here.parents]:
        if (candidate / "user_data").exists():
            return candidate
    # src/ui/app/backend_bridge.py -> repo root
    return here.parents[3]


_seeded = False


# Bumped whenever the shipped example configs change shape. A writable root
# seeded under an older stamp gets its examples refreshed on next launch.
#
# This exists because the examples are TEMPLATES, not user documents. Seeding
# them only when absent meant an upgraded install kept the examples from
# whatever version first ran, so a config written against the old schema
# survived into a build that no longer understood it — which surfaced as
# "not an unsteady config, no rocket inputs block found" and
# "ValueError: Unknown unit: 'n'" in the exe, and never in source mode, where
# the checkout's own files are read directly.
SEED_STAMP = "1.5"
_STAMP_FILE = "user_data/.seeded"


def _seed_writable_root(root: Path) -> None:
    """Populate the writable root from the bundle, refreshing stale examples.

    Idempotent, and never fatal: a failure here costs the user their example
    presets, not the ability to run the app.
    """
    global _seeded
    if _seeded:
        return
    _seeded = True

    import shutil
    src_root = Path(getattr(sys, "_MEIPASS", str(root)))

    for sub in (
        "user_data",
        "user_data/simulation_configs/steady",
        "user_data/simulation_configs/unsteady",
        "user_data/simulation_results/steady",
        "user_data/simulation_results/unsteady",
    ):
        (root / sub).mkdir(parents=True, exist_ok=True)

    stamp_path = root / _STAMP_FILE
    try:
        stale = stamp_path.read_text(encoding="utf-8").strip() != SEED_STAMP
    except OSError:
        stale = True                            # never seeded, or unreadable

    seeds = [
        "user_data/default_ui_settings.json",
        "user_data/simulation_configs/steady/steady_example.jsonc",
        "user_data/simulation_configs/steady/steady_parametric_example.jsonc",
        "user_data/simulation_configs/unsteady/unsteady_example.jsonc",
    ]
    for rel in seeds:
        src, dst = src_root / rel, root / rel
        if not src.exists():
            continue
        if dst.exists() and not stale:
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                # Someone may have edited an example in place. Keep a copy
                # rather than silently discarding their work.
                shutil.copyfile(dst, dst.with_suffix(dst.suffix + ".bak"))
            shutil.copyfile(src, dst)
        except OSError:
            pass

    if stale:
        try:
            stamp_path.write_text(SEED_STAMP, encoding="utf-8")
        except OSError:
            pass


def project_root() -> Path:
    """The WRITABLE root.  Everything the user creates lives under here."""
    if _is_frozen():
        root = _per_user_data_dir()
        _seed_writable_root(root)
        return root
    return _source_layout_root()


def bundled_root() -> Path:
    """The READ-ONLY root holding bundled resources."""
    if _is_frozen():
        return Path(sys._MEIPASS)               # noqa: SLF001 - PyInstaller's API
    return _source_layout_root()


def steady_presets_dir() -> Path:
    return project_root() / "user_data" / "simulation_configs" / "steady"


def unsteady_presets_dir() -> Path:
    return project_root() / "user_data" / "simulation_configs" / "unsteady"


def steady_results_dir() -> Path:
    return project_root() / "user_data" / "simulation_results" / "steady"


def unsteady_results_dir() -> Path:
    return project_root() / "user_data" / "simulation_results" / "unsteady"


def assets_dir() -> Path:
    """Images and icons, which ship read-only inside the bundle."""
    return bundled_root() / "src" / "ui" / "assets"


# =============================================================================
# JSONC
# =============================================================================
#
# Configs are .jsonc: JSON plus // and /* */ comments, and occasionally a
# trailing comma. json5 handles all of it and is already a dependency; the
# regex fallback exists only so the UI still opens if json5 is missing.

def load_jsonc(path: Path) -> dict:
    """Read a commented JSON file."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        import json5
        return json5.loads(text)
    except ImportError:
        stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        stripped = re.sub(r"//.*?$", "", stripped, flags=re.MULTILINE)
        stripped = re.sub(r",(\s*[}\]])", r"\1", stripped)
        return json.loads(stripped)


def save_jsonc(path: Path, data: dict) -> None:
    """Write a config.

    Comments are not preserved — the UI regenerates the file from the form, so
    there is nothing to preserve them from.  Hand-written presets keep their
    comments right up until someone saves over them from the app.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4), encoding="utf-8")


def list_presets(kind: str) -> list[Path]:
    """Saved presets for "steady" or "unsteady", newest first."""
    directory = steady_presets_dir() if kind == "steady" else unsteady_presets_dir()
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.jsonc"),
                  key=lambda p: p.stat().st_mtime, reverse=True)


# =============================================================================
# Validation
# =============================================================================
#
# These answer "would the backend accept this?" without running anything, so
# the user gets a list of problems instead of one exception at a time.
#
# Values arrive as [value, unit] pairs. "Filled" means the pair exists and its
# value is neither None nor "". That distinction carries real weight now: an
# unused alternate field is written [null, "m"], so the KEY is always present
# and only the value tells you whether the user filled it in.

def _is_filled(value: Any) -> bool:
    """True if a config entry actually carries a value."""
    if value is None:
        return False
    if isinstance(value, (list, tuple)):
        return len(value) > 0 and value[0] is not None and value[0] != ""
    return value != ""


def check_alternate_fields(values: dict, pairs: list[tuple[str, str]]) -> list[str]:
    """Enforce exactly-one-of for each pair.  Returns error strings.

    Both-filled and neither-filled are both errors.  Zero counts as filled,
    which is deliberate: 0 is a meaningful ullage fraction.
    """
    errors: list[str] = []
    for a, b in pairs:
        filled = [k for k in (a, b) if _is_filled(values.get(k))]
        if len(filled) == 0:
            errors.append(f"fill exactly one of: {a}, {b}")
        elif len(filled) == 2:
            errors.append(f"fill only one of: {a}, {b} (both are filled)")
    return errors


def validate_steady_config(config: dict) -> list[str]:
    """Human-readable problems with a steady config.  Empty list means valid.

    Variables driven by a parametric sweep count as satisfied even though they
    have no static value, because the solver fills them in per point.
    """
    from src.ui.app import field_registry as registry

    errors: list[str] = []
    sim = config.get("simulation_settings") or {}
    inputs = config.get("rocket_inputs") or {}

    sim_type = (sim.get("simulation_type") or "").lower()
    if sim_type not in ("hotfire", "fuel_mass_convergence", "parametric_study"):
        errors.append(f"simulation_type must be hotfire, fuel_mass_convergence "
                      f"or parametric_study (got {sim_type!r})")

    sweep = sim.get("parametric_study_settings") or {}
    parametrized = set(sweep) if sim_type == "parametric_study" else set()

    schema = registry.steady_schema_keys()
    for key in schema.get("base_requirements", []):
        if key not in parametrized and not _is_filled(inputs.get(key)):
            errors.append(f"missing required: {registry.label(key)}")

    if sim_type in ("fuel_mass_convergence", "parametric_study"):
        for key in schema.get("kinematics_requirements", []):
            if key not in parametrized and not _is_filled(inputs.get(key)):
                errors.append(f"missing required: {registry.label(key)}")

    # Hotfire derives whichever alternate you leave out, but needs one of them.
    if sim_type == "hotfire":
        errors += check_alternate_fields(
            inputs, [("fuel_mass", "initial_internal_fuel_diameter")])

    if sim_type == "parametric_study":
        if not sweep:
            errors.append("a parametric study needs at least one swept variable")
        for name, spec in sweep.items():
            if not isinstance(spec, dict):
                errors.append(f"swept variable {name!r} must be an object")
                continue
            for bound in ("low_end", "high_end", "step_size"):
                if not _is_filled(spec.get(bound)):
                    errors.append(f"swept variable {name!r} is missing {bound}")

    return errors


# Alternate-field pairs the unsteady form has to enforce, per CV.
UNSTEADY_ALTERNATES: dict[str, list[tuple[str, str]]] = {
    "CV1_tank": [("tank_ullage_fraction", "tank_internal_length")],
    "CV4_chamber": [("chamber_fuel_mass", "chamber_fuel_internal_diameter")],
}


def validate_unsteady_config(config: dict) -> list[str]:
    """Human-readable problems with an unsteady config.  Empty list means valid.

    Which fields matter depends on the model each CV has selected, so this
    walks the backend schema rather than a list of its own.
    """
    from src.ui.app import field_registry as registry

    errors: list[str] = []
    block = config.get("config") or {}
    cv_inputs = block.get("rocket_inputs") or {}
    if not cv_inputs:
        return ["config is missing its rocket_inputs block"]

    schema = registry.unsteady_schema_keys()
    known_cvs = {cv for cv, _model in schema}

    for cv in sorted(known_cvs):
        cv_block = cv_inputs.get(cv)
        if not isinstance(cv_block, dict):
            errors.append(f"{cv} is missing")
            continue

        model = cv_block.get("model")
        if not model:
            errors.append(f"{cv} has no model selected")
            continue
        if (cv, model) not in schema:
            errors.append(f"{cv}: unknown model {model!r}")
            continue

        alternates = UNSTEADY_ALTERNATES.get(cv, [])
        in_a_pair = {k for pair in alternates for k in pair}

        for key in schema[(cv, model)]:
            if key in in_a_pair:
                continue                        # handled by the pair check
            if not _is_filled(cv_block.get(key)):
                errors.append(f"{cv}: missing {registry.label(key)}")

        for message in check_alternate_fields(cv_block, alternates):
            errors.append(f"{cv}: {message}")

    return errors


# =============================================================================
# Preflight
# =============================================================================

def preflight_steady(rocket_inputs: dict) -> dict:
    """Input-range warnings for a steady config, keyed by warning ID."""
    from src.backend.common.preflight import preflight_steady as _preflight
    return _preflight(rocket_inputs)


def preflight_unsteady(rocket_inputs: dict) -> dict:
    """Input-range warnings for an unsteady config, keyed by warning ID."""
    from src.backend.common.preflight import preflight_unsteady as _preflight
    return _preflight(rocket_inputs)


def worst_severity(warnings: dict) -> str | None:
    """The most serious severity in a warnings dict, or None if it's empty.

    Lets a caller decide how loudly to present the modal without knowing the
    severity ordering itself.
    """
    order = ("advisory", "warning", "critical")
    worst = None
    for entry in (warnings or {}).values():
        severity = (entry or {}).get("severity") if isinstance(entry, dict) else None
        if severity in order and (worst is None or order.index(severity) > order.index(worst)):
            worst = severity
    return worst


# =============================================================================
# Running
# =============================================================================
#
# Both simulators read their config from a file rather than a dict, so a config
# built in the form has to be written somewhere first. When the user has saved
# a preset we run that file directly; otherwise we drop a temp copy.

def _config_to_file(config: dict, kind: str,
                    config_file_path: Path | None) -> tuple[str, Path, bool]:
    """Resolve a config into (filename, directory, is_temporary)."""
    if config_file_path is not None:
        path = Path(config_file_path)
        return path.name, path.parent, False
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"mrt_{kind}_"))
    name = f"{kind}_run.jsonc"
    save_jsonc(tmp_dir / name, config)
    return name, tmp_dir, True


def run_steady(config: dict, config_file_path: Path | None = None) -> Path:
    """Run a steady simulation.  Returns the path of the results JSON.

    Blocking and slow enough to matter, so callers run it on a worker thread.
    """
    from src.backend.steady.steady_main import run_steady as _run

    name, directory, is_temp = _config_to_file(config, "steady", config_file_path)
    out_dir = steady_results_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        return Path(_run(name, directory, out_dir))
    finally:
        if is_temp:
            import shutil
            shutil.rmtree(directory, ignore_errors=True)


def run_unsteady(config: dict, config_file_path: Path | None = None) -> Path:
    """Run an unsteady simulation.  Returns the path of the results JSON.

    Much slower than steady — tens of seconds to minutes — so this always
    belongs on a worker thread.
    """
    from src.backend.unsteady.engine.phase_runner import run_unsteady as _run

    name, directory, is_temp = _config_to_file(config, "unsteady", config_file_path)
    out_dir = unsteady_results_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        return Path(_run(name, directory, out_dir))
    finally:
        if is_temp:
            import shutil
            shutil.rmtree(directory, ignore_errors=True)


# =============================================================================
# Saved runs
# =============================================================================
#
# The two simulators write different shapes: steady drops <name>.json straight
# into its results folder, unsteady creates <name>/ holding sim_data.json plus
# any graphs. The helpers below paper over that so the results browser can list
# both without caring.

# "sim_results.json" is what the engine wrote before the rename; accepted so
# older runs still show up.
_RUN_JSON_NAMES = ("sim_data.json", "sim_results.json")


def _run_json_in_dir(directory: Path) -> Path | None:
    for name in _RUN_JSON_NAMES:
        candidate = directory / name
        if candidate.exists():
            return candidate
    return None


def list_runs(kind: str) -> list[Path]:
    """Saved runs for "steady" or "unsteady", newest first.

    Entries are whatever represents the run: a .json file for steady, a
    directory for unsteady.  Pass them to run_json_path() and run_display_name()
    rather than interpreting them directly.
    """
    directory = steady_results_dir() if kind == "steady" else unsteady_results_dir()
    if not directory.is_dir():
        return []
    runs = [entry for entry in directory.iterdir()
            if (entry.is_dir() and _run_json_in_dir(entry) is not None)
            or (entry.is_file() and entry.suffix == ".json")]
    return sorted(runs, key=lambda p: p.stat().st_mtime, reverse=True)


def run_json_path(run: Path) -> Path | None:
    """The results JSON for a run, whichever layout it uses."""
    run = Path(run)
    if run.is_dir():
        return _run_json_in_dir(run)
    return run if run.exists() else None


def run_display_name(run: Path) -> str:
    """What to call a run in a list."""
    return Path(run).stem if Path(run).is_file() else Path(run).name


def run_timestamp(run: Path) -> datetime:
    """When a run was written, for sorting and for display."""
    return datetime.fromtimestamp(Path(run).stat().st_mtime)


def load_run(run: Path) -> dict:
    """Parse a saved run's results JSON."""
    path = run_json_path(run)
    if path is None:
        raise FileNotFoundError(f"No results JSON inside {run}")
    return json.loads(path.read_text(encoding="utf-8"))
