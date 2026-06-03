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
from datetime import datetime
import sys, json

project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.backend.steady.variable_initialization import initialize_natural_constants_dict, load_steady_config
from src.backend.steady.simulation_engine import simulate_hotfire, simulate_fuel_mass_convergence
from src.backend.steady.parametric_study import simulate_parametric_study

import src.backend.variable_conversions as convert


def run_steady(rocket_inputs_filename: str, 
               rocket_inputs_filepath: str | Path = Path(f"{project_root}") / "user_data" / "simulation_configs" / "steady",
               output_dir_filepath: str | Path = Path(f"{project_root}") / "user_data" / "simulation_results" / "steady"
               ):
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
    
    # initialize dicts
    rocket_parameters = {}
    flight_dict = None
    param_results_dict = None
    
    # get simulation type
    sim_type = simulation_settings["simulation_type"].lower()
    
    # determine simulation type & run
    if sim_type == "hotfire": # calculates internal rocket dynamics without kinematics
        print("Running hotfire simulation")
        rocket_parameters = simulate_hotfire(rocket_inputs, rocket_parameters, simulation_settings, constants_dict)        
    elif sim_type == "fuel_mass_convergence": 
        print("Running fuel mass convergence simulation")
        rocket_parameters, flight_dict = simulate_fuel_mass_convergence(rocket_inputs, rocket_parameters, simulation_settings, constants_dict)
    elif sim_type == "parametric_study": 
        print("Running parametric study")
        param_results_dict = simulate_parametric_study(rocket_inputs, rocket_parameters, simulation_settings, constants_dict)    
    else: 
        raise ValueError(f"Requested simulation type unavailable")
    
    # convert values. At this point, multiple dicts may or may not exist. We check/convert values in each one
    if simulation_settings.get("output_units") == "MRT":
        # convert the various dicts if needed
        if rocket_inputs is not None:
            convert_rocket_inputs_SI_to_MRT(rocket_inputs)
        if rocket_parameters is not None:
            convert_rocket_parameters_SI_to_MRT(rocket_parameters)
        if flight_dict is not None:
            convert_flight_dict_SI_to_MRT(flight_dict)
        if simulation_settings is not None:
            convert_simulation_settings_SI_to_MRT(simulation_settings)
        if param_results_dict is not None:
            convert_param_results_dict_SI_to_MRT(param_results_dict)
    
    # assemble JSON export data
    export_data = {
        "rocket_inputs": rocket_inputs,
        "simulation_settings": simulation_settings
    }
    if sim_type == "hotfire":
        export_data["rocket_parameters"] = rocket_parameters
    elif sim_type == "fuel_mass_convergence":
        export_data["rocket_parameters"] = rocket_parameters
        export_data["flight_dict"] = flight_dict
    elif sim_type == "parametric_study":
        export_data["parametric_results"] = param_results_dict
    
    # setup output directory
    output_dir_filepath.mkdir(parents=True, exist_ok=True)
    sim_filepath = output_dir_filepath / f"{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.json"
    
    # write to JSON
    with open(sim_filepath, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=4)
        
    print(f"\nSimulation data exported to:\n -> {sim_filepath}")

# HELPERS
# prints all items of a dictionary in a nice way
def print_dict(input_dictionary):
    print()
    max_key_length = max(len(str(key)) for key in input_dictionary.keys())
    for key, value in input_dictionary.items():
        print(f"{key} {"." * (max_key_length - len(str(key)) + 2)} {value}")
    print()


