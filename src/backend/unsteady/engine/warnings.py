"""
Warnings look for an log validity/runtime information. They do not affect the program while it is running, but rather get returned to the user afterward. They can be global of phase/CV specific. 
    - Advisory (of note, not necessarily bad)
    - Caution (potential problems with the input rocket config)
    - Critical (cause the simulation to fail or to be severely unphysical)
    
    - Debug (more about the simulation engine than physics)
"""

import math

###############################
# init warnings
###############################
# input range & sanity checks
# checks whether a whole bunch of rocket input values are valid and within the model's validity range
# !!! this function is used directly by the frontend. Do not change the inputs, and only add to warning_dict if it would be reasonable for the user to get a popup warning them about that input. 
def warn_initialization_limits(rocket_inputs: dict, warning_dict: dict | None = None): 
    if warning_dict is None: 
        warning_dict={}
    
    
    ###### fuel grain
    L_f = rocket_inputs["chamber_fuel_length"]
    R_f = rocket_inputs["chamber_fuel_external_radius"]
    
    if "chamber_fuel_internal_radius" in rocket_inputs:
        # if the user provided fuel internal radius, check inputs
        r_f = rocket_inputs["chamber_fuel_internal_radius"]
    else:
        # if the user provided fuel mass instead, calculate the implied r_f, then check inputs
        m_f_tot = rocket_inputs["chamber_fuel_mass"]
        p_f = rocket_inputs["chamber_fuel_density"]
        try: # triggers if inputs are gemoetrically valid
            r_f = math.sqrt(R_f**2 - m_f_tot / (math.pi * p_f * L_f))
        except ValueError: # triggers if inputs are physically impossible (ie inner diameter > outer diameter)
            r_f = None
    
    if L_f < 0.2:
        warning_dict["init_short_fuel_grain"] = {
            "severity": "caution",
            "message": "Fuel grain length is dangerously short (< 0.2 m). 1D regression models lose accuracy at low L/D ratios.",
            "fuel_cell_length": L_f
        }
        
    if r_f is not None and r_f < 0.01:
        warning_dict["init_tight_fuel_port"] = {
            "severity": "caution",
            "message": f"Initial fuel port radius is extremely tight ({r_f*100} < 1 cm). High risk of choked port flow and flame blowout.",
            "inner_radius": r_f
        }
        
    if r_f is None or r_f >= R_f:
        warning_dict["init_inner_fuel_radius_exceeds_outer_fuel_radius"] = {
            "severity": "critical", 
            "message": f"Inner fuel radius ({r_f}{" m" if r_f is not None else ""}) either impossible to calculate or is larger than outer fuel radius ({R_f} m). If initialized via fuel mass, ensure a real value can be calculated.", 
            "inner_radius": r_f, 
            "outer_radius": R_f
        }
        
    ##### check if fuel grain radius is larger than rocket external radius
    R_r = rocket_inputs["rocket_outer_radius"]
    if R_f > R_r:
        warning_dict["init_fuel_outer_radius_greater_than_rocket_outer_radius"] = {
            "severity": "critical", 
            "message": f"Outer fuel radius ({R_f} m) is larger than rocket outer radius ({R_r} m)", 
            "fuel_outer_radius": R_f, 
            "rocket_outer_radius": R_r
        }
    
    ##### tank ullage
    if "tank_ullage_fraction" in rocket_inputs:
        ullage = rocket_inputs["tank_ullage_fraction"]
        if ullage < 0.10:
            warning_dict["init_low_ullage"] = {
                "severity": "caution",
                "message": "Tank ullage fraction is dangerously low (< 10%). Severe risk of hydraulic lock and catastrophic tank failure due to thermal expansion.",
                "ullage_fraction": ullage
            }
        elif ullage > 0.30:
            warning_dict["init_high_ullage"] = {
                "severity": "advisory",
                "message": "Tank ullage fraction is unusually high (> 30%). This reduces volumetric efficiency and total impulse.",
                "ullage_fraction": ullage
            }
    
    ##### regression rate warnings
    """
    accepted value ranges for Paraffin/N2O
        - fuel regression coefficient (a): [0.5e-4, 1e-3]
        - fuel regression exponent (n): [0.3, 0.9]
    
    sources
        - Karabeyoglu, Altman & Cantwell (2001), "Development and Testing of Paraffin-Based Hybrid Rocket Fuels"
        - Karabeyoglu et al. (2004), "Combustion of Liquefying Hybrid Propellants" (JPP Vol 20 No 6)
        - Sutton & Biblarz, Rocket Propulsion Elements, Chapter 15 (hybrids)
    """
    if "chamber_regression_rate_scaling_constant" in rocket_inputs: 
        a = rocket_inputs["chamber_regression_rate_scaling_constant"]
        if a < 0.5e-4:
            warning_dict["init_low_chamber_regression_rate_scaling_constant"] = {
                    "severity": "caution",
                    "message": f"Regression rate constant ({a}) is unusually low. Recommended range is [0.5e-4, 1e-3]. ",
                    "chamber_regression_rate_scaling_constant": a
                }
        elif a> 1e-3: 
            warning_dict["init_high_chamber_regression_rate_scaling_constant"] = {
                    "severity": "caution",
                    "message": f"Regression rate constant ({a}) is unusually high. Recommended range is [0.5e-4, 1e-3]. ",
                    "chamber_regression_rate_scaling_constant": a
                }

    if "chamber_regression_rate_exponent" in rocket_inputs:
        n = rocket_inputs["chamber_regression_rate_exponent"]
        if n < 0.3:
            warning_dict["init_low_chamber_regression_rate_exponent"] = {
                    "severity": "caution",
                    "message": f"Regression rate exponent ({n}) is unusually low. Recommended range is [0.3, 0.9]. ",
                    "chamber_regression_rate_exponent": n
                }
        elif n > 0.9:
            warning_dict["init_high_chamber_regression_rate_exponent"] = {
                    "severity": "caution",
                    "message": f"Regression rate exponent ({n}) is unusually high. Recommended range is [0.3, 0.9]. ",
                    "chamber_regression_rate_exponent": n
                }


