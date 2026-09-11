"""
Input-range sanity check, runnable before a simulation is launched.

The engine's own 'warn_initialization_limits' only fires once the config has already been loaded and unpacked, which is too late to be useful: by then the user has committed to the run and the next thing they see is either a long wait or a traceback.  This module exposes the same checks as a pure function the UI can call the moment Run is clicked, so a suspect grain geometry or an impossible ullage fraction produces a modal instead of a wasted minute.

Both entry points here:
  - deep-copy their input, so nothing they touch mutates the caller's dict,
  - do the same [value, unit] to SI and diameter-to-radius conversion the real loaders do, because the checks are written against physics-side values,
  - return a dict of warnings keyed by ID, empty when the inputs look clean.
  """

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.common.variable_conversions import pair_to_SI, regression_pair_to_SI

# convert one config block into the flat SI + radius form the checks want
def _to_physics_values(block: dict) -> dict:
    out: dict[str, Any] = {}
    # a's units depend on the regression exponent n, so it needs its sibling before it can be read
    exponent = None
    for key in block:
        if key.endswith("regression_rate_exponent"):
            exponent = pair_to_SI(block[key])
            break
    for key, value in block.items():
        if key == "model":
            continue
        if "regression_rate_scaling" in key:
            try:
                out[key] = regression_pair_to_SI(value, exponent)
            except (ValueError, KeyError):
                pass
            continue
        try:
            converted = pair_to_SI(value)
        except (ValueError, KeyError):
            # an unparseable pair or unknown unit is a config problem the validator will report properly; don't let it break preflight.
            continue
        if isinstance(converted, (int, float)) and "diameter" in key:
            before, after = key.split("diameter")
            out[f"{before}radius{after}"] = converted / 2.0
        else:
            out[key] = converted
    return out


def preflight_unsteady(rocket_inputs: dict) -> dict:
    from src.backend.unsteady.engine.warnings import warn_initialization_limits

    cv_inputs = deepcopy(rocket_inputs or {})

    flat: dict[str, Any] = {}
    for block in cv_inputs.values():
        if isinstance(block, dict):
            flat.update(_to_physics_values(block))

    warnings: dict = {}
    _check_tank_fill(flat, warnings)
    try:
        warn_initialization_limits(flat, warnings)
    except KeyError as exc:
        # a required field is missing, so the run would crash on it anyway
        warnings["preflight_missing_field"] = {
            "severity": "critical",
            "message": f"Preflight could not complete: required input {exc} is missing. The simulation would fail on this input, so fix it before running.",
            "missing_field": str(exc).strip("'\""),
        }
    except Exception as exc:                    # noqa: BLE001
        # Anything else is a bug in the checks rather than in the user's input.
        # Report it, but don't hard-block: the run itself may well be fine.
        warnings["preflight_error"] = {
            "severity": "caution",
            "message": f"Input-range preflight crashed with {type(exc).__name__}: {exc}. The simulation may still run, but its inputs were not fully checked.",
        }
    return warnings


def preflight_steady(rocket_inputs: dict) -> dict:
    ri = _to_physics_values(deepcopy(rocket_inputs or {}))
    warnings: dict = {}

    # a port wider than the grain itself, or a fuel mass that exceeds a solid billet, both mean the geometry is impossible
    outer = ri.get("fuel_external_radius")
    port = ri.get("initial_internal_fuel_radius")
    if isinstance(outer, (int, float)) and isinstance(port, (int, float)):
        if port >= outer:
            warnings["steady_port_exceeds_grain"] = {
                "severity": "critical",
                "message": f"Initial internal fuel diameter ({port * 2:.4g} m) is at least as wide as the grain itself ({outer * 2:.4g} m), so there is no fuel to burn.",
            }
        elif port > 0.9 * outer:
            warnings["steady_thin_web"] = {
                "severity": "caution",
                "message": f"Only {(outer - port) * 1000:.1f} mm of fuel web remains at ignition. The grain will burn through almost immediately.",
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
                "message": f"Fuel mass ({mass:.3g} kg) exceeds a completely solid grain of these dimensions ({solid_mass:.3g} kg).",
            }

    return warnings

# catch a tank that cannot physically hold the requested oxidizer
def _check_tank_fill(flat: dict, warnings: dict) -> None:
    import math

    R_T = flat.get("tank_internal_radius")
    L_T = flat.get("tank_internal_length")
    m_ox = flat.get("tank_oxidizer_mass")
    T_T = flat.get("tank_temperature")
    if not all(isinstance(v, (int, float)) for v in (R_T, L_T, m_ox, T_T)):
        return # ullage branch, or an incomplete form; nothing to check yet
    if R_T <= 0 or L_T <= 0 or m_ox <= 0:
        return # the ordinary validators own nonsense geometry

    try:
        from src.backend.unsteady.physics.N2O_properties import N2O_properties as N2O
        v_l = N2O.get_N2O_property("v_l", T_T)
        v_v = N2O.get_N2O_property("v_v", T_T)
        W_o = 0.044013 # kg/mol, N2O
    except Exception:
        return # don't block runs in the preflight checker. crashes will be bug reports. 

    n_tot = m_ox / W_o
    V_tank = math.pi * R_T ** 2 * L_T
    V_liquid_only = n_tot * v_l
    V_vapour_only = n_tot * v_v

    if V_liquid_only >= V_tank:
        warnings["tank_overfilled"] = {
            "severity": "critical",
            "message": f"Tank cannot hold this much oxidizer. {m_ox:.3f} kg of saturated liquid at {T_T:.1f} K occupies {V_liquid_only*1e3:.2f} L, but the tank is only {V_tank*1e3:.2f} L ({V_liquid_only/V_tank*100:.0f}% full before any ullage). There is no saturated state to start from, so the run will fail. Reduce the oxidizer mass, lengthen the tank, or widen it.",
            "tank_volume_L": V_tank * 1e3,
            "liquid_volume_L": V_liquid_only * 1e3,
        }
    elif V_vapour_only <= V_tank:
        warnings["tank_no_liquid_phase"] = {
            "severity": "critical",
            "message": f"Tank is too large for this much oxidizer to be saturated. {m_ox:.3f} kg as pure saturated vapour at {T_T:.1f} K occupies {V_vapour_only*1e3:.2f} L, less than the tank's {V_tank*1e3:.2f} L, so no liquid phase exists. Increase the oxidizer mass or shorten the tank.",
            "tank_volume_L": V_tank * 1e3,
            "vapour_volume_L": V_vapour_only * 1e3,
        }

