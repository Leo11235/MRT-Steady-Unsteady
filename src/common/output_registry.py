"""
What every unsteady RESULT key means.

The sibling of field_registry.py.  That one describes what the user types IN;
this one describes what the simulation writes OUT.

WHY THIS EXISTS
---------------
Unsteady output keys used to carry their unit in the name: peak_thrust_N,
burntime_s, apogee_m_agl.  kv_row parsed that suffix to work out what the
number was, which meant the unit system lived in a string convention rather
than anywhere you could look it up.  It also made the names unreadable and the
convention unenforceable: nothing stopped someone writing peak_thrust_kN.

So the names are now bare (peak_thrust, burntime, apogee_agl) and this module
is where their meaning lives.

READING OLD FILES
-----------------
Results files already on disk still hold the old spellings, and rewriting a
user's saved runs to fix a naming decision is not a trade worth making.  Every
spec therefore carries its `legacy` names, and value_of() resolves either.  A
file written in 2025 and one written today both render correctly, and the alias
list doubles as a record of what things used to be called.

ADDING AN OUTPUT
----------------
Add the OutputSpec here and write the key in objects.py.  The two must agree:
check_registry_covers_results() in the test suite fails if either side has a
key the other does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.common import variable_conversions as vc


DIMENSIONLESS = "dimensionless"
TEXT = "text"           # not a number; rendered as-is, never unit-converted


@dataclass(frozen=True)
class OutputSpec:
    """One result value, and everything a display surface needs to show it.

    key         Bare name, no unit suffix.  What objects.py writes today.
    label       What every surface calls it.  Fix a spelling here and the
                results page, the PDF and the figures all follow.
    category    A variable_conversions category, or DIMENSIONLESS/TEXT.
                Drives unit conversion and the unit shown beside the number.
    scopes      Which blocks of the results file this key appears in.
    aggregate   How a per-phase row combines into a totals column:
                "sum", "max", "min", or None when no total is meaningful
                (an average of averages is not an average).
    legacy      Older spellings of this key, still found in saved runs.
    help        One line on what it means, for tooltips.
    display_scale
                Multiply the stored value by this before showing it.  Exists for
                exactly one thing: the physics stores radii and every human-facing
                surface talks in diameters, so the doubling lives here rather than
                being repeated at each call site.  Leave it 1.0 for everything else.
    """
    key: str
    label: str
    category: str
    scopes: tuple[str, ...] = ("overall",)
    aggregate: Optional[str] = None
    legacy: tuple[str, ...] = ()
    help: str = ""
    display_scale: float = 1.0

    @property
    def si_unit(self) -> Optional[str]:
        """The SI unit, or None for dimensionless and text."""
        if self.category in (DIMENSIONLESS, TEXT):
            return None
        return vc.SI_UNITS[self.category]

    def unit_for(self, system: str = "SI") -> Optional[str]:
        """The unit this value should be DISPLAYED in, for a unit system."""
        if self.category in (DIMENSIONLESS, TEXT):
            return None
        return vc.unit_for_system(self.category, system)


# =============================================================================
# The outputs
# =============================================================================
#
# Grouped the way a person reads a run: did it work, how did the engine do,
# where did it go, what did it burn.  The order here is not the display order;
# each surface picks its own.

_SPECS: tuple[OutputSpec, ...] = (

    # ---- run metadata -------------------------------------------------
    OutputSpec("terminal_state", "Terminal state", TEXT, ("metadata",),
               help="Which exit condition ended the run."),
    OutputSpec("completed_nominally", "Completed nominally", TEXT, ("metadata",),
               help="True when the run reached a successful terminal state."),
    OutputSpec("terminal_reason", "Terminal reason", TEXT, ("metadata",),
               help="Plain-language version of the terminal state."),
    OutputSpec("total_timesteps", "Total timesteps", DIMENSIONLESS, ("metadata",),
               help="Solver steps kept across every phase."),
    OutputSpec("total_simulation_time", "Simulated flight time", "time", ("metadata",),
               help="Simulated time from ignition to the terminal state. Not wall clock."),

    # ---- timing -------------------------------------------------------
    OutputSpec("burntime", "Burn time", "time", ("overall", "steady"),
               legacy=("burntime_s",),
               help="Total time the engine produced thrust."),
    OutputSpec("t_start", "Start time", "time", ("phase",), aggregate="min",
               legacy=("t_start_s",),
               help="Simulated time this phase began."),
    OutputSpec("t_end", "End time", "time", ("phase",), aggregate="max",
               legacy=("t_end_s",),
               help="Simulated time this phase ended."),
    OutputSpec("duration", "Duration", "time", ("phase",), aggregate="sum",
               legacy=("duration_s",),
               help="How long this phase lasted."),
    OutputSpec("t", "Time", "time", ("event",),
               legacy=("t_s",),
               help="Simulated time an event fired."),
    OutputSpec("event_type", "Event", TEXT, ("event",),
               help="What kind of event fired: a phase transition, a warning, a cutoff."),
    OutputSpec("message", "Message", TEXT, ("event",),
               help="Human-readable description of the event."),

    # ---- thrust -------------------------------------------------------
    OutputSpec("total_impulse", "Total impulse", "impulse", ("overall", "phase", "steady"),
               aggregate="sum", legacy=("total_impulse_Ns",),
               help="Thrust integrated over time."),
    OutputSpec("peak_thrust", "Peak thrust", "force", ("overall", "phase"),
               aggregate="max", legacy=("peak_thrust_N",),
               help="Highest instantaneous thrust."),
    OutputSpec("average_thrust", "Average thrust", "force", ("overall", "phase"),
               legacy=("average_thrust_N",),
               help="Total impulse divided by duration. No meaningful total across "
                    "phases: averaging averages is not an average."),
    OutputSpec("peak_acceleration", "Peak acceleration", "acceleration",
               ("overall", "phase", "steady"), aggregate="max",
               help="Largest acceleration magnitude. Unsteady measures it while the engine "
                    "is firing and excludes recovery, since parachute inflation is a bigger "
                    "number but a recovery-loads one; steady measures it over the whole "
                    "ascent, which has no recovery to exclude."),
    OutputSpec("specific_impulse", "Specific impulse", "time", ("overall",),
               help="Total impulse over g0 times all propellant consumed, oxidizer and "
                    "fuel together. The whole-engine figure, comparable with published "
                    "hybrid numbers."),
    OutputSpec("average_cstar_actual", "Characteristic velocity (actual)", "velocity",
               ("overall",),
               help="Time-weighted mean c* the chamber actually delivered, over the part "
                    "of the burn where there is gas to speak of."),
    OutputSpec("average_cstar_theoretical", "Characteristic velocity (theoretical)",
               "velocity", ("overall",),
               help="The same average divided by the c* efficiency: what CEA predicts for "
                    "this propellant at these conditions."),
    OutputSpec("pad_thrust_to_weight", "Pad thrust-to-weight", DIMENSIONLESS, ("overall",),
               help="Peak thrust over wet weight at ignition. Below about 5 the "
                    "rocket leaves the rail too slowly to stay stable."),

    # ---- chamber ------------------------------------------------------
    OutputSpec("peak_chamber_pressure", "Peak chamber pressure", "pressure",
               ("overall", "phase"), aggregate="max",
               legacy=("peak_chamber_pressure_Pa",),
               help="Highest chamber stagnation pressure."),
    OutputSpec("peak_chamber_temperature", "Peak chamber temperature", "temperature",
               ("overall", "phase"), aggregate="max",
               legacy=("peak_chamber_temperature_K",),
               help="Highest chamber stagnation temperature, after c* efficiency."),
    OutputSpec("average_OF_ratio", "Average O/F ratio", DIMENSIONLESS,
               ("overall", "phase"),
               help="Mean oxidizer-to-fuel mass ratio over the burn."),

    # ---- flight -------------------------------------------------------
    OutputSpec("apogee_agl", "Apogee (AGL)", "distance", ("overall",),
               legacy=("apogee_m_agl",),
               help="Peak altitude above the launch site."),
    OutputSpec("apogee_asl", "Apogee (ASL)", "distance", ("overall",),
               legacy=("apogee_m_asl",),
               help="Peak altitude above sea level."),
    OutputSpec("landing_downrange", "Horizontal distance at landing", "distance", ("overall",),
               help="Downrange distance from the launch site at the last timestep."),
    OutputSpec("peak_velocity", "Peak velocity", "velocity", ("phase", "steady"),
               aggregate="max", legacy=("peak_velocity_ms",),
               help="Highest speed reached. Per phase in unsteady; over the whole ascent "
                    "in steady."),
    OutputSpec("terminal_velocity", "Terminal velocity", "velocity", ("phase",),
               legacy=("terminal_velocity_ms",),
               help="Speed at the end of this phase."),

    # ---- propellant ---------------------------------------------------
    OutputSpec("ox_mass_available", "Oxidizer loaded", "mass", ("overall",),
               legacy=("ox_mass_available_kg",),
               help="Oxidizer in the tank at ignition."),
    OutputSpec("ox_mass_consumed", "Oxidizer used", "mass", ("overall", "phase"),
               aggregate="sum", legacy=("ox_mass_consumed_kg",),
               help="Oxidizer actually burnt."),
    OutputSpec("ox_mass_remaining", "Oxidizer left", "mass", ("overall",),
               legacy=("ox_mass_remaining_kg",),
               help="Oxidizer still in the tank at burnout. A large figure means "
                    "the engine cut off early."),
    OutputSpec("fuel_mass_available", "Fuel loaded", "mass", ("overall",),
               legacy=("fuel_mass_available_kg",),
               help="Solid fuel in the grain at ignition."),
    OutputSpec("fuel_mass_consumed", "Fuel used", "mass", ("overall", "phase"),
               aggregate="sum", legacy=("fuel_mass_consumed_kg",),
               help="Solid fuel actually burnt."),
    OutputSpec("fuel_mass_remaining", "Fuel left", "mass", ("overall",),
               legacy=("fuel_mass_remaining_kg",),
               help="Unburnt grain at burnout. A large figure means the grain was "
                    "oversized for the oxidizer load."),
    OutputSpec("total_propellant_available", "Propellant loaded", "mass", ("overall",),
               legacy=("total_propellant_available_kg",),
               help="Oxidizer plus fuel at ignition."),
    OutputSpec("total_propellant_consumed", "Propellant used", "mass", ("overall",),
               legacy=("total_propellant_consumed_kg",),
               help="Oxidizer plus fuel actually burnt."),

    # ---- static: the rocket as the physics saw it ----------------------
    # Everything in results["static"]["rocket_inputs"], which is a mix of what the
    # user typed and what the loader and initializer derived from it.  Listed here
    # so the Hardware & Parameters tab gets its labels, units and radius-to-diameter
    # handling from the same place as everything else.
    #
    # The physics works in radii; people specify and read diameters.  display_scale
    # of 2.0 is that conversion, and it is the only arithmetic the results page is
    # allowed to do.

    # CV1 tank
    OutputSpec("tank_internal_radius", "Internal diameter", "length", ("static",),
               display_scale=2.0),
    OutputSpec("tank_internal_length", "End-to-end internal length", "length", ("static",),
               help="Given directly, or solved for from the ullage fraction."),
    OutputSpec("tank_volume", "Volume", "volume", ("static",)),
    OutputSpec("tank_temperature", "Initial temperature", "temperature", ("static",)),
    OutputSpec("tank_oxidizer_mass", "Oxidizer mass", "mass", ("static",)),
    OutputSpec("tank_ullage_fraction", "Ullage fraction", DIMENSIONLESS, ("static",),
               help="Vapour volume over LIQUID volume, not over total. 0.10 is a tank "
                    "one eleventh gas by volume."),
    OutputSpec("tank_liquid_volume", "Liquid volume", "volume", ("static",)),
    OutputSpec("tank_ullage_volume", "Ullage volume", "volume", ("static",)),

    # CV2 valve
    OutputSpec("valve_time_constant", "Time constant", "time", ("static",)),
    OutputSpec("sigmoid_half_time", "Sigmoid half time", "time", ("static",)),
    OutputSpec("sigmoid_steepness", "Sigmoid steepness", DIMENSIONLESS, ("static",)),

    # CV3 injector
    OutputSpec("injector_discharge_coefficient", "Discharge coefficient", DIMENSIONLESS, ("static",)),
    OutputSpec("injector_number_of_holes", "Number of holes", DIMENSIONLESS, ("static",)),
    OutputSpec("injector_hole_radius", "Hole diameter", "injector_length", ("static",), display_scale=2.0),
    OutputSpec("injector_hole_area", "Hole area", "injector_area", ("static",)),
    OutputSpec("feed_pressure_loss", "Feed pressure loss", "pressure", ("static",)),

    # CV4 chamber
    OutputSpec("chamber_fuel_external_radius", "External diameter", "length", ("static",),
               display_scale=2.0),
    OutputSpec("chamber_fuel_internal_radius", "Initial internal diameter", "length", ("static",),
               display_scale=2.0,
               help="Given directly, or derived from the fuel mass at initialization."),
    OutputSpec("chamber_fuel_length", "Length", "length", ("static",)),
    OutputSpec("chamber_fuel_mass", "Mass", "mass", ("static",)),
    OutputSpec("chamber_fuel_density", "Density", "density", ("static",)),
    OutputSpec("pre_chamber_radius", "Diameter", "length", ("static",), display_scale=2.0),
    OutputSpec("pre_chamber_length", "Length", "length", ("static",)),
    OutputSpec("pre_chamber_volume", "Volume", "volume", ("static",)),
    OutputSpec("post_chamber_radius", "Diameter", "length", ("static",), display_scale=2.0),
    OutputSpec("post_chamber_length", "Length", "length", ("static",)),
    OutputSpec("post_chamber_volume", "Volume", "volume", ("static",)),
    OutputSpec("chamber_regression_rate_scaling_constant", "Regression rate scaling constant",
               DIMENSIONLESS, ("static",),
               help="The 'a' in r_dot = a*G_ox^n. Stored in SI; see the regression "
                    "coefficient appendix in the developer manual."),
    OutputSpec("chamber_regression_rate_exponent", "Regression rate exponent",
               DIMENSIONLESS, ("static",)),
    OutputSpec("chamber_cstar_efficiency", "Combustion efficiency (c*)",
               DIMENSIONLESS, ("static",),
               help="Fraction of the theoretical characteristic velocity the chamber "
                    "delivers."),

    # CV5 nozzle
    # Steady sizes its nozzle rather than being given one, so it writes these
    # same four numbers as results. Same meaning, same units, one spec.
    OutputSpec("nozzle_throat_radius", "Throat diameter", "length", ("static", "steady"),
               display_scale=2.0),
    OutputSpec("nozzle_exit_radius", "Exit diameter", "length", ("static", "steady"),
               display_scale=2.0),
    OutputSpec("nozzle_throat_area", "Throat area", "area", ("static", "steady")),
    OutputSpec("nozzle_exit_area", "Exit area", "area", ("static", "steady")),
    OutputSpec("nozzle_expansion_ratio", "Expansion ratio", DIMENSIONLESS,
               ("static", "steady"),
               help="Exit area over throat area."),

    # CV6 trajectory
    OutputSpec("rocket_dry_mass", "Dry mass", "mass", ("static",)),
    OutputSpec("rocket_outer_radius", "Outer diameter", "length", ("static",), display_scale=2.0),
    OutputSpec("rocket_frontal_area", "Frontal area", "area", ("static",)),
    OutputSpec("rocket_drag_coefficient", "Drag coefficient", DIMENSIONLESS, ("static",)),
    OutputSpec("rocket_launch_angle", "Launch angle", "angle", ("static",)),
    OutputSpec("launch_site_altitude_asl", "Launch altitude ASL", "distance", ("static",)),
    OutputSpec("drogue_parachute_radius", "Drogue diameter", "canopy_length", ("static",), display_scale=2.0),
    OutputSpec("drogue_parachute_drag_coefficient", "Drogue drag coefficient", DIMENSIONLESS, ("static",)),
    OutputSpec("drogue_parachute_frontal_area", "Drogue frontal area", "canopy_area", ("static",)),
    OutputSpec("main_parachute_radius", "Main diameter", "canopy_length", ("static",), display_scale=2.0),
    OutputSpec("main_parachute_drag_coefficient", "Main drag coefficient", DIMENSIONLESS, ("static",)),
    OutputSpec("main_parachute_frontal_area", "Main frontal area", "canopy_area", ("static",)),
    OutputSpec("main_parachute_deployment_altitude_agl", "Main deployment altitude AGL",
               "distance", ("static",)),

    # solver knobs that ride along in the same block
    OutputSpec("ignition_delta_p", "Ignition pressure rise", "pressure", ("static",)),
    OutputSpec("k_amb", "Ambient pressure factor", DIMENSIONLESS, ("static",)),
    OutputSpec("min_thrust_to_weight", "Engine cutoff thrust-to-weight", DIMENSIONLESS, ("static",)),

    # =====================================================================
    # Steady
    # =====================================================================
    #
    # Steady keeps its own names.  Isp is not specific_impulse, thrust is not
    # peak_thrust, average_oxidizer_to_fuel_ratio is not average_OF_ratio: the
    # two programs were written years apart and renaming either side would
    # break every results file and config already written.  Where a name IS
    # shared, above, the spec is shared with it.
    #
    # Three scopes, because a steady file has three blocks and the coverage
    # check has to know which is which: "steady" is rocket_parameters, what the
    # run computed; "steady_input" is rocket_inputs, what it was given;
    # "steady_setting" is simulation_settings plus metadata.

    # ---- steady: the burn ----------------------------------------------
    OutputSpec("initial_internal_fuel_radius", "Initial internal fuel diameter", "length",
               ("steady",), display_scale=2.0,
               help="Port diameter at ignition. A hotfire is given it; a convergence run "
                    "solves for it, and it is that run's real answer."),
    OutputSpec("fuel_mass", "Fuel mass", "mass", ("steady",),
               help="Mass of the fuel grain. The steady model burns all of it, so this is "
                    "both what is loaded and what is consumed."),
    OutputSpec("oxidizer_mass", "Oxidizer mass", "mass", ("steady",),
               help="Oxidizer flow rate times burn time. There is no tank in the steady "
                    "model, so this is the mass the run needs, not a mass it was given."),
    OutputSpec("average_oxidizer_to_fuel_ratio", "Average O/F ratio", DIMENSIONLESS,
               ("steady",),
               help="Mean oxidizer-to-fuel mass ratio over the burn."),
    OutputSpec("average_fuel_mass_flow_rate", "Average fuel mass flow rate", "mass_flow",
               ("steady",)),
    OutputSpec("total_propellant_mass_flow_rate", "Total propellant mass flow rate",
               "mass_flow", ("steady",),
               help="Oxidizer plus fuel through the nozzle."),

    # ---- steady: the chamber -------------------------------------------
    OutputSpec("chamber_temperature", "Chamber stagnation temperature", "temperature",
               ("steady",),
               help="Flame temperature PROPEP returns for this propellant at this "
                    "chamber pressure."),
    OutputSpec("chamber_gas_molar_weight", "Chamber gas molar weight", "molar_mass",
               ("steady",)),
    OutputSpec("heat_capacity_ratio", "Heat capacity ratio", DIMENSIONLESS, ("steady",),
               help="Gamma for the combustion gas, from PROPEP."),

    # ---- steady: the nozzle --------------------------------------------
    OutputSpec("nozzle_gas_exit_pressure", "Exit pressure", "pressure", ("steady",),
               help="NOT calculated. Fixed at 0.959 atm in prop_calculations.py, because "
                    "tuning it there matched test data better than assuming a perfectly "
                    "expanded nozzle."),
    OutputSpec("nozzle_gas_exit_mach_number", "Exit Mach number", DIMENSIONLESS, ("steady",)),
    OutputSpec("nozzle_gas_exit_temperature", "Exit temperature", "temperature", ("steady",)),
    OutputSpec("nozzle_gas_exit_velocity", "Exit velocity", "velocity", ("steady",)),

    # ---- steady: performance -------------------------------------------
    OutputSpec("thrust", "Thrust", "force", ("steady",),
               help="Constant through the burn: that is what makes the model steady."),
    OutputSpec("Isp", "Specific impulse", "time", ("steady",),
               help="Thrust over total propellant weight flow at sea level."),
    OutputSpec("wet_mass", "Wet mass", "mass", ("steady",),
               help="Dry mass plus fuel plus oxidizer at ignition. Not computed for a "
                    "hotfire, which never leaves the ground."),
    OutputSpec("thrust_to_weight_ratio", "Pad thrust-to-weight", DIMENSIONLESS, ("steady",),
               help="Thrust over wet weight at ignition. Below about 5 the rocket leaves "
                    "the rail too slowly to stay stable."),

    # ---- steady: the flight --------------------------------------------
    OutputSpec("reached_apogee_agl", "Apogee (AGL)", "distance", ("steady",),
               help="Peak altitude above the launch pad. This is what the target apogee "
                    "means and what the convergence solver aims at."),
    OutputSpec("reached_apogee", "Apogee (ASL)", "distance", ("steady",),
               help="The same apogee above sea level. Runs written before the AGL key "
                    "existed have only this one, and their target was read against it."),
    OutputSpec("target_apogee_reached", "Target apogee reached", TEXT, ("steady",),
               help="False when the solver ran out of fuel grain before reaching the "
                    "target. The run still completes and its numbers are real."),

    # ---- steady inputs --------------------------------------------------
    OutputSpec("oxidizer_mass_flow_rate", "Oxidizer mass flow rate", "mass_flow",
               ("steady_input",),
               help="Held constant for the whole burn."),
    OutputSpec("chamber_pressure", "Chamber pressure", "pressure", ("steady_input",),
               help="Held constant for the whole burn, and the number the nozzle is "
                    "sized around."),
    OutputSpec("fuel_external_radius", "External diameter", "length", ("steady_input",),
               display_scale=2.0),
    OutputSpec("fuel_length", "Length", "length", ("steady_input",)),
    OutputSpec("fuel_grain_density", "Density", "density", ("steady_input",)),
    OutputSpec("regression_rate_scaling_coefficient", "Regression rate scaling constant",
               DIMENSIONLESS, ("steady_input",),
               help="The 'a' in r_dot = a*G_ox^n. Stored in SI; its units depend on n, "
                    "so see the regression coefficient appendix in the developer manual."),
    OutputSpec("regression_rate_exponent", "Regression rate exponent", DIMENSIONLESS,
               ("steady_input",)),
    OutputSpec("augmented_regression_rate_exponent", "Augmented regression rate exponent",
               DIMENSIONLESS, ("steady_input",),
               help="2n+1. Derived at initialization, not typed in."),
    OutputSpec("liquid_oxidizer_type", "Oxidizer", TEXT, ("steady_input",)),
    OutputSpec("solid_fuel_type", "Fuel", TEXT, ("steady_input",)),
    OutputSpec("dry_mass", "Dry mass", "mass", ("steady_input",)),
    OutputSpec("rocket_external_radius", "Outer diameter", "length", ("steady_input",),
               display_scale=2.0),
    OutputSpec("drag_coefficient", "Drag coefficient", DIMENSIONLESS, ("steady_input",)),
    OutputSpec("target_apogee", "Target apogee (AGL)", "distance", ("steady_input",),
               help="Measured above the launch pad, not above sea level."),
    OutputSpec("launch_site_altitude", "Launch site altitude ASL", "distance",
               ("steady_input",),
               help="Sets the air density and the backpressure the flight starts at."),
    OutputSpec("launch_angle", "Launch angle", "angle", ("steady_input",),
               help="From vertical."),

    # ---- steady settings and metadata -----------------------------------
    OutputSpec("simulation_type", "Simulation type", TEXT, ("steady_setting",)),
    OutputSpec("output_units", "Stored in", TEXT, ("steady_setting",),
               help="The unit system this file's numbers are written in. Not a display "
                    "choice: it is what the numbers on disk mean."),
    OutputSpec("number_of_timesteps", "Timesteps", DIMENSIONLESS, ("steady_setting",),
               help="Ascent samples per burn time. Only the trajectory uses it."),
    OutputSpec("tolerated_apogee_difference", "Apogee tolerance", "distance",
               ("steady_setting",),
               help="How close to the target counts as converged."),
    OutputSpec("smallest_allowed_inner_fuel_radius", "Smallest allowed internal fuel diameter",
               "length", ("steady_setting",), display_scale=2.0,
               help="The floor the convergence search stops at. Hitting it is what makes "
                    "a run report that the target cannot be reached."),
    OutputSpec("save_output_data", "Save output data", TEXT, ("steady_setting",)),
    OutputSpec("save_simulation_data", "Save simulation data", TEXT, ("steady_setting",)),
    OutputSpec("show_graphs", "Show graphs", TEXT, ("steady_setting",)),
    OutputSpec("simulation_name", "Name", TEXT, ("steady_setting",)),
    OutputSpec("simulation_description", "Description", TEXT, ("steady_setting",)),
    OutputSpec("expected_output", "Expected output", TEXT, ("steady_setting",)),

    # ---- internal -----------------------------------------------------
    # launch_metrics() feeds the launch-capability warning and never reaches a
    # results file, but it shares these names so the warning text and the page
    # agree on what things are called.
    OutputSpec("initial_mass", "Wet mass", "mass", ("internal",),
               legacy=("initial_mass_kg",),
               help="Dry mass plus all propellant at ignition."),
    OutputSpec("peak_thrust_to_weight", "Peak thrust-to-weight", DIMENSIONLESS,
               ("internal",)),
    OutputSpec("altitude_gain", "Altitude gained", "distance", ("internal",)),
    OutputSpec("reached_operating_point", "Reached operating point", TEXT, ("internal",)),
)


# =============================================================================
# Lookup
# =============================================================================

_BY_KEY: dict[str, OutputSpec] = {}
for _spec in _SPECS:
    if _spec.key in _BY_KEY:
        raise RuntimeError(f"Duplicate output key: {_spec.key!r}")
    _BY_KEY[_spec.key] = _spec

# every legacy spelling, mapped to the spec that replaced it
_BY_LEGACY: dict[str, OutputSpec] = {}
for _spec in _SPECS:
    for _old in _spec.legacy:
        if _old in _BY_LEGACY:
            raise RuntimeError(f"Legacy key {_old!r} claimed twice")
        _BY_LEGACY[_old] = _spec


def has(key: str) -> bool:
    """True if this key is a known output, under either its new or old name."""
    return key in _BY_KEY or key in _BY_LEGACY


def get(key: str) -> OutputSpec:
    """The spec for a key, accepting either the current or a legacy name."""
    spec = _BY_KEY.get(key) or _BY_LEGACY.get(key)
    if spec is None:
        raise KeyError(f"Unknown output key: {key!r}")
    return spec


def find(key: str) -> Optional[OutputSpec]:
    """get(), but None instead of raising.  For code walking arbitrary dicts."""
    return _BY_KEY.get(key) or _BY_LEGACY.get(key)


def canonical(key: str) -> str:
    """The current name for a key.  Unknown keys pass through unchanged."""
    spec = find(key)
    return spec.key if spec else key


def describe(key: str) -> Optional[tuple[str, Optional[str]]]:
    """(label, SI unit) for a key, or None if this module doesn't know it."""
    spec = find(key)
    return None if spec is None else (spec.label, spec.si_unit)


