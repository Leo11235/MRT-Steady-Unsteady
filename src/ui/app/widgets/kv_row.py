"""
KVRow — one row of a results table.

    [ Pretty name (unit) .................. ] [ value ........... ]

Rows remember the raw key and the raw SI value they were built from, so
switching the global unit system re-labels and re-converts in place with two
configure() calls.  Rebuilding a few hundred rows on every toggle was visibly
slow in the old UI.

The name and unit both come from the field registry, so a value shown here
carries the same label it had on the input form.  Result keys the registry
doesn't know about — computed outputs like `total_impulse`, which are never
inputs — fall back to the suffix parser below.
"""

from __future__ import annotations

from typing import Any, Optional

import customtkinter as ctk

from src.common import variable_conversions as vc
from src.ui.app import theme
from src.ui.app import field_registry as registry


# =============================================================================
# Working out what a result key means
# =============================================================================
#
# Two sources, in order:
#
#   1. The field registry, which covers everything that was an input.
#   2. The suffix on the key itself. Unsteady OUTPUT keys still carry their
#      unit (peak_thrust_N, apogee_m_agl, burntime_s), even though input keys
#      no longer do. Parsing them saves naming every computed value by hand.
#
# Anything neither source explains renders unitless, which is right for ratios
# and exponents and merely unhelpful for the rest.

_SUFFIX_UNITS: dict[str, str] = {
    "_m": "m", "_m2": "m2", "_m3": "m3",
    "_kg": "kg", "_kgs": "kg/s", "_kgm3": "kg/m3",
    "_pa": "Pa", "_k": "K", "_s": "s", "_n": "N", "_ns": "N*s",
    "_ms": "m/s", "_deg": "deg", "_rad": "rad",
}

# Explicit entries for computed values whose names don't self-describe.
_COMPUTED_FIELDS: dict[str, tuple[str, str]] = {
    # key: (label, SI unit)
    "thrust":                          ("Thrust", "N"),
    "Isp":                             ("Isp", "s"),
    "burntime":                        ("Burn time", "s"),
    "total_impulse":                   ("Total impulse", "N*s"),
    "wet_mass":                        ("Wet mass", "kg"),
    "reached_apogee":                  ("Apogee reached", "m"),
    "apogee":                          ("Apogee", "m"),
    # steady flight_dict series. The Trajectory tab shows <name>_max and
    # <name>_final, which the suffix stripper below reduces to these.
    "altitude":                        ("Altitude", "m"),
    "velocity":                        ("Velocity", "m/s"),
    "acceleration":                    ("Acceleration", "m/s2"),
    "drag_force":                      ("Drag force", "N"),
    "grav_force":                      ("Gravitational force", "N"),
    "time":                            ("Time", "s"),
    "chamber_temperature":             ("Chamber temperature", "K"),
    "nozzle_throat_area":              ("Nozzle throat area", "m2"),
    "nozzle_exit_area":                ("Nozzle exit area", "m2"),
    "nozzle_throat_radius":            ("Nozzle throat radius", "m"),
    "nozzle_exit_radius":              ("Nozzle exit radius", "m"),
    "nozzle_gas_exit_pressure":        ("Nozzle exit pressure", "Pa"),
    "nozzle_gas_exit_temperature":     ("Nozzle exit temperature", "K"),
    "nozzle_gas_exit_velocity":        ("Nozzle exit velocity", "m/s"),
    "average_fuel_mass_flow_rate":     ("Average fuel mass flow", "kg/s"),
    "total_propellant_mass_flow_rate": ("Total propellant flow", "kg/s"),
    "initial_internal_fuel_radius":    ("Initial port radius", "m"),
    # dimensionless, listed so they get a decent label rather than a raw key
    "average_oxidizer_to_fuel_ratio":  ("Average O/F ratio", "."),
    "thrust_to_weight_ratio":          ("Thrust-to-weight ratio", "."),
    "heat_capacity_ratio":             ("Heat capacity ratio", "."),
    "nozzle_gas_exit_mach_number":     ("Nozzle exit Mach", "."),
    "chamber_gas_molar_weight":        ("Chamber gas molar mass", "kg/mol"),
}


