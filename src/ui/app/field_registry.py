"""
One entry per input field: what to call it, what unit it carries, what to
explain about it.

WHY THIS EXISTS
---------------
The old UI described the same field in six different places — a label dict on
the steady page, another on the unsteady page, a help dict beside each, a
unit-category map in display.py, and a pretty-name map in results_units.py.
Adding a field meant six edits, and they drifted.  Worse, results pages and
input forms disagreed about what things were called.

This module is the single answer to "what is this key?".  The input forms build
themselves from it, and the results pages read the same entries, so a value
shown on a results page carries the same label and unit it had on the form.

WHAT LIVES HERE VS. IN THE SCHEMA
---------------------------------
The backend's input_schema.jsonc decides WHICH fields exist and WHEN they're
required — per CV, per physics model, and which pairs are alternates.  That
stays the backend's business, because the physics decides it.

This registry decides HOW each field is presented.  It carries no notion of
"required", no grouping, and no model logic.  Anything the schema can answer,
ask the schema.

The two must agree on key names, which `check_registry_covers_schema()` at the
bottom asserts.  It's exposed for the test suite to call, so a field added to a
schema without a label fails a test rather than showing up as a blank row.

UNITS
-----
`category` names a category in src/common/variable_conversions.py, which is
where the unit dropdown's options come from.  Fields whose category is
"dimensionless" get no dropdown.

A blank form starts every field in the user's chosen unit system, from the
"Default output units" setting: SI, MRT or IMP.  Nothing is hardcoded per
field, so switching that setting moves the whole form together rather than
leaving a scattering of exceptions behind.

DEFAULT VALUES
--------------
Pre-filled values live in src/common/static_data/default_inputs.jsonc, not
here.  They're physical properties and empirical constants, so they belong
beside the unit tables where the backend can read them too, and where they can
be documented with their sources.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from src.common import default_inputs
from src.common import variable_conversions as vc


# =============================================================================
# The entry
# =============================================================================

@dataclass(frozen=True)
class FieldSpec:
    """How one config key is presented to the user.

    key         The name used in the config file and by the backend.
    label       What the form and results pages call it.
    category    A category from variable_conversions ("length", "pressure",
                "dimensionless", ...).  Drives the unit dropdown.
    help        Tooltip text.  Say what it means and give a typical value;
                this is the only in-app documentation these inputs get.
    value_type  "float", "int" or "text".  Controls coercion and validation.
    choices     For "text" fields with a fixed set of valid answers; renders
                as a dropdown instead of a free-text entry.
    """
    key: str
    label: str
    category: str
    help: str
    value_type: str = "float"
    choices: tuple[str, ...] = ()

    def unit_for(self, system: str = "SI") -> str:
        """The unit a blank form shows, in the user's chosen unit system."""
        try:
            return vc.unit_for_system(self.category, system)
        except (ValueError, KeyError):
            return vc.SI_UNITS[self.category]

    @property
    def unit(self) -> str:
        """SI unit for this field.  Prefer unit_for() where the system matters."""
        return vc.SI_UNITS[self.category]

    @property
    def default(self) -> Any:
        """Pre-filled value as a [value, unit] pair, or None for a blank field.

        Read from default_inputs.jsonc rather than stored here, so the values
        stay data and can carry their own documentation.
        """
        return default_inputs.default_for(self.key)

    @property
    def unit_options(self) -> list[str]:
        """Every unit the dropdown offers.  Empty for dimensionless and text
        fields, which means "render no dropdown"."""
        if self.category == "dimensionless" or self.value_type == "text":
            return []
        return vc.units_in_category(self.category)

    @property
    def is_numeric(self) -> bool:
        return self.value_type in ("float", "int")


DIMENSIONLESS = "dimensionless"


# =============================================================================
# Steady fields
# =============================================================================

