"""
Input-range sanity check, runnable before a simulation is launched.

The engine's own `warn_initialization_limits` only fires once the config has
already been loaded and unpacked, which is too late to be useful: by then the
user has committed to the run and the next thing they see is either a long wait
or a traceback.  This module exposes the same checks as a pure function the UI
can call the moment Run is clicked, so a suspect grain geometry or an
impossible ullage fraction produces a modal instead of a wasted minute.

Both entry points here:
  - deep-copy their input, so nothing they touch mutates the caller's dict,
  - do the same [value, unit] to SI and diameter-to-radius conversion the real
    loaders do, because the checks are written against physics-side values,
  - return a dict of warnings keyed by ID, empty when the inputs look clean.

Callers show a modal when the result is non-empty.  A "critical" severity means
the run would almost certainly fail; anything else is advisory and the user
should be able to proceed anyway.

Later this should become the single implementation, with the loaders calling
it rather than duplicating the range logic.  Today it mirrors them.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.common.variable_conversions import pair_to_SI


def _to_physics_values(block: dict) -> dict:
    """Convert one config block into the flat SI + radius form the checks want.

    Same two transformations the backend loaders apply, in the same order:
    unpack [value, unit] pairs into SI floats, then rename any 'diameter' key
    to 'radius' and halve it.  Keys whose value isn't a pair (the 'model'
    marker, metadata strings) pass through untouched.
    """
    out: dict[str, Any] = {}
    for key, value in block.items():
        if key == "model":
            continue
        try:
            converted = pair_to_SI(value)
        except (ValueError, KeyError):
            # An unparseable pair or unknown unit is a config problem the
            # validator will report properly; don't let it break preflight.
            continue
        if isinstance(converted, (int, float)) and "diameter" in key:
            before, after = key.split("diameter")
            out[f"{before}radius{after}"] = converted / 2.0
        else:
            out[key] = converted
    return out


def preflight_unsteady(rocket_inputs: dict) -> dict:
    """Run the unsteady input-range checks.

    `rocket_inputs` is the nested per-CV block, i.e. what the UI puts in
    cfg["config"]["rocket_inputs"] — keyed by CV name, each holding a model and
    that model's fields.  The CVs get converted and flattened into one dict,
    which is the shape warnings.py expects.
    """
    # Imported here rather than at module scope: warnings.py drags in the
    # unsteady physics tree, and preflight shouldn't cost that on import.
    from src.backend.unsteady.engine.warnings import warn_initialization_limits

    cv_inputs = deepcopy(rocket_inputs or {})

    flat: dict[str, Any] = {}
    for block in cv_inputs.values():
        if isinstance(block, dict):
            flat.update(_to_physics_values(block))

    warnings: dict = {}
    try:
        warn_initialization_limits(flat, warnings)
    except KeyError as exc:
        # A required field is missing, so the run would crash on it anyway.
        # Surface it as critical: the user gets a modal naming the field
        # instead of a bare traceback several seconds into the run.
        warnings["preflight_missing_field"] = {
            "severity": "critical",
            "message": (
                f"Preflight could not complete: required input {exc} is "
                f"missing. The simulation would fail on this input, so fix it "
                f"before running."
            ),
            "missing_field": str(exc).strip("'\""),
        }
    except Exception as exc:                    # noqa: BLE001
        # Anything else is a bug in the checks rather than in the user's input.
        # Report it, but don't hard-block: the run itself may well be fine.
        warnings["preflight_error"] = {
            "severity": "warning",
            "message": (
                f"Input-range preflight crashed with {type(exc).__name__}: "
                f"{exc}. The simulation may still run, but its inputs were not "
                f"fully checked."
            ),
        }
    return warnings


def preflight_steady(rocket_inputs: dict) -> dict:
    """Run the steady input-range checks.

    `rocket_inputs` is the flat steady block from cfg["rocket_inputs"].

    There is no steady equivalent of warn_initialization_limits yet, so this
    currently only catches grain geometry that can't physically exist.  Kept
    symmetrical with preflight_unsteady so the UI calls both the same way; when
    a real steady warnings module lands, it slots in here.
    """
    ri = _to_physics_values(deepcopy(rocket_inputs or {}))
    warnings: dict = {}

    # A port wider than the grain itself, or a fuel mass that exceeds a solid
    # billet, both mean the geometry is impossible rather than merely unusual.
    outer = ri.get("fuel_external_radius")
    port = ri.get("initial_internal_fuel_radius")
    if isinstance(outer, (int, float)) and isinstance(port, (int, float)):
        if port >= outer:
            warnings["steady_port_exceeds_grain"] = {
                "severity": "critical",
                "message": (
                    f"Initial port diameter ({port * 2:.4g} m) is at least as "
                    f"wide as the grain itself ({outer * 2:.4g} m), so there is "
                    f"no fuel to burn."
                ),
            }
        elif port > 0.9 * outer:
            warnings["steady_thin_web"] = {
                "severity": "warning",
                "message": (
                    f"Only {(outer - port) * 1000:.1f} mm of fuel web remains "
                    f"at ignition. The grain will burn through almost "
                    f"immediately."
                ),
            }

    length = ri.get("fuel_length")
    density = ri.get("fuel_grain_density")
    mass = ri.get("fuel_mass")
    if all(isinstance(v, (int, float)) for v in (outer, length, density, mass)):
        import math
        solid_mass = math.pi * length * outer ** 2 * density
        if mass > solid_mass:
            warnings["steady_fuel_mass_impossible"] = {
                "severity": "critical",
                "message": (
                    f"Fuel mass ({mass:.3g} kg) exceeds a completely solid "
                    f"grain of these dimensions ({solid_mass:.3g} kg)."
                ),
            }

    return warnings
