import re, json
from pathlib import Path
from math import pi

from src.backend.common.input_normalizer import normalize_steady_inputs

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

    # convert any UI-side diameter keys into the radius/area keys the rest of the steady physics expects 
    normalize_steady_inputs(rocket_inputs)

    # get default sim settings
    default_simulation_settings = initialize_default_simulation_settings()

    # override simulation settings and constants as needed
    simulation_settings = {
        **default_simulation_settings,
        **simulation_settings_override
    }

    validate_simulation_inputs(rocket_inputs, simulation_settings)

    return rocket_inputs, simulation_settings



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
    For a given simulation type ('fuel mass convergence', 'parametric study', 'hotfire', or 'optimize values for unsteady'),
    this function verifies that all inputs required for the program to function are present and valid. 
    """
    
    # initialize input schema dict
    file = _STATIC_DATA_DIR / "input_schema.jsonc"
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    cleaned = re.sub(r'//.*', '', content)
    cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
    input_schema = json.loads(cleaned)

    sim_type = simulation_settings.get("simulation_type")

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
    if sim_type in ("fuel_mass_convergence", "parametric_study",
                    "optimize_values_for_unsteady"):
        for item in input_schema["kinematics_requirements"]:
            if item in parametrized_keys:
                continue
            if item not in rocket_inputs:
                raise ValueError(f"Missing required rocket input: '{item}'")

    # hotfire: exactly one of the alternates must be present, and if only one is given we derive the other so downstream physics has both to work with
    if sim_type == "hotfire":
        alternatives = input_schema["hotfire_requirements"][0]
        has = [opt for opt in alternatives if opt in rocket_inputs]
        if len(has) == 0:
            raise ValueError(f"Hotfire requires one of: {alternatives}")

        if "fuel_mass" not in rocket_inputs:
            rocket_inputs["fuel_mass"] = calculate_fuel_mass(rocket_inputs)
        elif "initial_internal_fuel_radius" not in rocket_inputs:
            rocket_inputs["initial_internal_fuel_radius"] = \
                calculate_initial_radius(rocket_inputs)


# helpers
def calculate_initial_radius(rocket_inputs):
    Lf = rocket_inputs["fuel_length"]
    Re = rocket_inputs["fuel_external_radius"]
    p  = rocket_inputs["fuel_grain_density"]
    Mf = rocket_inputs["fuel_mass"]
    # Mf = π L (Re² − Ri²) p  →  Ri = sqrt(Re² − Mf / (π L p))
    return (Re**2 - Mf / (pi * Lf * p)) ** 0.5


def calculate_fuel_mass(rocket_inputs):
    Lf  = rocket_inputs["fuel_length"]
    Ri0 = rocket_inputs["initial_internal_fuel_radius"]
    Re  = rocket_inputs["fuel_external_radius"]
    p   = rocket_inputs["fuel_grain_density"]
    return pi * Lf * (Re**2 - Ri0**2) * p