########################################
# timestep warnings (run every timestep)
########################################

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
from src.backend.unsteady.physics.CEA.CEA_interpolator import get_CEA_table_bounds, envelope_excursions
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

from src.backend.unsteady.physics.N2O_properties.N2O_properties import N2O_excursions
# N2O warnings implemented after and differently from CEA warnings. N2O_properties.py directly stores all the instances where we go outside table bounds, and a summary of all these instances is created once (see end of sim warnings section below)


##############################################################################################
# transition-triggered warning (run only once per phase transition rather than every timestep)
##############################################################################################

# phase 3 ended by the thrust floor rather than finishing on its own
# vapor blowdown decays asymptotically, so there is always some thrust left. better to cut it off early and save 5s of compute time (during tests, this missed out on ~0.0003% of total impulse)
def warn_engine_cutoff_thrust_floor(t: float, warning_dict: dict, state_vector: dict, live: dict, rocket_inputs: dict):
    F = live.get("F_thrust", 0.0)
    k = rocket_inputs.get("min_thrust_to_weight", 0.02)

    warning_dict["engine_cutoff_thrust_floor"] = {
        "severity": "advisory",
        "message": (f"Engine cut off at t={t:.2f} s while still producing {F:.1f} N, because thrust had fallen below {k:.1%} of vehicle weight. The remaining decay tail was not integrated, so apogee is marginally conservative."),
        "t_cutoff": t,
        "F_thrust_at_cutoff": F,
        "min_thrust_to_weight": k,
    }


#########################################
# end of sim warnings
#########################################