_STEADY: tuple[FieldSpec, ...] = (
    FieldSpec("oxidizer_mass_flow_rate", "Oxidizer mass flow rate", "mass_flow",
              "Steady-state N2O mass flow rate through the injector."),
    FieldSpec("chamber_pressure", "Chamber pressure", "pressure",
              "Combustion-chamber stagnation pressure."),
    FieldSpec("fuel_external_diameter", "Fuel external diameter", "length",
              "Outer diameter of the fuel grain, bounded by the case."),
    FieldSpec("fuel_length", "Fuel length", "length",
              "Length of the fuel grain."),
    FieldSpec("fuel_grain_density", "Fuel grain density", "density",
              "Bulk density of the solid fuel."),
    FieldSpec("regression_rate_scaling_coefficient", "Regression coefficient (a)", DIMENSIONLESS,
              "The 'a' in r_dot = a*G^n, with G in kg/m2/s and r_dot in m/s.\nWARNING: though listed as dimensionless, a's units in SI are actually m^(1+2n) · kg^(-n) · s^(n-1), where n is the regression rate exponent. The default value is verified via research and changing it is not recommended."
              "Paraffin with N2O is around 0.000132."),
    FieldSpec("regression_rate_exponent", "Regression exponent (n)", DIMENSIONLESS,
              "The 'n' in r_dot = a*G^n. Paraffin with N2O is around 0.555."),
    FieldSpec("liquid_oxidizer_type", "Liquid oxidizer", DIMENSIONLESS,
              "Oxidizer species, looked up in the PROPEP tables.",
              value_type="text", choices=("NITROUS OXIDE",)),
    FieldSpec("solid_fuel_type", "Solid fuel", DIMENSIONLESS,
              "Fuel species, looked up in the PROPEP tables.",
              value_type="text", choices=("EICOSANE (PARAFFIN)",)),

    # kinematics
    FieldSpec("target_apogee", "Target apogee", "distance",
              "Design apogee. The convergence solver iterates fuel mass until the trajectory reaches this."),
    FieldSpec("launch_site_altitude", "Launch site altitude", "distance",
              "Launch-site elevation above sea level."),
    FieldSpec("dry_mass", "Dry mass", "mass",
              "The mass of the rocket without any fuel."),
    FieldSpec("rocket_external_diameter", "Rocket external diameter", "length",
              "Airframe outer diameter."),
    FieldSpec("drag_coefficient", "Drag coefficient", DIMENSIONLESS,
              "Rocket drag coefficient. Slender rockets sit around 0.5 to 0.7."),
    FieldSpec("launch_angle", "Launch angle", "angle",
              "Launch rail angle from vertical. 0 degrees is straight up."),

    # hotfire alternates: fill exactly one
    FieldSpec("fuel_mass", "Fuel mass", "mass",
              "Total solid fuel loaded. Fill this OR the initial port "
              "diameter, not both."),
    FieldSpec("initial_internal_fuel_diameter", "Initial port diameter", "length",
              "Initial fuel port diameter. Fill this OR the fuel mass, not "
              "both."),
)


# =============================================================================
# Unsteady fields
# =============================================================================

