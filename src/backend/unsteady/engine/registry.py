"""
This file maps string model names form the JSON inputs config to the actual physics code inside src/backend/unsteady/physics/CVs


PHASE DEFINITIONS:
phase_1: Ignition and startup ramp
phase_2: Liquid blowdown (nominal)
phase_3: Gaseous blowdown (nominal)
phase_4a: Vapor Purge Shutdown (Fuel depleted, gaseous oxidizer flows)
phase_4b: Liquid Shutdown (Fuel depleted, liquid oxidizer remains) -- not in CV_REGISTRY because it aborts the simulation rather than running its own physics
phase_4c: Dry Blowdown Shutdown (Tank empty, chamber depressurizes)
phase_5: Coasting (ballistic flight)
phase_6: Drogue descent (drogue parachute)
phase_7: Main descent (main parachute)
"""

import src.backend.unsteady.physics.CVs.CV1_tank as CV1
import src.backend.unsteady.physics.CVs.CV2_valve as CV2
import src.backend.unsteady.physics.CVs.CV3_injector as CV3
import src.backend.unsteady.physics.CVs.CV4_chamber as CV4
import src.backend.unsteady.physics.CVs.CV5_nozzle as CV5
import src.backend.unsteady.physics.CVs.CV6_trajectory as CV6

# list out every function for each CV/model & which phase(s) each function belongs to
CV_REGISTRY = {
    "CV1_tank": {
        "joel": {
            ("phase_1", "phase_2"): CV1.tank_liquid_blowdown,
            ("phase_3", "phase_4a"): CV1.tank_gaseous_blowdown
        }
    },
    "CV2_valve": {
        "linear": {"universal": CV2.valve_linear_ramp},
        "sigmoid": {"universal": CV2.valve_sigmoid_ramp}
    },
    "CV3_injector": {
        "joel": {
            ("phase_1", "phase_2"): CV3.injector_joel_liquid_blowdown,
            ("phase_3", "phase_4a"): CV3.injector_joel_gaseous_blowdown
        },
        "nhne": {
            ("phase_1", "phase_2"): CV3.injector_nhne_liquid_blowdown,
            ("phase_3", "phase_4a"): CV3.injector_nhne_gaseous_blowdown
        }
    },
    "CV4_chamber": {
        "joel": {
            ("phase_1", "phase_2", "phase_3"): CV4.chamber_joel_unsteady,
            ("phase_4a", "phase_4c"): CV4.chamber_residual_blowdown
        }
    },
    "CV5_nozzle": {
        "joel": {
            ("phase_1", "phase_2", "phase_3"): CV5.nozzle_joel_unsteady,
            ("phase_4a", "phase_4c"): CV5.nozzle_residual_blowdown
        }
    },
    "CV6_trajectory": {
        "2dof": {
            ("phase_1", "phase_2", "phase_3", "phase_4a", "phase_4c"): CV6.trajectory_powered_ascent,
            ("phase_5",): CV6.trajectory_coasting,
            ("phase_6",): CV6.trajectory_drogue_descent,
            ("phase_7",): CV6.trajectory_main_descent
        }
    }
}


def get_active_functions(cv_models_dict: dict, current_phase: str) -> dict:
    """
    takes CV_models dict (contains which models to use for which CVs), 
    returns a dict of the corresponding functions to run in solve_ivp
    """
    
    active_funcs = {}
    for cv_name, model_string in cv_models_dict.items():
        try:
            available_phases = CV_REGISTRY[cv_name][model_string]
        except KeyError:
            raise KeyError(f"Model '{model_string}' for {cv_name} is not registered in registry.py")
            
        # check if the model uses the same math for all phases
        if "universal" in available_phases:
            active_funcs[cv_name] = available_phases["universal"]
            
        # iterate through the phase tuples to find the current phase
        else:
            func_found = False
            for phase_tuple, func in available_phases.items():
                if current_phase in phase_tuple:
                    active_funcs[cv_name] = func
                    func_found = True
                    break # can stop looking once a match is found
            
            # if no tuple contained the current phase, the CV is inactive
            if not func_found:
                active_funcs[cv_name] = None
            
    return active_funcs


