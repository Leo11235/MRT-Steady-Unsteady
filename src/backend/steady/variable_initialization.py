import re, json
from pathlib import Path
from math import pi, sqrt
from src.common.variable_conversions import to_SI, pair_to_SI

_STEADY_DIR = Path(__file__).resolve().parent
_STATIC_DATA_DIR = _STEADY_DIR / "static_data"


# process inputs, modifies simulation_settings_dict and constants_dict, and outputs a rocket_inputs dict
def load_steady_config(input_file_path):
    # extract json from input file
    with open(input_file_path, 'r') as f:
        content = f.read()
    # remove comments
    content = re.sub(r'//.*?$|/\*.*?\*/', '', content, flags=re.MULTILINE | re.DOTALL)
    # parse the cleaned JSON string
    input_file = json.loads(content)

    # any simulation settings provided by the user override the default sim settings in static data
    simulation_settings_override = input_file.get('simulation_settings', {})
    rocket_inputs = input_file['rocket_inputs']
    metadata = input_file.get('metadata', {})
    
    # convert any UI-side diameter keys into the radius/area keys the rest of the steady physics expects 
    # clean and standardize rocket inputs
    rocket_inputs_cleaned = {}
    for key, val in rocket_inputs.items():
        # skip PROPEP str inputs
        if key == "liquid_oxidizer_type" or key == "solid_fuel_type":
            rocket_inputs_cleaned[key] = val
            continue
        # convert to SI
        newval = to_SI(val[0], val[1])
        # convert diameters to radii
        if "diameter" in key:
            p1, p2 = key.split("diameter")
            newkey = f"{p1}radius{p2}"
            newval = _diameter_to_radius(newval)
        else:
            newkey = key
        # add newkey, newval to dict
        rocket_inputs_cleaned[newkey] = newval
    
    # get default sim settings
    default_simulation_settings = initialize_default_simulation_settings()

    # override simulation settings and constants as needed
    simulation_settings = {
        **default_simulation_settings,
        **simulation_settings_override
    }

    validate_simulation_inputs(rocket_inputs_cleaned, simulation_settings)

    return rocket_inputs_cleaned, simulation_settings, metadata



def initialize_natural_constants_dict():
    """
    Returns a dict of natural constants used throughout the simulation.
    """
    # find and open file
    file = _STATIC_DATA_DIR / "natural_constants.jsonc"
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    # remove comments
    cleaned = re.sub(r'//.*', '', content)
    cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
    # parse cleaned file into dict
    constants_dict = json.loads(cleaned)
    return constants_dict

def initialize_default_simulation_settings():
    """
    Returns a dict of default simulation settings which can be overridden by the user
    """
    # find and open file
    file = _STATIC_DATA_DIR / "default_simulation_settings.jsonc"
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    # remove comments
    cleaned = re.sub(r'//.*', '', content)
    cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
    # parse cleaned file into dict
    sim_settings = json.loads(cleaned)
    return sim_settings


def validate_simulation_inputs(rocket_inputs, simulation_settings):
    """
    For a given simulation type ('fuel mass convergence', 'parametric study', 'hotfire', or 'optimize values for unsteady'), this function verifies that all inputs required for the program to function are present and valid. 
    """
    
    # initialize input schema dict
    file = _STATIC_DATA_DIR / "input_schema.jsonc"
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    cleaned = re.sub(r'//.*', '', content)
    cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
    input_schema = json.loads(cleaned)

    sim_type = simulation_settings.get("simulation_type")

    # check that the requested sim type actually exists
    _VALID_SIM_TYPES = ("hotfire", "fuel_mass_convergence", "parametric_study")
    if str(sim_type).lower() not in _VALID_SIM_TYPES:
        raise ValueError(f"Unknown simulation_type '{sim_type}'. Valid values are: {', '.join(_VALID_SIM_TYPES)}.")

    # any variable being swept by a parametric study is filled in per point by the solver, so it counts as satisfied for these checks even though it isn't a static value in rocket_inputs
    parametrized_keys: set = set()
    if sim_type == "parametric_study":
        ps = simulation_settings.get("parametric_study_settings") or {}
        if isinstance(ps, dict):
            parametrized_keys = set(ps.keys())

    # base requirements: needed for every simulation type
    for item in input_schema["base_requirements"]:
        if item in parametrized_keys:
            continue
        if item not in rocket_inputs:
            raise ValueError(f"Missing required rocket input: '{item}'")

    # kinematics: needed for everything except plain hotfire
    if sim_type in ("fuel_mass_convergence", "parametric_study", "optimize_values_for_unsteady"):
        for item in input_schema["kinematics_requirements"]:
            if item in parametrized_keys:
                continue
            if item not in rocket_inputs:
                raise ValueError(f"Missing required rocket input: '{item}'")

    # hotfire: exactly one of the alternates must be present, and if only one is given we derive the other so downstream physics has both to work with
    if sim_type == "hotfire":
        alternatives = input_schema["hotfire_requirements"][0]
        # values are already unpacked to bare floats here, so an unused alternate is present-but-None rather than absent
        has = [opt for opt in alternatives if rocket_inputs.get(opt) is not None]
        if len(has) == 0:
            raise ValueError(f"Hotfire requires one of: {alternatives}")
        if len(has) > 1:
            raise ValueError(f"Hotfire requires exactly one of: {alternatives}, got both")

        _validate_geometry(rocket_inputs)

        if rocket_inputs.get("fuel_mass") is None:
            rocket_inputs["fuel_mass"] = _calculate_fuel_mass(rocket_inputs)
        else:
            rocket_inputs["initial_internal_fuel_radius"] = \
                _calculate_initial_radius(rocket_inputs)
    
    # parametric: sweep definition has to describe a real range
    if sim_type == "parametric_study":
        _validate_parametric_settings(simulation_settings)