_UNSTEADY: tuple[FieldSpec, ...] = (
    # ---- CV1 tank ----
    FieldSpec("tank_internal_diameter", "Internal diameter", "length",
              "Inner diameter of the oxidizer tank shell."),
    FieldSpec("tank_temperature", "Initial temperature", "temperature",
              "Initial N2O bulk temperature."),
    FieldSpec("tank_oxidizer_mass", "Oxidizer mass", "mass",
              "Total oxidizer mass."),
    FieldSpec("dip_tube_external_diameter", "Dip tube external diameter", "length",
              "External diameter of the dip tube."),
    FieldSpec("dip_tube_internal_diameter", "Dip tube internal diameter", "length",
              "Internal flow diameter of the dip tube."),
    FieldSpec("dip_tube_length", "Dip tube length", "length",
              "Length of the dip tube, measured down from the top of the tank."),
    FieldSpec("tank_ullage_fraction", "Ullage fraction", DIMENSIONLESS,
              "Fraction of tank volume that is gas at t=0, from 0 to 1. Fill "
              "this OR the internal length, not both."),
    FieldSpec("tank_internal_length", "Internal length", "length",
              "Full internal length, including end caps. Fill this OR the "
              "ullage fraction, not both."),

    # ---- CV2 valve ----
    FieldSpec("valve_time_constant", "Time constant", "time",
              "How long the linear ramp takes to go fully open. 0 means "
              "instantaneous. \nWARNING: Slow valves with an opening time of above ~0.05s can destabilise the solver."),
    FieldSpec("sigmoid_half_time", "Sigmoid half-time", "time",
              "Time at which the sigmoid valve reaches 50 percent open."),
    FieldSpec("sigmoid_steepness", "Sigmoid steepness", DIMENSIONLESS,
              "Sharpness of the sigmoid. Higher values approach a step."),

    # ---- CV3 injector ----
    FieldSpec("injector_discharge_coefficient", "Discharge coefficient", DIMENSIONLESS,
              "Injector discharge coefficient. MRT's injectors run 0.6 to 0.85."),
    FieldSpec("injector_number_of_holes", "Number of holes", DIMENSIONLESS,
              "Total number of orifices in the injector plate.",
              value_type="int"),
    FieldSpec("injector_hole_diameter", "Hole diameter", "length",
              "Diameter of one injector hole."),
    FieldSpec("feed_pressure_loss", "Feed pressure loss", "pressure",
              "Static pressure lost upstream of the injector, across the feed lines and valve."),

    # ---- CV4 chamber ----
    FieldSpec("chamber_fuel_length", "Fuel length", "length",
              "Length of the fuel grain."),
    FieldSpec("chamber_fuel_density", "Fuel density", "density",
              "Bulk density of the solid fuel."),
    FieldSpec("chamber_fuel_external_diameter", "Fuel external diameter", "length",
              "Outer diameter of the fuel grain, bounded by the case."),
    FieldSpec("chamber_regression_rate_scaling_constant", "Regression coefficient (a)", DIMENSIONLESS,
              "The 'a' in r_dot = a*G^n. Paraffin with N2O is around 0.000132.\nWARNING: though listed as dimensionless, a's units in SI are actually m^(1+2n) · kg^(-n) · s^(n-1), where n is the regression rate exponent. The default value is verified via research and changing it is not recommended."),
    FieldSpec("chamber_regression_rate_exponent", "Regression exponent (n)", DIMENSIONLESS,
              "The 'n' in r_dot = a*G^n. Paraffin with N2O is around 0.555."),
    FieldSpec("chamber_cstar_efficiency", "C* efficiency", DIMENSIONLESS,
              "Fraction of the theoretical characteristic velocity (c*) that the chamber actually delivers, from 0 to 1. 1.0 assumes perfect combustion. Paraffin/N2O hybrids typically run 0.85 to 0.95. Lowering it drops chamber pressure, thrust and Isp by roughly the same fraction."),
    FieldSpec("pre_chamber_diameter", "Pre-chamber diameter", "length",
              "Diameter of the empty volume upstream of the fuel grain."),
    FieldSpec("pre_chamber_length", "Pre-chamber length", "length",
              "Length of the empty volume upstream of the fuel grain. With the "
              "diameter this sets the pre-chamber volume."),
    FieldSpec("post_chamber_diameter", "Post-chamber diameter", "length",
              "Diameter of the empty volume between the grain and the throat."),
    FieldSpec("post_chamber_length", "Post-chamber length", "length",
              "Length of the empty volume between the grain and the throat."),
    FieldSpec("chamber_fuel_mass", "Fuel mass", "mass",
              "Total solid fuel loaded. Fill this OR the internal diameter, not both."),
    FieldSpec("chamber_fuel_internal_diameter", "Fuel internal diameter", "length",
              "Initial fuel port diameter. Fill this OR the fuel mass, not both."),

    # ---- CV5 nozzle ----
    FieldSpec("nozzle_throat_diameter", "Throat diameter", "length",
              "Nozzle throat diameter. Sets the chamber pressure for a given "
              "mass flow, so it is the single most sensitive nozzle input."),
    FieldSpec("nozzle_exit_diameter", "Exit diameter", "length",
              "Nozzle exit-plane diameter. Together with the throat this sets "
              "the expansion ratio, and so the altitude the nozzle suits."),

    # ---- CV6 trajectory ----
    FieldSpec("rocket_dry_mass", "Dry mass", "mass",
              "The mass of the rocket without any fuel."),
    FieldSpec("rocket_drag_coefficient", "Drag coefficient", DIMENSIONLESS,
              "Rocket drag coefficient. Slender rockets sit around 0.5 to 0.7."),
    FieldSpec("rocket_outer_diameter", "Outer diameter", "length",
              "Rocket maximum outer diameter."),
    FieldSpec("rocket_launch_angle", "Launch angle", "angle",
              "Launch rail angle from vertical. 0 degrees is straight up."),
    FieldSpec("drogue_parachute_drag_coefficient", "Drogue drag coefficient", DIMENSIONLESS,
              "Drogue parachute drag coefficient."),
    FieldSpec("drogue_parachute_diameter", "Drogue diameter", "length",
              "Drogue parachute canopy diameter."),
    FieldSpec("main_parachute_deployment_altitude_agl", "Main deploy altitude AGL", "distance",
              "Altitude above ground at which the main parachute deploys."),
    FieldSpec("main_parachute_drag_coefficient", "Main drag coefficient", DIMENSIONLESS,
              "Main parachute drag coefficient."),
    FieldSpec("main_parachute_diameter", "Main diameter", "length",
              "Main parachute canopy diameter."),
    FieldSpec("launch_site_altitude_asl", "Launch site altitude ASL", "distance",
              "Launch-site elevation above sea level."),
)