# CEA lookups that were held at the edge of the precomputed table
def warn_CEA_envelope_excursions(warning_dict: dict):
    for key, exc in envelope_excursions().items():
        warning_dict[f"cea_envelope_{key.replace(' ', '_').replace('/', '')}"] = {
            "severity": "caution",
            "message": (f"{exc['axis']} went {exc['limit']} {exc['count']} times; worst was {exc['worst_requested']:.4g} against a table edge of {exc['table_edge']:.4g}. Values were held at the edge for those steps."),
            "axis": exc["axis"],
            "worst_requested": exc["worst_requested"],
            "table_edge": exc["table_edge"],
            "occurrences": exc["count"],
        }

# N2O lookups that fell outside the N2O table
def warn_N2O_envelope_excursions(warning_dict: dict):
    for key, exc in N2O_excursions().items():
        if "minimum" in exc["limit"]:
            note = "Below the N2O triple point no saturated liquid-vapour state exists; the tank had effectively finished blowing down."
        else:
            note = "Above the N2O critical point the liquid and vapour phases are not distinct."

        warning_dict[f"n2o_table_{key.replace(' ', '_')}"] = {
            "severity": "caution",
            "message": (f"Tank temperature went {exc['limit']} {exc['count']} times; worst was {exc['worst_requested']:.5g} K against a table edge of {exc['table_edge']:.5g} K. Saturated properties were held at the edge for those steps. {note}"),
            "worst_requested_K": exc["worst_requested"],
            "table_edge_K": exc["table_edge"],
            "occurrences": exc["count"],
        }

# report any abnormal ending for the user to see
def warn_terminal_state(warning_dict: dict, terminal_info: dict, t: float):
    if terminal_info["completed_nominally"]:
        return

    warning_dict[f"terminal_{terminal_info['code']}"] = {
        "severity": terminal_info["severity"],
        "message": f"Simulation ended at t={t:.3f} s. {terminal_info['message']}",
        "terminal_state": terminal_info["code"],
        "t_terminal": t,
    }

# checks whether peak TtW is above ~5 and whether the rocket climbed at least ~10m (~ for both because the values depend on what is written in default_simulation_settings.jsonc)
def warn_launch_capability(warning_dict: dict, metrics: dict, min_TtW: float, min_gain_m: float):
    TtW = metrics.get("peak_thrust_to_weight")
    if TtW is not None and TtW < min_TtW:
        warning_dict["low_peak_thrust_to_weight"] = {
            "severity": "caution",
            "message": f"Peak thrust-to-weight is {TtW:.2f}, below the recommended minimum of {min_TtW:.1f}. A rocket this marginal leaves the rail slowly and is unstable while it does.",
            "peak_thrust_to_weight": TtW,
            "peak_thrust_N": metrics.get("peak_thrust_N"),
            "minimum": min_TtW,
        }

    gain = metrics.get("altitude_gain", 0.0)
    if gain < min_gain_m:
        warning_dict["failed_to_launch"] = {
            "severity": "critical",
            "message": f"The vehicle rose {gain:.2f} m above the pad, under the {min_gain_m:.0f} m needed to count as a launch. Every trajectory figure in this run describes a rocket that did not fly.",
            "altitude_gain": gain,
            "minimum": min_gain_m,
        }


###############################################################################################
# WARNING REGISTRIES
# these keep track of all the warnings between each timestep/phase. if a new warning function is added in the file above, it must also be added in a registry in order for phase_runner to interact with it. 


# tested every timestep
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


# which transition events owe the user a warning when they fire, keyed by th event function's __name__
TRANSITION_WARNINGS_REGISTRY = {
    "event_thrust_below_floor": [warn_engine_cutoff_thrust_floor],
}
# run whatever warnings a just-fired transition event owes the user
# phase runner calls this on every transition without checking anything, so which events are worth warning about stays a question this file answers and the runner never grows a chain of name comparisons
def warn_on_transition(event_name: str, t: float, warning_dict: dict, state_vector: dict, live: dict, rocket_inputs: dict):
    for func in TRANSITION_WARNINGS_REGISTRY.get(event_name, []):
        func(t, warning_dict, state_vector, live, rocket_inputs)

# computes overall simulation health level
def finalize_warnings(warning_dict: dict):
    severity_rank = {"advisory": 1, "caution": 2, "critical": 3}
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