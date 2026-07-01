"""
Display layer — pretty names for dropdowns + UI-side unit conversions.

Design rationale
----------------
The simulator backend speaks snake_case wire values for both
simulation_type and the parametric variable names, and stores every
numerical value in SI. The UI surface needs prettier labels and lets
users type in non-SI units. This module is the single source of truth
for both mappings; the UI never invents display strings inline.

  - SIM_TYPE_DISPLAY / SIM_TYPE_VALUE        round-trip the simulation type
  - PARAM_VAR_DISPLAY / PARAM_VAR_VALUE      round-trip parametric variable names
  - UNIT_KINDS                               which units belong to which dimension
  - to_internal / from_internal              numeric conversion between user-unit and field-internal
  - field_kind                               look-up: field name -> dimension kind (or None)
"""

from __future__ import annotations

from typing import Optional


# =============================================================================
# Pretty-name maps
# =============================================================================

# Simulation type ---------------------------------------------------------------
SIM_TYPE_DISPLAY: dict[str, str] = {
    "hotfire":               "Hotfire",
    "fuel_mass_convergence": "Fuel mass convergence",
    "parametric_study":      "Parametric study",
}
SIM_TYPE_VALUE: dict[str, str] = {v: k for k, v in SIM_TYPE_DISPLAY.items()}


# Parametric variable names -----------------------------------------------------
PARAM_VAR_DISPLAY: dict[str, str] = {
    "oxidizer_mass_flow_rate":  "Oxidizer mass flow rate",
    "chamber_pressure":         "Chamber pressure",
    "fuel_length":              "Fuel length",
    "fuel_external_radius":     "Fuel external radius",
    "rocket_external_radius":   "Rocket external radius",
    "drag_coefficient":         "Drag coefficient",
    "dry_mass":                 "Dry mass",
}
PARAM_VAR_VALUE: dict[str, str] = {v: k for k, v in PARAM_VAR_DISPLAY.items()}


def prettify(value: str, mapping: dict[str, str]) -> str:
    """Look up `value` in `mapping`; fall back to `value` itself if missing."""
    return mapping.get(value, value)


def unprettify(display: str, mapping: dict[str, str]) -> str:
    """Reverse of prettify — `mapping` is the *display -> value* dict."""
    return mapping.get(display, display)


# =============================================================================
# Unit conversion
# =============================================================================
#
# Each "kind" represents a physical dimension. For every kind we declare:
#   - the INTERNAL unit (the unit the backend already speaks; we
#     convert to/from this when serializing/loading)
#   - the user-selectable OPTIONS (always includes the internal unit first)
#
# The TO_INTERNAL table gives the multiplicative factor that converts
# 1 user-unit -> 1 internal-unit, for every (option, internal) pair we
# might need.
#
# To add a new unit option: add to UNIT_KINDS[<kind>]["options"] and add
# the (option, internal) factor to TO_INTERNAL.

UNIT_KINDS: dict[str, dict] = {
    "length": {
        "internal": "m",
        "options":  ["m", "cm", "mm", "in", "ft", "km"],
    },
    "pressure": {
        "internal": "Pa",
        "options":  ["Pa", "kPa", "MPa", "psi", "bar"],
    },
    "mass": {
        "internal": "kg",
        "options":  ["kg", "g", "lbm"],
    },
    "mass_flow": {
        "internal": "kg/s",
        "options":  ["kg/s", "lbm/s"],
    },
    "density": {
        "internal": "kg/m^3",
        "options":  ["kg/m^3", "g/cm^3"],
    },
    "angle": {
        # The backend's launch_angle is in degrees, so degrees is the internal.
        "internal": "deg",
        "options":  ["deg", "rad"],
    },
    "volume": {
        "internal": "m^3",
        "options":  ["m^3", "L", "cm^3"],
    },
    "area": {
        "internal": "m^2",
        "options":  ["m^2", "cm^2", "mm^2", "in^2"],
    },
    "temperature": {
        # Kelvin is the backend unit; °C is just a label-shift (handled inline).
        "internal": "K",
        "options":  ["K", "°C"],
    },
    "time": {
        "internal": "s",
        "options":  ["s", "ms"],
    },
    "force": {
        "internal": "N",
        "options":  ["N", "lbf"],
    },
    "impulse": {
        "internal": "N*s",
        "options":  ["N*s", "lbf*s"],
    },
    "velocity": {
        "internal": "m/s",
        "options":  ["m/s", "ft/s", "mph"],
    },
}