def value_of(block: Any, key: str, default: Any = None) -> Any:
    """Read `key` out of a results block, whatever spelling the file used.

    The one function every display surface should call.  Tries the current
    name, then each legacy name, so a run saved before the rename reads exactly
    like one saved after it.

        value_of(overall, "peak_thrust")    # finds peak_thrust_N in an old file
    """
    if not isinstance(block, dict):
        return default
    if key in block:
        return block[key]
    spec = find(key)
    if spec is not None:
        if spec.key in block:
            return block[spec.key]
        for old in spec.legacy:
            if old in block:
                return block[old]
    return default


def key_in(block: Any, key: str) -> Optional[str]:
    """Which spelling of `key` this particular block actually uses, or None.

    value_of() is enough when you only want the number.  This is for callers
    that also need the key itself, usually to mark it as already rendered.
    """
    if not isinstance(block, dict):
        return None
    if key in block:
        return key
    spec = find(key)
    if spec is not None:
        if spec.key in block:
            return spec.key
        for old in spec.legacy:
            if old in block:
                return old
    return None


def in_scope(scope: str) -> tuple[OutputSpec, ...]:
    """Every spec that appears in a given block: overall, phase, metadata, ..."""
    return tuple(s for s in _SPECS if scope in s.scopes)


def all_specs() -> tuple[OutputSpec, ...]:
    return _SPECS


