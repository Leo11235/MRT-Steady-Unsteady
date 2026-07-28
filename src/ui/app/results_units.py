"""
Field-level metadata for the results pages.

Given a raw JSON key from a simulation-result dict, produce:

    (pretty_name, kind, si_unit)

where
    pretty_name   — a human-readable label ("Peak thrust")
    kind          — a UNIT_KINDS bucket from display.py, or None (unitless / text)
    si_unit       — the SI unit string ("N", "m", "kg", ...) for numeric fields,
                    or "." for dimensionless / non-numeric.

Two lookup layers:

  1. EXPLICIT_FIELDS — hand-maintained map for steady rocket_parameters and
     any other keys that don't self-declare their unit.

  2. UNIT_SUFFIXES — automatic parsing of unsteady-style suffixes
     (`_m`, `_kg`, `_Pa`, ...) so the map doesn't have to name every
     tank_internal_shell_length_m style key one by one.

Also here: unit_for_system() picks the right target unit given a system
identifier ('SI' / 'IMP' / 'MRT') and the field context.
"""

from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# Explicit field info for keys that don't self-declare their unit.
#
# Order/precedence: EXPLICIT_FIELDS is consulted first, before UNIT_SUFFIXES.
# ---------------------------------------------------------------------------

EXPLICIT_FIELDS: dict[str, tuple[str, Optional[str], str]] = {
    # ---- steady rocket_parameters ----
    "thrust":                              ("Thrust",                    "force",   "N"),
    "Isp":                                 ("Isp",                       "time",    "s"),
    "burntime":                            ("Burntime",                  "time",    "s"),
    "total_impulse":                       ("Total impulse",             "impulse", "N*s"),
    "average_oxidizer_to_fuel_ratio":      ("Average O/F ratio",         None,      "."),
    "fuel_mass":                           ("Fuel mass",                 "mass",    "kg"),
    "nozzle_throat_radius":                ("Nozzle throat radius",      "length",  "m"),
    "nozzle_exit_radius":                  ("Nozzle exit radius",        "length",  "m"),
    "wet_mass":                            ("Wet mass",                  "mass",    "kg"),
    "thrust_to_weight_ratio":              ("Thrust-to-weight ratio",    None,      "."),
    "reached_apogee":                      ("Apogee reached",            "length",  "m"),
    "augmented_regression_rate_exponent":  ("Augmented regression exponent", None, "."),
    "initial_internal_fuel_radius":        ("Initial internal fuel radius","length","m"),
    "initial_internal_fuel_diameter":      ("Initial internal fuel diameter","length","m"),
    "nozzle_throat_area":                  ("Nozzle throat area",        "area",    "m^2"),
    "nozzle_exit_area":                    ("Nozzle exit area",          "area",    "m^2"),
    "nozzle_gas_exit_mach_number":         ("Nozzle exit Mach",          None,      "."),
    "nozzle_gas_exit_pressure":            ("Nozzle exit pressure",      "pressure","Pa"),
    "nozzle_gas_exit_temperature":         ("Nozzle exit temperature",   "temperature","K"),
    "nozzle_gas_exit_velocity":            ("Nozzle exit velocity",      "velocity","m/s"),
    "average_fuel_mass_flow_rate":         ("Average fuel mass flow rate","mass_flow","kg/s"),
    "total_propellant_mass_flow_rate":     ("Total propellant flow rate","mass_flow","kg/s"),
    "chamber_temperature":                 ("Chamber temperature",       "temperature","K"),
    # No 'molar_mass' unit-kind, so embed the (kg/mol) unit inline in the
    # label — the KVRow appends units only when kind is a real kind.
    "chamber_gas_molar_mass":              ("Chamber gas molar mass (kg/mol)", None, "."),
    "chamber_gas_molar_weight":            ("Chamber gas molar mass (kg/mol)", None, "."),
    "heat_capacity_ratio":                 ("Heat capacity ratio",       None,      "."),

    # ---- steady rocket_inputs ----
    "oxidizer_mass_flow_rate":     ("Oxidizer mass flow rate",     "mass_flow", "kg/s"),
    "chamber_pressure":            ("Chamber pressure",            "pressure",  "Pa"),
    "fuel_external_radius":        ("Fuel external radius",        "length",    "m"),
    "fuel_external_diameter":      ("Fuel external diameter",      "length",    "m"),
    "fuel_length":                 ("Fuel length",                 "length",    "m"),
    "launch_site_altitude":        ("Launch site altitude",        "length",    "m"),
    "dry_mass":                    ("Dry mass",                    "mass",      "kg"),
    "rocket_external_radius":      ("Rocket external radius",      "length",    "m"),
    "rocket_external_diameter":    ("Rocket external diameter",    "length",    "m"),
    "drag_coefficient":            ("Drag coefficient",            None,        "."),
    "launch_angle":                ("Launch angle",                "angle",     "deg"),
    "fuel_grain_density":          ("Fuel grain density",          "density",   "kg/m^3"),
    "regression_rate_scaling_coefficient":
                                    ("Regression rate coefficient", None,       "."),
    "regression_rate_exponent":    ("Regression rate exponent",    None,        "."),
    "target_apogee":               ("Target apogee",               "length",    "m"),
    "rocket_name":                 ("Rocket name",                 None,        "."),
    "liquid_oxidizer_type":        ("Liquid oxidizer type",        None,        "."),
    "solid_fuel_type":             ("Solid fuel type",             None,        "."),

    # ---- simulation_settings / metadata (both steady and unsteady) ----
    "simulation_type":             ("Simulation type",             None,        "."),
    "output_units":                ("Output units",                None,        "."),
    "save_output_data":            ("Save output data",            None,        "."),
    "save_simulation_data":        ("Save simulation data",        None,        "."),
    "simulation_name":             ("Simulation name",             None,        "."),
    "warnings":                    ("Warnings enabled",            None,        "."),
    "save_to_pdf":                 ("Save to PDF",                 None,        "."),
    "save_to_png":                 ("Save to PNG",                 None,        "."),
    "show_graphs":                 ("Show graphs",                 None,        "."),
    "total_simulation_time":       ("Total simulation time",       "time",      "s"),
    "total_timesteps":             ("Total timesteps",             None,        "."),
    "number_of_timesteps":         ("Number of timesteps",         None,        "."),
    "tolerated_apogee_difference": ("Tolerated apogee difference", "length",    "m"),

    # ---- unsteady overall performance ----
    "average_OF_ratio":            ("Average O/F ratio",           None,        "."),
    "pad_thrust_to_weight":        ("Pad thrust-to-weight",        None,        "."),

    # ---- unsteady per-phase ----
    "peak_velocity_ms":            ("Peak velocity",               "velocity",  "m/s"),
    "terminal_velocity_ms":        ("Terminal velocity",           "velocity",  "m/s"),

    # ---- unsteady CV models ----
    "model":                       ("Model",                       None,        "."),
    "sigmoid_steepness":           ("Sigmoid steepness",           None,        "."),
    "injector_discharge_coefficient": ("Injector discharge coefficient", None, "."),
    "injector_number_of_holes":    ("Injector number of holes",    None,        "."),
    "tank_ullage_fraction":        ("Tank ullage fraction",        None,        "."),
    "chamber_regression_rate_scaling_constant":
                                    ("Chamber regression rate coefficient", None, "."),
    "chamber_regression_rate_exponent":
                                    ("Chamber regression rate exponent",    None, "."),
    "rocket_drag_coefficient":     ("Rocket drag coefficient",     None,        "."),
    "drogue_parachute_drag_coefficient":
                                    ("Drogue parachute drag coefficient", None, "."),
    "main_parachute_drag_coefficient":
                                    ("Main parachute drag coefficient",   None, "."),

    # ---- unsteady overall performance (apogee: length-typed) ----
    # The raw keys are apogee_m_asl / apogee_m_agl — the "_m" is embedded
    # between apogee and asl/agl, so the suffix table wouldn't fire on
    # its own.  Register them explicitly.
    "apogee_m_asl":                ("Apogee asl",                  "length",    "m"),
    "apogee_m_agl":                ("Apogee agl",                  "length",    "m"),
}