# =============================================================================
# Physics model presentation
# =============================================================================
#
# Which models exist per CV comes from the schema.  These two say how to show
# them: a display name, and a paragraph explaining what the model assumes.

MODEL_LABELS: dict[str, str] = {
    "saturated_equilibrium": "Saturated equilibrium",
    "linear":                "Linear",
    "sigmoid":               "Sigmoid",
    "instant":               "Instant",
    "SPI":                   "SPI",
    "0D_quasi_steady":       "0D quasi-steady",
    "1D_frozen":             "1D frozen",
    "2dof":                  "2-DOF",
}

MODEL_DESCRIPTIONS: dict[str, str] = {
    "saturated_equilibrium":
        "Treats the tank contents as liquid and vapour N2O in constant phase "
        "equilibrium. Tank pressure follows the saturation curve at the "
        "current temperature, and both the liquid and vapour-only blowdown "
        "regimes are handled automatically as the tank empties.",
    "linear":
        "The valve opens linearly from closed to fully open over the time "
        "constant.",
    "sigmoid":
        "The valve opens along a logistic curve centred on the half-time. "
        "Steepness controls how sharp the transition is, with high values "
        "approaching a step. More realistic for solenoid and pilot-operated "
        "valves that ease in and out.",
    "instant":
        "The valve is fully open at t=0. No opening transient at all.",
    "SPI":
        "Single-phase incompressible. Treats the upstream N2O as pure liquid "
        "across the injector, which holds while the tank still has liquid. "
        "Vapour-phase flow falls back to a choked-flow relation.",
    "0D_quasi_steady":
        "Treats the chamber as one well-mixed control volume at instantaneous "
        "chemical equilibrium. Combustion properties come from CEA at the "
        "current pressure and O/F, and fuel regresses radially as "
        "r_dot = a*G^n. Pre- and post-chamber volumes add gas storage and damp "
        "pressure transients.",
    "1D_frozen":
        "One-dimensional isentropic expansion with frozen chemistry, so the "
        "exhaust composition is fixed at the throat and does not recombine "
        "downstream. Detects under-expanded, ideal and over-expanded flow, "
        "including separation in heavily over-expanded cases.",
    "2dof":
        "Two-degree-of-freedom point mass, vertical and downrange. Uses a "
        "fixed drag coefficient times frontal area, standard-atmosphere "
        "density and altitude-dependent gravity. Drogue deploys at apogee, "
        "main at the specified AGL altitude.",
}


def model_label(wire: str) -> str:
    """Display name for a model, falling back to the wire name."""
    return MODEL_LABELS.get(wire, wire)


def model_wire(label: str) -> str:
    """Reverse of model_label."""
    for wire, shown in MODEL_LABELS.items():
        if shown == label:
            return wire
    return label


def model_description(wire: str) -> str:
    return MODEL_DESCRIPTIONS.get(wire, "")


# =============================================================================
# Lookup
# =============================================================================

FIELDS: dict[str, FieldSpec] = {spec.key: spec for spec in (_STEADY + _UNSTEADY)}

# Keys unique to each simulator, for the rare caller that needs to know.
STEADY_KEYS: tuple[str, ...] = tuple(spec.key for spec in _STEADY)
UNSTEADY_KEYS: tuple[str, ...] = tuple(spec.key for spec in _UNSTEADY)


def get(key: str) -> FieldSpec:
    """The spec for a key.  Raises KeyError for an unregistered one, which is
    always a bug rather than a user-input problem."""
    if key not in FIELDS:
        raise KeyError(
            f"No field registry entry for {key!r}. Add one to field_registry.py "
            f"so the form and the results pages agree about what it is."
        )
    return FIELDS[key]


def label(key: str) -> str:
    """Display label, falling back to the raw key so an unregistered field
    still renders something rather than crashing a whole page."""
    spec = FIELDS.get(key)
    return spec.label if spec else key


def help_text(key: str) -> str:
    spec = FIELDS.get(key)
    return spec.help if spec else ""