def aggregate_phases(by_phase: dict, key: str) -> Any:
    """Combine one row of the per-phase table into a single totals figure.

    Returns None when no total is meaningful for that row, which the table
    renders as a dash rather than an invented number.  Averages are the case
    that matters: the mean of three phase averages is not the mean over the
    burn, so those deliberately have no aggregate rule.
    """
    spec = find(key)
    if spec is None or spec.aggregate is None:
        return None
    values = [value_of(entry, key) for entry in (by_phase or {}).values()]
    numbers = [v for v in values
               if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v]
    if not numbers:
        return None
    if spec.aggregate == "sum":
        return sum(numbers)
    if spec.aggregate == "max":
        return max(numbers)
    if spec.aggregate == "min":
        return min(numbers)
    return None


# =============================================================================
# Consistency
# =============================================================================

def check_registry_covers_results(results: Any) -> list[str]:
    """Every key a results file holds must have a spec, and vice versa.

    The sibling of field_registry.check_registry_covers_schema(), and the thing
    that stops this module drifting away from objects.py.  Without it, adding a
    metric in the backend and forgetting the spec here shows up as an unlabelled
    row in the UI months later, which nobody reports as a bug.

    Returns a list of problems, empty when consistent.  Pass it a loaded
    sim_data.json.
    """
    problems: list[str] = []

    blocks = [
        ("metadata", results.get("metadata") or {}, "metadata"),
        ("performance.overall", (results.get("performance") or {}).get("overall") or {}, "overall"),
    ]
    for name, block, scope in blocks:
        for key in block:
            if not has(key):
                problems.append(f"{name}: {key!r} is in the file but has no OutputSpec")
        present = {canonical(k) for k in block}
        for spec in in_scope(scope):
            if spec.key not in present:
                problems.append(f"{name}: {spec.key!r} has a spec but the file never writes it")

    by_phase = (results.get("performance") or {}).get("by_phase") or {}
    phase_keys: set[str] = set()
    for entry in by_phase.values():
        if isinstance(entry, dict):
            phase_keys |= set(entry)
    if by_phase:
        for key in phase_keys:
            if not has(key):
                problems.append(f"performance.by_phase: {key!r} is in the file but has no OutputSpec")
        present = {canonical(k) for k in phase_keys}
        for spec in in_scope("phase"):
            if spec.key not in present:
                problems.append(f"performance.by_phase: {spec.key!r} has a spec but the file never writes it")

    static = (results.get("static") or {}).get("rocket_inputs") or {}
    for key, value in static.items():
        if key in ("CV_models", "epsilons"):
            continue            # nested structures, rendered by their own panels
        if not has(key):
            problems.append(f"static.rocket_inputs: {key!r} is in the file but has no OutputSpec")

    for event in (results.get("event_log") or [])[:1]:
        if isinstance(event, dict):
            for key in event:
                if not has(key):
                    problems.append(f"event_log: {key!r} is in the file but has no OutputSpec")

    # A spec whose category is not a real unit category would only surface when
    # something tried to convert it, which is far too late.
    for spec in _SPECS:
        if spec.category in (DIMENSIONLESS, TEXT):
            continue
        if spec.category not in vc.SI_UNITS:
            problems.append(f"{spec.key!r}: category {spec.category!r} is not in variable_conversions")
    for spec in _SPECS:
        if spec.aggregate not in (None, "sum", "max", "min"):
            problems.append(f"{spec.key!r}: unknown aggregate rule {spec.aggregate!r}")

    return problems