# ---------------------------------------------------------------------------
# Suffix-based automatic inference.  Longest suffix wins.
# ---------------------------------------------------------------------------

# List is ordered longest-first so we try `_agl_m` / `_kgm3` / `_kgs` / `_Ns`
# before the shorter `_m` / `_kg` / `_s`.
UNIT_SUFFIXES: list[tuple[str, tuple[str, str]]] = [
    ("_agl_m",  ("length",       "m")),
    ("_asl_m",  ("length",       "m")),
    ("_kgm3",   ("density",      "kg/m^3")),
    ("_kgs",    ("mass_flow",    "kg/s")),
    ("_lbms",   ("mass_flow",    "lbm/s")),
    ("_Ns",     ("impulse",      "N*s")),
    ("_kg",     ("mass",         "kg")),
    ("_ms",     ("velocity",     "m/s")),
    ("_m2",     ("area",         "m^2")),
    ("_m3",     ("volume",       "m^3")),
    ("_Pa",     ("pressure",     "Pa")),
    ("_deg",    ("angle",        "deg")),
    ("_rad",    ("angle",        "rad")),
    ("_N",      ("force",        "N")),
    ("_K",      ("temperature",  "K")),
    ("_m",      ("length",       "m")),
    ("_s",      ("time",         "s")),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _prettify_key(key: str) -> str:
    """my_snake_case_key → 'My snake case key'"""
    if not key:
        return key
    cleaned = key.replace("_", " ").strip()
    if not cleaned:
        return key
    return cleaned[0].upper() + cleaned[1:]


def get_field_info(key: str) -> tuple[str, Optional[str], str]:
    """
    Return (pretty_name, kind, si_unit).

      - kind is a UNIT_KINDS bucket from display.py, or None for
        dimensionless / non-numeric fields.
      - si_unit is the SI unit string (e.g. 'N', 'Pa', 'm'), or '.' for
        dimensionless / non-numeric.
    """
    # 1) explicit table wins
    if key in EXPLICIT_FIELDS:
        return EXPLICIT_FIELDS[key]

    # 2) suffix inference
    for suffix, (kind, si_unit) in UNIT_SUFFIXES:
        if key.endswith(suffix):
            trimmed = key[:-len(suffix)]
            if trimmed:
                return (_prettify_key(trimmed), kind, si_unit)

    # 3) fallback — text / unknown
    return (_prettify_key(key), None, ".")


# ---------------------------------------------------------------------------
# Unit-system tables
# ---------------------------------------------------------------------------

# Per-kind overrides for the two non-SI systems.  Anything not listed here
# stays in the SI unit for that kind.
_IMP_UNITS: dict[str, str] = {
    "length":       "ft",
    "pressure":     "psi",
    "mass":         "lbm",
    "mass_flow":    "lbm/s",
    "force":        "lbf",
    "impulse":      "lbf*s",
    "velocity":     "ft/s",
    "area":         "ft^2",
    "volume":       "ft^3",
    "density":      "lbm/ft^3",
    # keep angle=deg, time=s, temperature=K
}

_MRT_UNITS: dict[str, str] = {
    "length":       "in",       # small lengths are in inches ...
    "pressure":     "psi",
    "volume":       "ft^3",     # tank volumes read best in ft^3
    # areas default to in^2 for MRT (see _SMALL_AREA_KEYWORDS + fallback).
    # Everything else stays SI.
}

# Field-name keywords that should use FEET for length in the MRT system
# (rather than inches).  Case-insensitive substring match on the RAW key.
_MRT_LONG_LENGTH_KEYWORDS = (
    "altitude",
    "apogee",
    "downrange",
    "distance",
    "sy_r",   # rocket vertical position in the unsteady state vector
    "sx_r",   # rocket downrange position
)

# Field-name keywords that use IN² for area (rather than the system's
# default area unit).  Applies in both IMP and MRT so an injector hole
# doesn't get printed as 0.001 ft² / 0.001 m².
_SMALL_AREA_KEYWORDS = (
    "hole",     # injector_hole_area
    "throat",   # nozzle_throat_area
    "port",     # fuel port area (if it appears)
)


# SI unit per kind — matches display.UNIT_KINDS[kind]["internal"].
_SI_UNITS: dict[str, str] = {
    "length":       "m",
    "pressure":     "Pa",
    "mass":         "kg",
    "mass_flow":    "kg/s",
    "density":      "kg/m^3",
    "angle":        "deg",
    "volume":       "m^3",
    "area":         "m^2",
    "temperature":  "K",
    "time":         "s",
    "force":        "N",
    "impulse":      "N*s",
    "velocity":     "m/s",
}


def unit_for_system(field_name: str, kind: Optional[str], system: str) -> str:
    """
    Which unit should this field be displayed in for the given system?

    `field_name` is the raw JSON key — used to disambiguate MRT
    small-vs-long lengths (altitude/apogee → ft; everything else → in).
    """
    if kind is None:
        return "."
    system = (system or "SI").upper()
    if system == "SI":
        return _SI_UNITS.get(kind, kind)

    name = (field_name or "").lower()

    # Small-area override — injector holes / throats / ports look
    # unreadable in ft² or m².  Applies to both IMP and MRT.
    if kind == "area" and system in ("IMP", "MRT") and any(
            k in name for k in _SMALL_AREA_KEYWORDS):
        return "in^2"

    if system == "IMP":
        return _IMP_UNITS.get(kind, _SI_UNITS.get(kind, kind))
    if system == "MRT":
        # MRT length: inches by default, ft for "long"-flavored fields.
        if kind == "length":
            if any(k in name for k in _MRT_LONG_LENGTH_KEYWORDS):
                return "ft"
            return "in"
        # MRT area default (when no small-area keyword matched)
        if kind == "area":
            return "in^2"
        return _MRT_UNITS.get(kind, _SI_UNITS.get(kind, kind))
    return _SI_UNITS.get(kind, kind)


# ---------------------------------------------------------------------------
# Display formatting
# ---------------------------------------------------------------------------

def format_unit_label(unit: str) -> str:
    """Prettier rendering of the internal unit string for on-screen display."""
    return {
        "m^2":       "m²",
        "cm^2":      "cm²",
        "mm^2":      "mm²",
        "in^2":      "in²",
        "ft^2":      "ft²",
        "m^3":       "m³",
        "cm^3":      "cm³",
        "ft^3":      "ft³",
        "kg/m^3":    "kg/m³",
        "lbm/ft^3":  "lbm/ft³",
        "N*s":       "N·s",
        "lbf*s":     "lbf·s",
    }.get(unit, unit)
