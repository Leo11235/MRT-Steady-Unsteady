"""
The main script for the steady model
"""

from pathlib import Path
import sys

project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.backend.steady.variable_initialization import initialize_natural_constants_dict, load_steady_config

def run_steady(rocket_inputs_filename: str, rocket_inputs_filepath: str | Path = Path(f"{project_root}") / "user_data" / "simulation_configs" / "steady"):
    """
    The main function for running the steady simulation.
    Takes a JSON file of rocket inputs, outputs another JSON with simulation performance
    """
    
    # load rocket inputs and simulation settings
    rocket_inputs_full_filepath = Path(f"{rocket_inputs_filepath}") / f"{rocket_inputs_filename}"
    print(f"Loading rocket inputs from {rocket_inputs_full_filepath}\n")
    rocket_inputs, simulation_settings = load_steady_config(rocket_inputs_full_filepath)
        
    # initialize constants dict
    constants_dict = initialize_natural_constants_dict()
    
    # determine simulation type & run
    if simulation_settings["simulation_type"].lower() == "hotfire": # calculates internal rocket dynamics without kinematics
        return
    elif simulation_settings["simulation_type"].lower() == "fuel_mass_convergence": 
        return
    elif simulation_settings["simulation_type"].lower() == "parametric_study": 
        return
    elif simulation_settings["simulation_type"].lower() == "optimize_values_for_unsteady": 
        return
    else: 
        raise ValueError(f"Requested simulation type unavailable")

# prints all items of a dictionary in a nice way
def print_dict(input_dictionary):
    print()
    max_key_length = max(len(str(key)) for key in input_dictionary.keys())
    for key, value in input_dictionary.items():
        print(f"{key} {"." * (max_key_length - len(str(key)) + 2)} {value}")
    print()


run_steady("steady_inputs_template.jsonc")
