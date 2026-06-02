"""
The main script for the steady model
Main dicts used:
- rocket_inputs: the user inputs to the simulation
- rocket_parameters: values that get calculated by the program
- simulation_settings: values that get used by the simulation engine itself
- constants_dict: natural constants used for physics equations

Simulation types: 
- hotfire: takes in a specific rocket preset, simulates the rocket burn
- fuel mass convergence: takes in the same values as hotfire except fuel mass or inner fuel radius, runs a hotfire+kinematics over and over, tweaking the fuel mass slightly untill the desired target apogee is reached
- parametric study: runs many fuel mass convergence simulations on a range of input values
- optimize values: runs a predefined paramtric study on fuel length, ox flow rate, and
"""

from pathlib import Path
import sys

project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.backend.steady.variable_initialization import initialize_natural_constants_dict, load_steady_config
from src.backend.steady.simulation_engine import simulate_hotfire, simulate_fuel_mass_convergence
from src.backend.steady.parametric_study import simulate_parametric_study, simulate_optimized_parametric_study


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
    
    # initialize parameters dict
    rocket_parameters = {}
    
    # determine simulation type & run
    if simulation_settings["simulation_type"].lower() == "hotfire": # calculates internal rocket dynamics without kinematics
        print("Running hotfire simulation")
        rocket_parameters = simulate_hotfire(rocket_inputs, rocket_parameters, simulation_settings, constants_dict)
        return rocket_inputs, rocket_parameters, simulation_settings
    
    elif simulation_settings["simulation_type"].lower() == "fuel_mass_convergence": 
        print("Running fuel mass convergence simulation")
        rocket_parameters = simulate_fuel_mass_convergence(rocket_inputs, rocket_parameters, simulation_settings, constants_dict)
        return rocket_inputs, rocket_parameters, simulation_settings
    
    elif simulation_settings["simulation_type"].lower() == "parametric_study": 
        print("Running parametric study")
        rocket_parameters = simulate_parametric_study(rocket_inputs, rocket_parameters, simulation_settings, constants_dict)
        return rocket_inputs, rocket_parameters, simulation_settings
    
    elif simulation_settings["simulation_type"].lower() == "optimize_values_for_unsteady": 
        print("Optimizing values for unsteady")
        rocket_parameters = simulate_optimized_parametric_study(rocket_inputs, rocket_parameters, simulation_settings, constants_dict)
        return rocket_inputs, rocket_parameters, simulation_settings
    
    else: 
        raise ValueError(f"Requested simulation type unavailable")

# prints all items of a dictionary in a nice way
def print_dict(input_dictionary):
    print()
    max_key_length = max(len(str(key)) for key in input_dictionary.keys())
    for key, value in input_dictionary.items():
        print(f"{key} {"." * (max_key_length - len(str(key)) + 2)} {value}")
    print()


#v= run_steady("steady_inputs_template.jsonc")
#print(v)