# helpers
def _calculate_initial_radius(rocket_inputs):
    Lf = rocket_inputs["fuel_length"]
    Re = rocket_inputs["fuel_external_radius"]
    p = rocket_inputs["fuel_grain_density"]
    Mf = rocket_inputs["fuel_mass"]
    return sqrt(Re**2 - Mf / (pi * Lf * p))

def _calculate_fuel_mass(rocket_inputs):
    Lf = rocket_inputs["fuel_length"]
    Ri0 = rocket_inputs["initial_internal_fuel_radius"]
    Re = rocket_inputs["fuel_external_radius"]
    p = rocket_inputs["fuel_grain_density"]
    return pi * Lf * (Re**2 - Ri0**2) * p

def _diameter_to_radius(var):
    if var is None:
        return None
    return var/2

# check that every swept variable defines a range the solver can walk
def _validate_parametric_settings(simulation_settings):
    settings = simulation_settings.get("parametric_study_settings")
    if not isinstance(settings, dict) or not settings:
        raise ValueError("Parametric study requires a 'parametric_study_settings' block with at least one variable to sweep")

    for var_name, bounds in settings.items():
        if not isinstance(bounds, dict):
            raise ValueError(f"Parametric variable '{var_name}' must be a block with low_end, high_end and step_size")

        for key in ("low_end", "high_end", "step_size"):
            if key not in bounds:
                raise ValueError(f"Parametric variable '{var_name}' is missing '{key}'")

        try:
            low = pair_to_SI(bounds["low_end"])
            high = pair_to_SI(bounds["high_end"])
            step = pair_to_SI(bounds["step_size"])
        except (ValueError, KeyError, TypeError) as e:
            raise ValueError(f"Parametric variable '{var_name}' has an unreadable bound: {e}") from e

        if None in (low, high, step):
            raise ValueError(f"Parametric variable '{var_name}' has an empty bound")
        
        if step <= 0:
            raise ValueError(
                f"Parametric variable '{var_name}' has step_size {step}; it must be greater than zero")
            
        if low > high:
            raise ValueError(
                f"Parametric variable '{var_name}' has low_end {low} above high_end {high}")

# reject grain geometry that cannot physically exist
def _validate_geometry(rocket_inputs):
    Re = rocket_inputs.get("fuel_external_radius")
    Ri = rocket_inputs.get("initial_internal_fuel_radius")
    Lf = rocket_inputs.get("fuel_length")
    rho = rocket_inputs.get("fuel_grain_density")
    Mf = rocket_inputs.get("fuel_mass")

    for name, value in (("fuel_external_radius", Re), ("fuel_length", Lf), ("fuel_grain_density", rho)):
        if isinstance(value, (int, float)) and value <= 0:
            raise ValueError(f"'{name}' must be greater than zero, got {value:g}.")

    if isinstance(Re, (int, float)) and isinstance(Ri, (int, float)) and Ri >= Re:
        raise ValueError(f"Initial port diameter ({Ri * 2:.4g} m) is at least as wide as the fuel grain itself ({Re * 2:.4g} m), so there is no fuel to burn.")

    if all(isinstance(v, (int, float)) for v in (Re, Lf, rho, Mf)):
        solid_mass = pi * Lf * Re**2 * rho
        if Mf > solid_mass:
            raise ValueError(f"Fuel mass ({Mf:.4g} kg) exceeds a completely solid grain of these dimensions ({solid_mass:.4g} kg). At {rho:g} kg/m3 that mass needs {Mf / rho * 1000:.2f} L, and the grain envelope only holds {solid_mass / rho * 1000:.2f} L. Reduce the fuel mass, lengthen the grain, or widen it.")