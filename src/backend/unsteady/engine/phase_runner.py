"""
The main executive script that initializes and runs the unsteady simulation
"""

# hella imports
import numpy as np
from scipy.integrate import solve_ivp
from pathlib import Path
import sys

project_root = Path(__file__).resolve().parents[4]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.backend.unsteady.engine.objects import StateVector, History
from src.backend.unsteady.engine.config import load_unsteady_config
from src.backend.unsteady.engine.registry import get_active_functions
from src.backend.unsteady.engine.variable_initialization import initialize_state_vector, initialize_natural_constants_dict
from src.backend.unsteady.engine.transitions import TRANSITION_REGISTRY

from src.backend.unsteady.physics.N2O_properties.N2O_properties import get_N2O_property
from src.backend.unsteady.physics.CEA.CEA_interpolator import CEA_interpolation_lookup
from src.backend.unsteady.physics.atmosphere.atmosphere import get_atmosphere_properties
from src.backend.unsteady.engine.warnings import (WARNINGS_REGISTRY, warn_initialization_limits, finalize_warnings)

import src.backend.unsteady.engine.rhs as rhs


def run_unsteady(rocket_inputs_filename: str, rocket_inputs_filepath: str | Path = Path(f"{project_root}") / "user_data" / "simulation_configs"):
    """
    The main function for running the unsteady simulation.
    Takes a JSON file of rocket inputs, outputs another JSON with simulation performance
    If you're trying to figure out how unsteady works, this is the place to start
    """
    
    # load rocket inputs and simulation settings
    rocket_inputs_full_filepath = Path(f"{rocket_inputs_filepath}") / f"{rocket_inputs_filename}"
    print(f"Loading rocket inputs from {rocket_inputs_full_filepath}\n")
    config = load_unsteady_config(rocket_inputs_full_filepath)
    rocket_inputs = config["rocket_inputs"]
    sim_settings = config["simulation_settings"]
    rocket_inputs_metadata = config["metadata"]
    
    # this dict contains constants (gravity, universal gas constant, etc)
    constants_dict = initialize_natural_constants_dict()
    
    # map physics functions (this tells the program which physics models it is supposed to run)
    cv_funcs = get_active_functions(rocket_inputs["CV_models"], "phase_2")
    
    # calculate initial state at t=0
    print("Calculating t=0 physical states\n")
        # compute initial state vector
    initial_state_dict = initialize_state_vector(rocket_inputs, constants_dict, get_N2O_property)
        # convert initial state dict to flat array to be used by solve_ivp
    y0 = StateVector.to_array(initial_state_dict)
        # compute t=0 non-state-vector values
    live_0 = {}
    live_0.update(get_atmosphere_properties(initial_state_dict["sy_R"]))
    live_0["p_T"] = get_N2O_property("p", initial_state_dict["T_T"])
    live_0["v_l"] = get_N2O_property("v_l", initial_state_dict["T_T"])
    live_0["v_v"] = get_N2O_property("v_v", initial_state_dict["T_T"])
    
    if cv_funcs.get("CV2_valve"): live_0.update(cv_funcs["CV2_valve"](0.0, initial_state_dict, rocket_inputs, live_0, constants_dict))
    if cv_funcs.get("CV3_injector"): live_0.update(cv_funcs["CV3_injector"](0.0, initial_state_dict, rocket_inputs, live_0, constants_dict))
    if cv_funcs.get("CV1_tank"): live_0.update(cv_funcs["CV1_tank"](0.0, initial_state_dict, rocket_inputs, live_0, constants_dict))
    if cv_funcs.get("CV5_nozzle"): live_0.update(cv_funcs["CV5_nozzle"](0.0, initial_state_dict, rocket_inputs, live_0, constants_dict))
    if cv_funcs.get("CV4_chamber"): live_0.update(cv_funcs["CV4_chamber"](0.0, initial_state_dict, rocket_inputs, live_0, constants_dict))
    if cv_funcs.get("CV6_trajectory"): live_0.update(cv_funcs["CV6_trajectory"](0.0, initial_state_dict, rocket_inputs, live_0, constants_dict))
    
    # initialize History object & log the starting state
    history = History(rocket_inputs)
    history.log_timestep(t=0.0, state_dict=initial_state_dict, derived_dict=live_0, phase="phase_1")
    
    # initialize warnings dictionary & log starting state
    warnings_dict = {}
    warn_initialization_limits(rocket_inputs, warnings_dict)
    
    ###################
    # MAIN PHASE LOOP #
    ###################
    active_phase = "phase_1"
    current_time = 0.0
    y_current = y0
    phase_metadata = {} # carries frozen variables (t_burnout, T_c, W_c, gamma) between phases
    
    # map phase strings to their respective RHS functions
    RHS_MAP = {
        "phase_1": rhs.rhs_phase1_ignition,
        "phase_2": rhs.rhs_phase2_liquid,
        "phase_3": rhs.rhs_phase3_gas,
        "phase_4a": rhs.rhs_phase4a_vapor_purge,
        "phase_4c": rhs.rhs_phase4c_dry_blowdown,
        "phase_5": rhs.rhs_phase5_coast,
        "phase_6": rhs.rhs_phase6_drogue_descent,
        "phase_7": rhs.rhs_phase7_main_descent
    }

    # helper to rebuild derived variables for logging and transition handler
    def _reconstruct_live(t_eval, state_dict, cvs):
        ld = {}
        ld.update(get_atmosphere_properties(state_dict["sy_R"]))
        
        # Using .get() evaluates to False if the key is missing OR if the value is None
        if cvs.get("CV1_tank"):
            ld["p_T"] = get_N2O_property("p", state_dict["T_T"])
            ld["v_l"] = get_N2O_property("v_l", state_dict["T_T"])
            ld["v_v"] = get_N2O_property("v_v", state_dict["T_T"])
            
        if cvs.get("CV2_valve"): ld.update(cvs["CV2_valve"](t_eval, state_dict, rocket_inputs, ld, constants_dict))
        if cvs.get("CV3_injector"): ld.update(cvs["CV3_injector"](t_eval, state_dict, rocket_inputs, ld, constants_dict))
        if cvs.get("CV1_tank"): ld.update(cvs["CV1_tank"](t_eval, state_dict, rocket_inputs, ld, constants_dict))
        if cvs.get("CV5_nozzle"): ld.update(cvs["CV5_nozzle"](t_eval, state_dict, rocket_inputs, ld, constants_dict))
        if cvs.get("CV4_chamber"): ld.update(cvs["CV4_chamber"](t_eval, state_dict, rocket_inputs, ld, constants_dict))
        if cvs.get("CV6_trajectory"): ld.update(cvs["CV6_trajectory"](t_eval, state_dict, rocket_inputs, ld, constants_dict))
        
        # guarantee these keys are always present
        ld.setdefault("F_thrust", 0.0)
        ld.setdefault("OF", float("nan"))
        ld.setdefault("T_c", float("nan"))
        return ld

    while not active_phase.startswith("terminal"):
        print(f"\n--- {active_phase.upper()} ---")
        
        cv_funcs = get_active_functions(rocket_inputs["CV_models"], active_phase)
        active_rhs = RHS_MAP[active_phase]
        active_events = TRANSITION_REGISTRY.get(active_phase, {}).get("events", [])
        
        # Pull dynamic timeout from settings, fallback to 60.0 if not explicitly defined
        phase_timeout = sim_settings.get("phase_max_times", {}).get(active_phase, 60.0)
        
        solution = solve_ivp(
            fun=active_rhs,
            t_span=(current_time, current_time + phase_timeout), 
            y0=y_current,
            method=sim_settings.get("solver", {}).get("integration_method", "LSODA"),
            events=active_events,
            args=(rocket_inputs, cv_funcs, constants_dict, phase_metadata),
            max_step=sim_settings.get("solver", {}).get("max_step_s", 0.05),
            rtol=sim_settings.get("solver", {}).get("rtol", 1e-6),
            atol=sim_settings.get("solver", {}).get("atol", 1e-9)
        )
        
        final_live = {} 
        
        for i in range(1, len(solution.t)): 
            t_step = solution.t[i]
            state_dict = StateVector.unpack(solution.y[:, i])
            
            live = _reconstruct_live(t_step, state_dict, cv_funcs)
            
            # update warnings dict
            for warn_func in WARNINGS_REGISTRY.get(active_phase, []):
                warn_func(t_step, warnings_dict, state_dict, live, rocket_inputs)
            
            history.log_timestep(t=t_step, state_dict=state_dict, derived_dict=live, phase=active_phase)
            
            if i == len(solution.t) - 1:
                final_live = live
            
        current_time = solution.t[-1]
        y_current = solution.y[:, -1]
        
        if solution.status == 1:
            triggered_idx = -1
            for idx, event_func in enumerate(active_events):
                if abs(event_func(current_time, y_current, rocket_inputs, cv_funcs, constants_dict, phase_metadata)) < 1e-6:
                    triggered_idx = idx
                    break
            
            state_dict = StateVector.unpack(y_current)
            if not final_live:
                final_live = _reconstruct_live(current_time, state_dict, cv_funcs)
                
            handler = TRANSITION_REGISTRY[active_phase]["handlers"][triggered_idx]
            clamped_state_dict, next_phase, new_metadata = handler(state_dict, rocket_inputs, current_time, final_live)
            
            phase_metadata.update(new_metadata)
            y_current = StateVector.to_array(clamped_state_dict)
            
            event_name = active_events[triggered_idx].__name__
            history.log_event(current_time, "PHASE_TRANSITION", f"Event '{event_name}' triggered. Exiting {active_phase} to {next_phase}")
            print(f"\n>>> [{event_name}] -> {active_phase.capitalize()} transitioned to {next_phase} at t = {current_time:.3f} s")
            active_phase = next_phase
            
        else:
            print(f"Simulation ended or timed out. Message: {solution.message}")
            active_phase = "terminal"

    # TERMINAL ABORT HANDLING
    if active_phase == "terminal_002_liquid_quench":
        history.log_event(current_time, "ABORT_002", "Catastrophic liquid quench detected. Halting simulation.")
        print("\n[ABORT 002] Catastrophic liquid quench detected. Execution stopped.")
    elif active_phase == "terminal_apogee_abort":
        history.log_event(current_time, "ABORT_APOGEE", "Apogee reached during powered ascent. Halting simulation.")
        print("\n[ABORT] Apogee reached during powered ascent. Execution stopped.")
    elif active_phase == "terminal_success_landed":
        print("\n[SUCCESS] Rocket landed")

    print("\nSimulation Complete! Ready for export.")
    finalized_warnings = finalize_warnings(warnings_dict) if rocket_inputs_metadata.get("warnings", True) else None # keep warnings by default if not specified
    return history.export(rocket_inputs, finalized_warnings)
    


run_unsteady("unsteady_input_template.jsonc")
#run_unsteady("joel_unsteady_inputs.jsonc")