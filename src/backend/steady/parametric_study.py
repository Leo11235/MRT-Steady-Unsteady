import itertools
import numpy as np

from src.backend.steady import simulation_engine


def simulate_parametric_study(rocket_inputs, rocket_parameters, simulation_settings, constants_dict):
    param_settings = simulation_settings.get("parametric_study_settings", {})
    if not param_settings:
        print("Warning: No parametric_study_settings found in simulation config.")
        return {}
    
    # generate ranges for each variable
    var_ranges = {}
    for var_name, var_values in param_settings.items():
        low = var_values.get("low_end", 0.0)
        high = var_values.get("high_end", 0.0)
        step = var_values.get("step_size", 1.0)
        
        # add a tiny epsilon
        var_ranges[var_name] = np.arange(low, high + (step * 0.01), step).tolist()
    
    variables = list(var_ranges.keys())
    combinations = list(itertools.product(*var_ranges.values()))
    total_iterations = len(combinations)
    
    print(f"Running parametric study on {len(variables)} variables.")
    print(f"Total combinations to simulate: {total_iterations}\n")
    
    # initialize results dict
    param_results_dict = {
        "variable_ranges": var_ranges, 
        "combinations": combinations,
        "rocket_inputs": [], 
        "rocket_parameters": [], 
        "flight_data": []
    }
    
    # execution loop
    for i, combination in enumerate(combinations, start=1):
        # isolate state for this iteration
        current_rocket_inputs = rocket_inputs.copy()
        current_rocket_parameters = rocket_parameters.copy()
        
        # parametric variables
        for var_name, val in zip(variables, combination):
            current_rocket_inputs[var_name] = val
        
        combination_str = ", ".join([f"{var}: {val:.4f}" for var, val in zip(variables, combination)])
        print(f"[{i}/{total_iterations}] Testing -> {combination_str}")
        
        # run the convergence simulation
        rocket_parameters, flight_dict = simulation_engine.simulate_fuel_mass_convergence(current_rocket_inputs, current_rocket_parameters, simulation_settings, constants_dict)
        
        # save results
        param_results_dict["rocket_inputs"].append(current_rocket_inputs)
        param_results_dict["rocket_parameters"].append(rocket_parameters)
        param_results_dict["flight_data"].append(flight_dict)

    print("\nParametric study complete.")
    return param_results_dict