# Multiplicative factor: (option_unit, internal_unit) -> factor
# Use: value_in_internal = value_in_option * TO_INTERNAL[(option, internal)]
TO_INTERNAL: dict[tuple[str, str], float] = {
    # length, internal=m
    ("m", "m"):    1.0,
    ("cm", "m"):   0.01,
    ("mm", "m"):   0.001,
    ("in", "m"):   0.0254,
    ("ft", "m"):   0.3048,
    ("km", "m"):   1000.0,

    # pressure, internal=Pa
    ("Pa", "Pa"):  1.0,
    ("kPa", "Pa"): 1000.0,
    ("MPa", "Pa"): 1_000_000.0,
    ("psi", "Pa"): 6894.757293168,
    ("bar", "Pa"): 100000.0,

    # mass, internal=kg
    ("kg", "kg"):  1.0,
    ("g", "kg"):   0.001,
    ("lbm", "kg"): 0.45359237,

    # mass flow, internal=kg/s
    ("kg/s",  "kg/s"): 1.0,
    ("lbm/s", "kg/s"): 0.45359237,

    # density, internal=kg/m^3
    ("kg/m^3", "kg/m^3"): 1.0,
    ("g/cm^3", "kg/m^3"): 1000.0,

    # angle, internal=deg
    ("deg", "deg"): 1.0,
    ("rad", "deg"): 57.29577951308232,

    # volume, internal=m^3
    ("m^3",  "m^3"): 1.0,
    ("L",    "m^3"): 0.001,
    ("cm^3", "m^3"): 1e-6,

    # area, internal=m^2
    ("m^2",  "m^2"): 1.0,
    ("cm^2", "m^2"): 1e-4,
    ("mm^2", "m^2"): 1e-6,
    ("in^2", "m^2"): 6.4516e-4,

    # temperature is an additive transformation rather than multiplicative —
    # we keep K=K (factor 1) and intercept °C in convert() below.
    ("K",  "K"): 1.0,
    ("°C", "K"): 1.0,    # placeholder; convert() handles the +273.15 shift

    # time, internal=s
    ("s",  "s"): 1.0,
    ("ms", "s"): 0.001,

    # force, internal=N
    ("N",   "N"): 1.0,
    ("lbf", "N"): 4.4482216152605,

    # impulse, internal=N*s
    ("N*s",   "N*s"): 1.0,
    ("lbf*s", "N*s"): 4.4482216152605,

    # velocity, internal=m/s
    ("m/s",  "m/s"): 1.0,
    ("ft/s", "m/s"): 0.3048,
    ("mph",  "m/s"): 0.44704,

    # extra area / volume / density options for the IMP unit-system
    ("ft^2",     "m^2"): 0.09290304,
    ("ft^3",     "m^3"): 0.028316846592,
    ("lbm/ft^3", "kg/m^3"): 16.0184634,
}


def to_internal(value: float, from_unit: str, internal: str) -> float:
    """Convert a numeric value FROM a user-facing unit TO the internal unit."""
    # Temperature gets the additive shift special-case.
    if internal == "K":
        if from_unit == "°C":
            return value + 273.15
        return value
    if from_unit == internal:
        return value
    return value * TO_INTERNAL[(from_unit, internal)]


def from_internal(value: float, internal: str, to_unit: str) -> float:
    """Convert FROM the internal unit TO a user-facing unit."""
    if internal == "K":
        if to_unit == "°C":
            return value - 273.15
        return value
    if to_unit == internal:
        return value
    return value / TO_INTERNAL[(to_unit, internal)]


def convert(value: float, from_unit: str, to_unit: str, kind: str) -> float:
    """Convert between any two units of the same kind."""
    internal = UNIT_KINDS[kind]["internal"]
    return from_internal(to_internal(value, from_unit, internal), internal, to_unit)


# =============================================================================
# Field metadata
# =============================================================================
#
# Maps a `rocket_inputs` key to the unit-kind it belongs to.
# Unknown keys / non-numeric fields return None and the UI shows no unit dropdown.

FIELD_KIND: dict[str, str] = {
    # ====================  STEADY FIELDS  ====================
    "oxidizer_mass_flow_rate":          "mass_flow",
    "chamber_pressure":                 "pressure",
    "fuel_external_radius":             "length",
    "fuel_length":                      "length",
    "initial_internal_fuel_radius":     "length",
    "fuel_grain_density":               "density",
    "target_apogee":                    "length",
    "launch_site_altitude":             "length",
    "dry_mass":                         "mass",
    "rocket_external_radius":           "length",
    "launch_angle":                     "angle",

    # ====================  UNSTEADY FIELDS  ====================
    # CV1 — tank
    "tank_internal_radius_m":               "length",
    "tank_internal_shell_length_m":         "length",
    "tank_internal_volume_m3":              "volume",
    "tank_temperature_K":                   "temperature",
    "tank_oxidizer_mass_kg":                "mass",
    "dip_tube_external_radius_m":           "length",
    "dip_tube_internal_radius_m":           "length",
    "dip_tube_length_m":                    "length",
    "tank_internal_length_m":               "length",
    # CV2 — valve
    "valve_time_constant_s":                "time",
    "sigmoid_half_time_s":                  "time",
    # CV3 — injector
    "injector_hole_area_m2":                "area",
    "feed_pressure_loss_Pa":                "pressure",
    # CV4 — chamber
    "chamber_fuel_length_m":                "length",
    "chamber_fuel_density_kgm3":            "density",
    "chamber_fuel_external_radius_m":       "length",
    "chamber_fuel_internal_radius_m":       "length",
    "chamber_fuel_mass_kg":                 "mass",
    "pre_chamber_volume_m3":                "volume",
    "post_chamber_volume_m3":               "volume",
    # CV5 — nozzle
    "nozzle_throat_radius_m":               "length",
    "nozzle_exit_radius_m":                 "length",
    # CV6 — trajectory
    "rocket_dry_mass_kg":                   "mass",
    "rocket_frontal_area_m2":               "area",
    "rocket_launch_angle_deg":              "angle",
    "drogue_parachute_frontal_area_m2":     "area",
    "main_parachute_deployment_altitude_agl_m": "length",
    "main_parachute_frontal_area_m2":       "area",
    "launch_site_altitude_asl_m":           "length",
    # Fields without units (dimensionless or text) are deliberately omitted.
}


def field_kind(field_name: str) -> Optional[str]:
    """Return the unit-kind for a field, or None if the field has no units."""
    return FIELD_KIND.get(field_name)
