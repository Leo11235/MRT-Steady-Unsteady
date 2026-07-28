"""
The UI writes user-friendly config keys (diameters), but the physics code was originally written to consume radii and areas. 
This file does the diameter → radius/area mapping so the physics files never have to change.

Two directions:

  * 'normalize_*' — forward pass, called from the backend entry points right after parsing the JSONC. 
    Converts any diameter-flavoured key into the radius / area key the physics loop expects.

  * 'promote_to_diameter_*' — reverse pass, called by the UI when loading an OLD preset (one saved before the diameter switch).
    Adds a diameter key next to any legacy radius/area so the UI's diameter-only form can populate.

Both directions are idempotent — if the destination key already exists, the input is left alone. 
That means legacy presets keep working, new presets get diameters, and the round-trip 
(UI save → backend load → results write) doesn't double-convert anything.

The mapping tables here are the SINGLE SOURCE OF TRUTH. 
If a new diameter-based input is added later, add it in one place (either _STEADY_MAP or _UNSTEADY_MAP) and both directions light up.
"""

from __future__ import annotations

import math
from typing import Any

# each entry: diameter_key --> (physics_key, kind) 'kind' is:
#     "radius" —> physics_key = diameter / 2
#     "area"   —> physics_key = pi * (diameter / 2) ** 2

_STEADY_MAP: dict[str, tuple[str, str]] = {
    "rocket_external_diameter": ("rocket_external_radius", "radius"),
    "fuel_external_diameter": ("fuel_external_radius", "radius"),
    "initial_internal_fuel_diameter": ("initial_internal_fuel_radius", "radius"),
}

# for the unsteady side the config is nested: rocket_inputs.CV_inputs.CV*.
# key the outer map by CV name so the caller can pass the flat CV block directly (which is what config.py has just after parsing).
_UNSTEADY_MAP: dict[str, dict[str, tuple[str, str]]] = {
    "CV3_injector": {
        "injector_hole_diameter_m": ("injector_hole_area_m2", "area"),
    },
    "CV4_chamber": {
        "chamber_fuel_external_diameter_m": ("chamber_fuel_external_radius_m", "radius"),
        "chamber_fuel_internal_diameter_m": ("chamber_fuel_internal_radius_m", "radius"),
    },
    "CV5_nozzle": {
        "nozzle_throat_diameter_m": ("nozzle_throat_radius_m", "radius"),
        "nozzle_exit_diameter_m": ("nozzle_exit_radius_m",   "radius"),
    },
    "CV6_trajectory": {
        "rocket_outer_diameter_m": ("rocket_frontal_area_m2",           "area"),
        "drogue_parachute_diameter_m": ("drogue_parachute_frontal_area_m2", "area"),
        "main_parachute_diameter_m": ("main_parachute_frontal_area_m2",   "area"),
    },
}

# KERNEL CONVERSIONS
def _to_radius(d: float) -> float:
    return d / 2.0
def _to_area(d: float) -> float:
    return math.pi * (d / 2.0) ** 2
def _from_radius(r: float) -> float:
    return r * 2.0
def _from_area(a: float) -> float:
    if a is None or a <= 0: # guard against tiny negative values from floating-point noise
        return 0.0
    return 2.0 * math.sqrt(a / math.pi)
def _numeric(value: Any) -> bool:
    """
    Only float/int (not None, not booleans, not empty strings) are valid inputs for the transform
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# DIAMETER --> RADIUS
def normalize_steady_inputs(rocket_inputs: dict) -> dict:
    """
    Given the flat steady 'rocket_inputs' dict, add every physics-side radius/area key derived from a diameter key that lives in the dict.
    Mutates in place; returns the same dict.
    """
    # if the physics key already exists, no conversion
    if not isinstance(rocket_inputs, dict):
        return rocket_inputs
    for diam_key, (target_key, kind) in _STEADY_MAP.items():
        if target_key in rocket_inputs:
            continue   # physics key already present, respect it
        val = rocket_inputs.get(diam_key)
        if not _numeric(val):
            continue
        fn = _to_radius if kind == "radius" else _to_area
        rocket_inputs[target_key] = fn(float(val))
    return rocket_inputs


def normalize_unsteady_inputs(cv_inputs: dict) -> dict:
    """
    Given the nested unsteady 'CV_inputs' dict (keyed by CV name), add physics-side radius/area keys derived from diameter keys inside
    each CV block.  Mutates in place; returns the same dict.

    Only CVs that appear in _UNSTEADY_MAP get touched; anything else passes through untouched.
    """
    if not isinstance(cv_inputs, dict):
        return cv_inputs
    for cv_name, mapping in _UNSTEADY_MAP.items():
        block = cv_inputs.get(cv_name)
        if not isinstance(block, dict):
            continue
        for diam_key, (target_key, kind) in mapping.items():
            if target_key in block:
                continue
            val = block.get(diam_key)
            if not _numeric(val):
                continue
            fn = _to_radius if kind == "radius" else _to_area
            block[target_key] = fn(float(val))
    return cv_inputs


# reverse pass: radius/area --> diameter  (called by the UI when loading legacy presets that predate the diameter switch)

def promote_to_diameter_steady(rocket_inputs: dict) -> dict:
    """
    Inverse of 'normalize_steady_inputs'.  
    If a legacy preset only has radius / area keys, add the corresponding diameter key so the diameter-based UI form can populate. 
    If the diameter key is already present, leave the dict alone.
    """
    if not isinstance(rocket_inputs, dict):
        return rocket_inputs
    for diam_key, (target_key, kind) in _STEADY_MAP.items():
        if diam_key in rocket_inputs:
            continue
        val = rocket_inputs.get(target_key)
        if not _numeric(val):
            continue
        fn = _from_radius if kind == "radius" else _from_area
        rocket_inputs[diam_key] = fn(float(val))
    return rocket_inputs


def promote_to_diameter_unsteady(cv_inputs: dict) -> dict:
    """
    Inverse of 'normalize_unsteady_inputs'.
    If a legacy preset only has radius / area keys, add the corresponding diameter key so the diameter-based UI form can populate. 
    If the diameter key is already present, leave the dict alone.
    """
    if not isinstance(cv_inputs, dict):
        return cv_inputs
    for cv_name, mapping in _UNSTEADY_MAP.items():
        block = cv_inputs.get(cv_name)
        if not isinstance(block, dict):
            continue
        for diam_key, (target_key, kind) in mapping.items():
            if diam_key in block:
                continue
            val = block.get(target_key)
            if not _numeric(val):
                continue
            fn = _from_radius if kind == "radius" else _from_area
            block[diam_key] = fn(float(val))
    return cv_inputs