# How far the rocket WENT, as opposed to how big a part of it is. A key whose
# name contains one of these is a mission distance: metres and feet, not
# centimetres and inches.
#
# Matched on the name rather than enumerated, because unsteady emits dozens of
# these (apogee_m_asl, apogee_m_agl, max_altitude_m, downrange_m, ...) and any
# fixed list would go stale the first time someone adds an output.
_DISTANCE_WORDS = (
    "apogee", "altitude", "downrange", "range", "distance", "asl", "agl",
)


def category_of_key(key: str) -> Optional[str]:
    """The DISPLAY category for a result key, or None if we can't tell.

    Needed because "length" and "distance" share a unit table: both are metres
    in SI, so the unit string alone can't say whether a value is a grain
    diameter (centimetres, inches) or an apogee (metres, feet).

    The registry wins when it knows the key. Otherwise, if the key is
    length-dimensioned, the name decides.
    """
    if registry.has(key):
        category = registry.get(key).category
        return None if category == "dimensionless" else category

    _label, si_unit = _describe_uncategorised(key)
    if si_unit and vc.category_of(si_unit) == "length":
        lowered = key.lower()
        if any(word in lowered for word in _DISTANCE_WORDS):
            return "distance"
        return "length"
    return None


def describe(key: str) -> tuple[str, Optional[str]]:
    """(label, SI unit) for a result key.  Unit is None when dimensionless."""
    if registry.has(key):
        spec = registry.get(key)
        if spec.category == "dimensionless":
            return spec.label, None
        return spec.label, vc.SI_UNITS[spec.category]
    return _describe_uncategorised(key)


def _describe_uncategorised(key: str) -> tuple[str, Optional[str]]:
    """The half of describe() that doesn't consult the field registry.

    Split out so category_of_key() can reach it without recursing back through
    describe(), which would call category_of_key() again.
    """
    if key in _COMPUTED_FIELDS:
        label, unit = _COMPUTED_FIELDS[key]
        return label, (None if unit == "." else unit)

    # The trajectory tab summarises each series as <name>_max / <name>_final.
    # Those aren't separate quantities, so resolve the stem and keep the
    # qualifier in the label.
    for qualifier in ("_max", "_final"):
        if key.endswith(qualifier) and key[: -len(qualifier)] in _COMPUTED_FIELDS:
            label, unit = _COMPUTED_FIELDS[key[: -len(qualifier)]]
            return (f"{label} ({qualifier.lstrip('_')})",
                    None if unit == "." else unit)

    # Fall back to the suffix, longest first so "_m3" wins over "_m".
    lowered = key.lower()
    for suffix in sorted(_SUFFIX_UNITS, key=len, reverse=True):
        if lowered.endswith(suffix):
            return _prettify(key[: -len(suffix)]), _SUFFIX_UNITS[suffix]
        # Some keys bury the unit mid-name: apogee_m_agl, altitude_m_asl.
        if f"{suffix}_" in lowered:
            return _prettify(key.replace(suffix, "", 1)), _SUFFIX_UNITS[suffix]

    return _prettify(key), None


def _prettify(key: str) -> str:
    """Turn a snake_case key into something readable."""
    return key.replace("_", " ").strip().capitalize() or key


# =============================================================================
# Formatting
# =============================================================================

def format_scalar(value: Any) -> str:
    """Render one value for display.

    Trims trailing zeros, drops a pointless ".0", and switches to scientific
    notation for very small numbers instead of showing "0".
    """
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value:                  # NaN
            return "—"
        if abs(value) < 1e-15:
            return "0"
        if abs(value - round(value)) < 1e-9 and abs(value) < 1e15:
            return str(int(round(value)))
        if abs(value) < 1e-3 or abs(value) >= 1e7:
            return f"{value:.4g}"
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if isinstance(value, dict):
        return f"({len(value)} keys)"
    if isinstance(value, (list, tuple)):
        return f"[{len(value)} items]"
    return str(value)


def as_pair(value: Any) -> Optional[tuple[float, str]]:
    """Recognise a config-style [value, unit] pair.

    Results files echo the inputs back verbatim, pairs included, so a results
    page will meet them. Without this they render as "[2 items]", which is
    both useless and slightly insulting.
    """
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    number, unit = value
    if isinstance(number, bool) or not isinstance(number, (int, float)):
        return None
    if not isinstance(unit, str) or not vc.is_known_unit(unit):
        return None
    return float(number), unit


