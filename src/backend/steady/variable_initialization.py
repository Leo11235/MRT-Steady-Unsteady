import re, json
from pathlib import Path

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
    
    # get default sim settings
    default_simulation_settings = initialize_default_simulation_settings()
        
    # override simulation settings and constants as needed 
    simulation_settings = {
        **default_simulation_settings,
        **simulation_settings_override
    }
    print(simulation_settings)
        
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
    # remove comments
    cleaned = re.sub(r'//.*', '', content)
    cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
    # parse cleaned file into dict
    input_schema = json.loads(cleaned)
    
    # first, validate base requirements needed for all simulation types
    for item in input_schema["base_requirements"]:    
        if item not in rocket_inputs:
            raise ValueError(f"Missing required rocket input: '{item}'")

    # validate items required for kinematics (all simulation types except hotfire)
    if simulation_settings.get("simulation_type") == ("fuel_mass_convergence" or "parametric_study" or "optimize_values_for_unsteady"):
        for item in input_schema["kinematics_requirements"]:    
            if item not in rocket_inputs:
                raise ValueError(f"Missing required rocket input: '{item}'")
    
    # validate additional parametric study inputs
    if simulation_settings.get("simulation_type") == ("parametric_study" or "optimize_values_for_unsteady"):
        # note, "optimize values for unsteady" is just a preset parametric study
        # for now, no controls. But this is where we could validate the parametric section of the simulation settings in the future
        pass