def category(key: str) -> Optional[str]:
    spec = FIELDS.get(key)
    return spec.category if spec else None


def has(key: str) -> bool:
    return key in FIELDS


# =============================================================================
# Consistency with the backend schemas
# =============================================================================

_ROOT = Path(__file__).resolve().parents[3]
_UNSTEADY_SCHEMA = _ROOT / "src" / "backend" / "unsteady" / "static_data" / "input_schema.jsonc"
_STEADY_SCHEMA = _ROOT / "src" / "backend" / "steady" / "static_data" / "input_schema.jsonc"


def _read_jsonc(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    # Trailing commas are legal in .jsonc and turn up whenever someone comments
    # out the last entry in a block. Strip them rather than failing to parse.
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return json.loads(text)


def _flatten(items) -> list[str]:
    """Schema lists nest one level for alternate-field pairs."""
    out: list[str] = []
    for item in items:
        out.extend(item) if isinstance(item, list) else out.append(item)
    return out


def unsteady_schema_keys() -> dict[tuple[str, str], list[str]]:
    """{(cv, model): [field keys]} straight from the backend schema.

    This is what the unsteady form iterates to decide which fields to show for
    the currently selected model."""
    schema = _read_jsonc(_UNSTEADY_SCHEMA)
    return {(cv, model): _flatten(keys)
            for cv, models in schema.items()
            for model, keys in models.items()}


def steady_schema_keys() -> dict[str, list[str]]:
    """{group: [field keys]} from the backend schema.

    NOTE: the steady schema names PHYSICS keys (fuel_external_radius) because
    steady validates after the diameter-to-radius conversion, whereas the
    unsteady schema names USER keys (tank_internal_diameter) because it
    validates before.  We translate here so callers see user keys either way.
    """
    schema = _read_jsonc(_STEADY_SCHEMA)
    return {group: [_radius_to_diameter(k) for k in _flatten(keys)]
            for group, keys in schema.items()}


def _radius_to_diameter(key: str) -> str:
    """Mirror of the backend loaders' diameter-to-radius rename, run backwards.

    Only used to reconcile the steady schema with this registry; the UI itself
    always writes diameters."""
    return key.replace("radius", "diameter") if "radius" in key else key


def check_registry_covers_schema() -> list[str]:
    """Every key either schema names must have a registry entry.

    Returns a list of problems, empty when consistent.  Also checks that every
    declared unit category and default unit actually exists in
    variable_conversions, since a bad one there would only surface when the
    form tried to render that field's dropdown.
    """
    problems: list[str] = []

    for (cv, model), keys in unsteady_schema_keys().items():
        for key in keys:
            if key not in FIELDS:
                problems.append(f"unsteady {cv}/{model}: {key!r} has no registry entry")

    for group, keys in steady_schema_keys().items():
        for key in keys:
            if key not in FIELDS:
                problems.append(f"steady {group}: {key!r} has no registry entry")

    # Every category must exist in variable_conversions, and must resolve to a
    # real unit in all three systems, otherwise the dropdown blows up at render
    # time in whichever system the user happens to have selected.
    for spec in FIELDS.values():
        if spec.category not in vc.CATEGORIES:
            problems.append(f"{spec.key!r}: unknown unit category {spec.category!r}")
            continue
        for system in vc.UNIT_SYSTEMS:
            unit = spec.unit_for(system)
            if unit not in vc.units_in_category(spec.category):
                problems.append(
                    f"{spec.key!r}: {system} resolves to {unit!r}, which isn't "
                    f"a {spec.category} unit")

    # A default must be a pair whose unit matches the field's category, or a
    # string for a text field. A mismatch would load a wrong number silently.
    for spec in FIELDS.values():
        default = spec.default
        if default is None:
            continue
        if spec.value_type == "text":
            if not isinstance(default, str):
                problems.append(f"{spec.key!r}: text field has a non-string default")
        elif not (isinstance(default, (list, tuple)) and len(default) == 2):
            problems.append(f"{spec.key!r}: default should be a [value, unit] pair")
        elif not vc.is_known_unit(default[1]):
            problems.append(f"{spec.key!r}: default unit {default[1]!r} is unknown")
        elif vc.category_of(default[1]) != spec.category:
            problems.append(
                f"{spec.key!r}: default unit {default[1]!r} is "
                f"{vc.category_of(default[1])}, not {spec.category}")

    return problems
