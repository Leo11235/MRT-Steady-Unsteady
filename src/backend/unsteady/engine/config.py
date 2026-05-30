"""
Parses .jsonc inputs, merges them with default settings, and validates them
"""

import json5, os
from pathlib import Path

# load .jsonc inputs file
# takes a filepath str, returns a dict
def _load_jsonc(filepath: str) -> dict:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Configuration file not found: {filepath}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        return json5.load(f)

# Load simulation settings
# Overrides default simulation settings with any user-provided settings
def _merge_settings(default_settings: dict, user_settings: dict) -> dict:
    merged = default_settings.copy()
    
    for key, value in user_settings.items():
        # if both are dictionaries (ie nested settings), merge them recursively
        if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
            merged[key].update(value)
        else:
            # otherwise, just overwrite the default with the user's value
            merged[key] = value
            
    return merged


# validates user input for each control volume, returns full dictionary of inputs
def _validate_and_unpack_CVs(user_rocket_inputs: dict, schema: dict):
    validated_cv_args = {}
    expected_cvs = ["CV1_tank", "CV2_valve", "CV3_injector", "CV4_chamber", "CV5_nozzle", "CV6_trajectory"]

    for cv_name in expected_cvs:
        if cv_name not in user_rocket_inputs:
            raise KeyError(f"Missing section '{cv_name}' in user inputs.")
            
        cv_user_data = user_rocket_inputs[cv_name]
        selected_model = cv_user_data.get("model")
        
        if not selected_model:
            raise KeyError(f"'{cv_name}' is missing the 'model' key.")
            
        if cv_name not in schema or selected_model not in schema[cv_name]:
            raise ValueError(f"Unknown model '{selected_model}' for '{cv_name}'.")
            
        required_keys = schema[cv_name][selected_model]
        unpacked_args = {}
        
        for item in required_keys:
            if isinstance(item, list):
                # handle 'one or the other' inputs
                found = False
                for sub_key in item:
                    if sub_key in cv_user_data:
                        unpacked_args[sub_key] = cv_user_data[sub_key]
                        found = True
                        break # stop looking early if we find a valid option
                
                if not found:
                    raise KeyError(f"Missing input for {cv_name} ({selected_model} model). You must provide AT LEAST ONE of the following: {item}")
            else:
                # handle standard single required keys
                if item not in cv_user_data:
                    raise KeyError(f"Missing required input '{item}' for {cv_name} ({selected_model} model).")
                unpacked_args[item] = cv_user_data[item]
            
        validated_cv_args[cv_name] = {
            "model_name": selected_model,
            "kwargs": unpacked_args
        }
        
    return validated_cv_args


def load_unsteady_config(user_inputs_filepath: str | Path, 
                         defaults_filepath: str | Path = Path(__file__).parents[4] / "src" / "backend" / "unsteady" / "static_data" / "default_simulation_settings.jsonc", 
                         schema_filepath: str | Path = Path(__file__).parents[4] / "src" / "backend" / "unsteady" / "static_data" / "input_schema.jsonc") -> dict:
    """
    Loads and merges full engine configuration
    user_inputs_filepath (str): the file path to the unsteady inputs json file
    defaults_filepath (str): the file path to the default simulation settings (inside static_data; user can override any default value by including it in their inputs)
    schema_filepath (str): the file path to the CV model registry (contains all necessary inputs for each physical model for each CV)
    """
    
    # load files
    user_config = _load_jsonc(user_inputs_filepath)
    defaults_config = _load_jsonc(defaults_filepath)
    schema = _load_jsonc(schema_filepath)
    
    # merge default & user input simulation settings
    # user inputs override default settings
    overrides = user_config.get("simulation_settings_override", {})
    if overrides:
        final_settings = _merge_settings(defaults_config, overrides)
    else:
        final_settings = defaults_config
        
    # get rocket inputs
    rocket_inputs = user_config.get("rocket_inputs", {})
    if not rocket_inputs:
        raise KeyError("Missing 'rocket_inputs' block in user JSON.")
    
    # get metadata
    metadata = rocket_inputs.get("metadata", {})
    if not metadata:
        raise KeyError("Missing rocket inputs metadata")
    
    # get initial conditions
    initial_conditions = rocket_inputs.get("initial_conditions", {})
    if not initial_conditions:
        raise KeyError("Missing rocket inputs initial_conditions")
    # validate
    for required_key in schema.get("initial_conditions", []):
        if required_key not in initial_conditions:
            raise KeyError(f"Missing required initial condition: '{required_key}'")
    
    # get control volume inputs
    CV_inputs = rocket_inputs.get("CV_inputs", {})
    if not CV_inputs:
        raise KeyError("Missing rocket inputs 'CV_inputs'")
    # unpack & validate CVs
    validated_cvs = _validate_and_unpack_CVs(CV_inputs, schema)
    
    # define rocket_inputs dictionary
    rocket_inputs = {}
    cv_models = {}
    
    # dump initial conditions into rocket_inputs
    for key, value in initial_conditions.items():
        rocket_inputs[key] = value
    
    # get CV model names & put into CV_models
    for cv_name, cv_data in validated_cvs.items():
        cv_models[cv_name] = cv_data["model_name"]
        
        # dump CV args into rocket_inputs as well
        for param_key, param_value in cv_data["kwargs"].items():
            rocket_inputs[param_key] = param_value
    
    rocket_inputs["CV_models"] = cv_models
    
    return {
        "simulation_settings": final_settings,
        "rocket_inputs": rocket_inputs,
        "metadata": metadata
    }