def check_registry_covers_steady_results(results: Any) -> list[str]:
    """The same guard for a steady run, in one direction only.

    One direction because steady writes different keys depending on the mode: a
    hotfire has no wet mass and no apogee, a parametric file has no top-level
    rocket_parameters at all. Demanding that every steady spec appear in every
    steady file would fail on a correct hotfire. What can be demanded is the
    other way round: nothing lands in a results file without a spec to label it.

    Returns a list of problems, empty when consistent. Pass it a loaded steady
    results JSON, of any mode.
    """
    problems: list[str] = []

    def check(name: str, block: Any) -> None:
        if not isinstance(block, dict):
            return
        for key in block:
            if not has(key):
                problems.append(f"{name}: {key!r} is in the file but has no OutputSpec")

    check("metadata", results.get("metadata"))
    check("simulation_settings", {k: v for k, v in (results.get("simulation_settings") or {}).items()
                                  if k != "parametric_study_settings"})
    check("rocket_inputs", results.get("rocket_inputs"))
    check("rocket_parameters", results.get("rocket_parameters"))

    sweep = results.get("parametric_results") or {}
    for index, entry in enumerate((sweep.get("rocket_parameters") or [])[:1]):
        check(f"parametric_results.rocket_parameters[{index}]", entry)
    for index, entry in enumerate((sweep.get("rocket_inputs") or [])[:1]):
        check(f"parametric_results.rocket_inputs[{index}]", entry)

    return problems

