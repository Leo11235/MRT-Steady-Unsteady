"""
Warnings look for an log validity/runtime information. They do not affect the program while it is running, but rather get returned to the user afterward. They can be global of phase/CV specific. 
    - Advisory (of note, not necessarily bad)
    - Warning (potential problems with the input rcket config)
    - Critical (cause the simulation to fail or to be severely unphysical)
    
    - Debug (more about the simulation engine than physics)
"""

import math

# checks whether a whole bunch of rocket input values are within the model's validity range
def warn_initialization_limits(rocket_inputs: dict, warning_dict: dict): 
    ###### fuel grain
    L_f = rocket_inputs["chamber_fuel_length_m"]
    if "chamber_fuel_internal_radius_m" in rocket_inputs:
        r_f = rocket_inputs["chamber_fuel_internal_radius_m"]
    else:
        # if the user provided fuel mass instead, calculate the implied r_f
        m_f_tot = rocket_inputs["chamber_fuel_mass_kg"]
        p_f = rocket_inputs["chamber_fuel_density_kgm3"]
        R_f = rocket_inputs["chamber_fuel_external_radius_m"]
        r_f = math.sqrt(R_f**2 - m_f_tot / (math.pi * p_f * L_f))
    
    if L_f < 0.2:
        warning_dict["init_short_fuel_grain"] = {
            "severity": "warning",
            "message": "Fuel grain length is dangerously short (< 0.2 m). 1D regression models lose accuracy at low L/D ratios.",
            "length_m": L_f
        }
        
    if r_f < 0.01:
        warning_dict["init_tight_fuel_port"] = {
            "severity": "warning",
            "message": "Initial fuel port radius is extremely tight (< 1 cm). High risk of choked port flow and flame blowout.",
            "radius_m": r_f
        }
    
    ##### tank ullage
    if "tank_ullage_fraction" in rocket_inputs:
        ullage = rocket_inputs["tank_ullage_fraction"]
        if ullage < 0.10:
            warning_dict["init_low_ullage"] = {
                "severity": "critical",
                "message": "Tank ullage fraction is dangerously low (< 10%). Severe risk of hydraulic lock and catastrophic tank failure due to thermal expansion.",
                "ullage_fraction": ullage
            }
        elif ullage > 0.30:
            warning_dict["init_high_ullage"] = {
                "severity": "advisory",
                "message": "Tank ullage fraction is unusually high (> 30%). This reduces volumetric efficiency and total impulse.",
                "ullage_fraction": ullage
            }
    

# checks whether CEA is a good predictor for a given (OF, p_C) input to CEA
def warn_CEA_outside_tested_range(t: float, warning_dict: dict, state_vector: dict, live: dict, rocket_inputs: dict):
    warn_key = "CEA_outside_tested_range"
    
    OF = live.get("OF", float('nan'))
    p_C = state_vector.get("p_C", float('nan'))
    
    # exit if OF or p_C not computed yet
    if math.isnan(OF) or math.isnan(p_C):
        return
    
    of_out_of_bounds = (OF < 1.0) or (OF > 12.0)
    pc_out_of_bounds = (p_C < 1e5) or (p_C > 100e5)
    
    # exit if within bounds
    if not (of_out_of_bounds or pc_out_of_bounds):
        return
    
    # if this warning is already in the dict, update
    if warning_dict.get(warn_key):
        # update num occurences, timesteps, (OF, p_C), min, max OF, min, max p_C, etc
        key = warning_dict[warn_key]
        key["num_occurences"] += 1
        key["timesteps"].append(t)
        key["(OF, p_C)"].append((live["OF"], state_vector["p_C"]))
        key["min_OF"] = min(key["min_OF"], OF)
        key["max_OF"] = max(key["max_OF"], OF)
        key["min_p_C"] = min(key["min_p_C"], p_C)
        key["max_p_C"] = max(key["max_p_C"], p_C)
    
    # else, add the warning to the dict
    else: 
        warning_dict[warn_key] = {
            "severity": "advisory",
            "message": "One or more NASA-CEA inputs are outside the range the program was designed to handle",
            "num_occurences": 1,
            "timesteps": [t],
            "(OF, p_C)": [(live["OF"], state_vector["p_C"])],
            "min_OF": OF,
            "max_OF": OF,
            "min_p_C": p_C,
            "max_p_C": p_C
        }
    
# checks whether a given (OF, p_C) CEA input is outside the table bounds in static_data/CEA_table.json
from src.backend.unsteady.physics.CEA.CEA_interpolator import get_CEA_table_bounds
OF_MIN, OF_MAX, p_C_MIN, p_C_MAX = get_CEA_table_bounds()
def warn_CEA_outside_table_bounds(t: float, warning_dict: dict, state_vector: dict, live: dict, rocket_inputs: dict):
    warn_key = "CEA_outside_table_bounds"
    
    OF = live.get("OF", float('nan'))
    p_C = state_vector.get("p_C", float('nan'))
    
    # exit if OF or p_C not computed yet
    if math.isnan(OF) or math.isnan(p_C):
        return
    
    of_out_of_bounds = (OF < OF_MIN) or (OF > OF_MAX)
    pc_out_of_bounds = (p_C < p_C_MIN) or (p_C > p_C_MAX)
    
    # exit if within bounds
    if not (of_out_of_bounds or pc_out_of_bounds):
        return
    
    # if this warning is already in the dict, update
    if warning_dict.get(warn_key):
        # update num occurences, timesteps, (OF, p_C), min, max OF, min, max p_C, etc
        key = warning_dict[warn_key]
        key["num_occurences"] += 1
        key["timesteps"].append(t)
        key["min_OF"] = min(key["min_OF"], OF)
        key["max_OF"] = max(key["max_OF"], OF)
        key["min_p_C"] = min(key["min_p_C"], p_C)
        key["max_p_C"] = max(key["max_p_C"], p_C)
    
    # else, add the warning to the dict
    else: 
        warning_dict[warn_key] = {
            "severity": "debug",
            "message": "One or more NASA-CEA inputs are outside the precomputed table's range",
            "num_occurences": 1,
            "timesteps": [t],
            "min_OF": OF,
            "max_OF": OF,
            "min_p_C": p_C,
            "max_p_C": p_C
        }

WARNINGS_REGISTRY = {
    "phase_1": [warn_CEA_outside_tested_range, warn_CEA_outside_table_bounds],
    "phase_2": [warn_CEA_outside_tested_range, warn_CEA_outside_table_bounds],
    "phase_3": [warn_CEA_outside_tested_range, warn_CEA_outside_table_bounds],
    "phase_4a": [],
    "phase_4c": [],
    "phase_5": [],
    "phase_6": [],
    "phase_7": []
}

# computes overall simulation health level
def finalize_warnings(warning_dict: dict):
    severity_rank = {"advisory": 1, "warning": 2, "critical": 3}
    max_severity_val = 0
    overall_level = "nominal"

    for warn_id, warn_data in warning_dict.items():
        val = severity_rank.get(warn_data.get("severity", "").lower(), 0)
        if val > max_severity_val:
            max_severity_val = val
            overall_level = warn_data["severity"]

    return {
        "overall_warning_level": overall_level,
        "triggered_warnings": warning_dict
    }