def native_system_of(results: dict) -> str:
    """Which unit system a results file's numbers are actually stored in.

    NOT always SI. steady_main rewrites every dict in place when
    simulation_settings.output_units is "MRT", so an MRT run's file holds feet
    and psi. Read it back as SI and every number on the page is wrong by a
    conversion factor — which is how the shortfall dialog came to announce a
    45000 ft target as "45000 m".

    Only "MRT" triggers that rewrite in the backend; "IMP" falls through and
    the file stays SI. Mirror that rather than what the setting is named.
    """
    units = ((results or {}).get("simulation_settings") or {}).get("output_units")
    return "MRT" if units == "MRT" else "SI"


def convert_for_display(value: Any, si_unit: Optional[str], system: str,
                        category: Optional[str] = None,
                        native_system: str = "SI") -> tuple[str, str]:
    """(formatted value, unit label) for a value in the given unit system.

    `category` overrides what would otherwise be inferred from `si_unit`. Pass
    it whenever you know it: metres are both "length" and "distance", and only
    the caller can say which.

    `native_system` is the system the STORED value is in. See
    native_system_of(); it is not always SI.

    Non-numeric values and dimensionless quantities pass through untouched.
    """
    # A pair carries its own unit, which beats whatever the registry guessed
    # for the key.
    pair = as_pair(value)
    if pair is not None:
        number, unit = pair
        try:
            target = vc.unit_for_system(vc.category_of(unit), system)
            return format_scalar(vc.convert(number, unit, target)), target
        except (ValueError, KeyError):
            return format_scalar(number), unit

    if si_unit is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return format_scalar(value), ""
    try:
        resolved = category or vc.category_of(si_unit)
        source = vc.storage_unit(resolved, native_system)
        target = vc.unit_for_system(resolved, system)
        return format_scalar(vc.convert(float(value), source, target)), target
    except (ValueError, KeyError):
        return format_scalar(value), si_unit


# =============================================================================
# The widget
# =============================================================================

class KVRow(ctk.CTkFrame):
    """A name/value row that can re-unit itself without being rebuilt."""

    _NAME_WIDTH = 340

    def __init__(self, master, key: str, value: Any, system: str = "SI",
                 *, name_width: Optional[int] = None,
                 native_system: str = "SI") -> None:
        super().__init__(master, fg_color="transparent")

        self.key = key
        self._value = value
        self._label, self._si_unit = describe(key)
        self._category = category_of_key(key)
        self._native_system = native_system

        shown, unit_label = convert_for_display(value, self._si_unit, system,
                                                self._category, native_system)

        self._name_widget = ctk.CTkLabel(
            self, text=self._compose_name(unit_label),
            width=name_width or self._NAME_WIDTH, anchor="w",
        )
        self._name_widget.pack(side="left", padx=(0, theme.PAD_S))

        self._value_widget = ctk.CTkLabel(
            self, text=shown, anchor="w", justify="left", wraplength=520,
        )
        self._value_widget.pack(side="left", fill="x", expand=True,
                                padx=(0, theme.PAD_L))

    def _compose_name(self, unit_label: str) -> str:
        return f"{self._label} ({unit_label})" if unit_label else self._label

    def update_system(self, system: str) -> None:
        """Re-label and re-convert for a new unit system.  No rebuild."""
        shown, unit_label = convert_for_display(self._value, self._si_unit, system,
                                                self._category, self._native_system)
        self._name_widget.configure(text=self._compose_name(unit_label))
        self._value_widget.configure(text=shown)

    def matches(self, query: str) -> bool:
        """Case-insensitive search across the label, the raw key and the value.

        Including the raw key means someone who knows the JSON can search for
        `apogee_m_agl` and find the row labelled "Apogee".
        """
        if not query or not query.strip():
            return True
        needle = query.lower().strip()
        haystack = "\n".join((
            self._name_widget.cget("text"),
            self.key,
            str(self._value_widget.cget("text")),
        )).lower()
        return needle in haystack