# various conversion functions to go from all SI values to MRT unit system (cursed mishmash of SI and IMP that Canadian engineers apparently like)
def convert_rocket_inputs_SI_to_MRT(rocket_inputs):
    if rocket_inputs.get("target_apogee"): rocket_inputs["target_apogee"] = convert.m_to_ft(rocket_inputs["target_apogee"])
    if rocket_inputs.get("launch_site_altitude"): rocket_inputs["launch_site_altitude"] = convert.m_to_ft(rocket_inputs["launch_site_altitude"])
    if rocket_inputs.get("fuel_external_radius"): rocket_inputs["fuel_external_radius"] = convert.m_to_in(rocket_inputs["fuel_external_radius"])
    if rocket_inputs.get("fuel_length"): rocket_inputs["fuel_length"] = convert.m_to_in(rocket_inputs["fuel_length"])
    if rocket_inputs.get("chamber_pressure"): rocket_inputs["chamber_pressure"] = convert.Pa_to_psi(rocket_inputs["chamber_pressure"])
    if rocket_inputs.get("rocket_external_radius"): rocket_inputs["rocket_external_radius"] = convert.m_to_in(rocket_inputs["rocket_external_radius"])

def convert_rocket_parameters_SI_to_MRT(rocket_parameters):
    if rocket_parameters.get("initial_internal_fuel_radius"): rocket_parameters["initial_internal_fuel_radius"] = convert.m_to_in(rocket_parameters["initial_internal_fuel_radius"])
    if rocket_parameters.get("nozzle_throat_area"): rocket_parameters["nozzle_throat_area"] = convert.m2_to_in2(rocket_parameters["nozzle_throat_area"])
    if rocket_parameters.get("nozzle_throat_radius"): rocket_parameters["nozzle_throat_radius"] = convert.m_to_in(rocket_parameters["nozzle_throat_radius"])
    if rocket_parameters.get("nozzle_gas_exit_pressure"): rocket_parameters["nozzle_gas_exit_pressure"] = convert.Pa_to_psi(rocket_parameters["nozzle_gas_exit_pressure"])
    if rocket_parameters.get("nozzle_exit_area"): rocket_parameters["nozzle_exit_area"] = convert.m2_to_in2(rocket_parameters["nozzle_exit_area"])
    if rocket_parameters.get("nozzle_exit_radius"): rocket_parameters["nozzle_exit_radius"] = convert.m_to_in(rocket_parameters["nozzle_exit_radius"])
    if rocket_parameters.get("nozzle_gas_exit_velocity"): rocket_parameters["nozzle_gas_exit_velocity"] = convert.ms_to_fts(rocket_parameters["nozzle_gas_exit_velocity"])
    if rocket_parameters.get("reached_apogee"): rocket_parameters["reached_apogee"] = convert.m_to_ft(rocket_parameters["reached_apogee"])

def convert_flight_dict_SI_to_MRT(flight_dict):
    if flight_dict.get("altitude"): flight_dict["altitude"] = [convert.m_to_ft(val) for val in flight_dict["altitude"]]
    if flight_dict.get("velocity"): flight_dict["velocity"] = [convert.ms_to_fts(val) for val in flight_dict["velocity"]]
    if flight_dict.get("acceleration"): flight_dict["acceleration"] = [convert.ms_to_fts(val) for val in flight_dict["acceleration"]]

def convert_simulation_settings_SI_to_MRT(simulation_settings):
    if simulation_settings.get("tolerated_apogee_difference"): simulation_settings["tolerated_apogee_difference"] = convert.m_to_ft(simulation_settings["tolerated_apogee_difference"])
    if simulation_settings.get("smallest_allowed_inner_fuel_radius"): simulation_settings["smallest_allowed_inner_fuel_radius"] = convert.m_to_in(simulation_settings["smallest_allowed_inner_fuel_radius"])

def convert_param_results_dict_SI_to_MRT(param_results_dict):
    for inputs in param_results_dict.get("rocket_inputs", []):
        convert_rocket_inputs_SI_to_MRT(inputs)
    for params in param_results_dict.get("rocket_parameters", []):
        convert_rocket_parameters_SI_to_MRT(params)
    for flight in param_results_dict.get("flight_data", []):
        convert_flight_dict_SI_to_MRT(flight)
