"""
Contains all event triggers and their corresponding transition handlers for the unsteady simulation, organized by phase
"""

from src.backend.unsteady.engine.objects import StateVector
from src.backend.unsteady.physics.N2O_properties.N2O_properties import get_N2O_property
from src.backend.unsteady.physics.atmosphere.atmosphere import get_atmosphere_properties

# HELPER FUNCTIONS
def _get_n_l_thresh(rocket_inputs, constants):
    m_ox_0 = rocket_inputs.get("tank_oxidizer_mass", 0.0)
    W_o = constants.get("nitrous_oxide_molar_mass", 0.044013)
    n_l0 = m_ox_0 / W_o
    return rocket_inputs.get("n_l_thresh_mol", 0.005 * n_l0)

def _get_eps_n_ox(rocket_inputs):
    return rocket_inputs.get("epsilons", {}).get("n_ox_mol", 1e-8)

def _capture_burnout_metadata(current_time, live):
    """Utility to freeze the thermodynamics at the moment of engine burnout/abort"""
    return {
        "t_burnout": current_time,
        "T_c_burnout": live.get("T_c", 3000.0),
        "W_c_burnout": live.get("W_c", 0.025),
        "gamma_burnout": live.get("gamma", 1.15)
    }

def event_apogee_abort(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    launch_asl = rocket_inputs.get("launch_site_altitude_asl", 0.0)
    
    # apogee can only happen if the rocket has taken off
    if state["sy_R"] < launch_asl + 1.0:
        return 1.0 # dummy; ensures the event is ignored if on the pad
    return state["vy_R"]
event_apogee_abort.terminal = True
event_apogee_abort.direction = -1

def transition_apogee_abort(state, rocket_inputs, current_time, live):
    # Aborts the simulation if apogee is reached while the engine is still supposed to be firing
    return state, "terminal_apogee_abort", {}


# ========================================================
# ======================= PHASE 1 ========================
# ========================================================

def event_fuel_burnout_during_ignition(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    return rocket_inputs["chamber_fuel_external_radius"] - state["r_f"]
event_fuel_burnout_during_ignition.terminal = True
event_fuel_burnout_during_ignition.direction = -1
def transition_fuel_burnout_during_ignition(state, rocket_inputs, current_time, live):
    state["r_f"] = rocket_inputs["chamber_fuel_external_radius"]
    state["T_C"] = live.get("T_c", 3000.0)
    return state, "terminal_liquid_quench", _capture_burnout_metadata(current_time, live)

def event_liquid_depleted_during_ignition(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    return state["n_l"] - _get_n_l_thresh(rocket_inputs, constants)
event_liquid_depleted_during_ignition.terminal = True
event_liquid_depleted_during_ignition.direction = -1
def transition_liquid_depleted_during_ignition(state, rocket_inputs, current_time, live):
    state["n_v"] += state["n_l"]
    state["n_l"] = 0.0
    return state, "phase_3", {}

def event_ignition_pressure_reached(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    p_amb = get_atmosphere_properties(state["sy_R"])["p_amb"]
    return (p_amb + rocket_inputs.get("ignition_delta_p_pa", 500000.0)) - state["p_C"]
event_ignition_pressure_reached.terminal = True
event_ignition_pressure_reached.direction = -1
def transition_ignition_pressure_reached(state, rocket_inputs, current_time, live):
    return state, "phase_2", {}


# ========================================================
# ======================= PHASE 2 ========================
# ========================================================

def event_fuel_burnout_during_liquid_blowdown(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    return rocket_inputs["chamber_fuel_external_radius"] - state["r_f"]
event_fuel_burnout_during_liquid_blowdown.terminal = True
event_fuel_burnout_during_liquid_blowdown.direction = -1
def transition_fuel_burnout_during_liquid_blowdown(state, rocket_inputs, current_time, live):
    state["r_f"] = rocket_inputs["chamber_fuel_external_radius"]
    return state, "terminal_liquid_quench", _capture_burnout_metadata(current_time, live)

def event_oxidizer_depleted_during_liquid_blowdown(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    return (state["n_v"] + state["n_l"]) - _get_eps_n_ox(rocket_inputs)
event_oxidizer_depleted_during_liquid_blowdown.terminal = True
event_oxidizer_depleted_during_liquid_blowdown.direction = -1
def transition_oxidizer_depleted_during_liquid_blowdown(state, rocket_inputs, current_time, live):
    state["n_v"] = 0.0
    state["n_l"] = 0.0
    state["T_C"] = live.get("T_c", 3000.0)
    return state, "phase_4c", _capture_burnout_metadata(current_time, live)

def event_liquid_depleted(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    return state["n_l"] - _get_n_l_thresh(rocket_inputs, constants)
event_liquid_depleted.terminal = True
event_liquid_depleted.direction = -1
def transition_liquid_depleted(state, rocket_inputs, current_time, live):
    state["n_v"] += state["n_l"]
    state["n_l"] = 0.0
    return state, "phase_3", {}


# ========================================================
# ======================= PHASE 3 ========================
# ========================================================

# fuel cell burns out while tank still contains gas --> to go phase 4a
def event_fuel_burnout_during_gaseous_blowdown(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    return rocket_inputs["chamber_fuel_external_radius"] - state["r_f"]
event_fuel_burnout_during_gaseous_blowdown.terminal = True
event_fuel_burnout_during_gaseous_blowdown.direction = -1
def transition_fuel_burnout_during_gaseous_blowdown(state, rocket_inputs, current_time, live):
    state["r_f"] = rocket_inputs["chamber_fuel_external_radius"]
    state["T_C"] = live.get("T_c", 3000.0)
    return state, "phase_4a", _capture_burnout_metadata(current_time, live)

# combustion stalls (tank gas runs out before chamber fuel) --> go to phase 5
def event_chamber_near_ambient_during_gaseous_blowdown(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    k_amb = rocket_inputs.get("k_amb", 1.05)
    p_amb = get_atmosphere_properties(state["sy_R"])["p_amb"]
    return state["p_C"] - (k_amb * p_amb)
event_chamber_near_ambient_during_gaseous_blowdown.terminal = True
event_chamber_near_ambient_during_gaseous_blowdown.direction = -1
def transition_chamber_near_ambient_during_gaseous_blowdown(state, rocket_inputs, current_time, live):
    state["n_l"] = 0.0 
    state["T_C"] = live.get("T_c", 3000.0)
    return state, "phase_5", _capture_burnout_metadata(current_time, live) # bypass phase 4 if the feed stalls

# in case the tank gas runs out before chamber fuel but the combustion still hasn't stalled --> phase 4c
def event_oxidizer_depleted_during_gaseous_blowdown(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    return state["n_v"] - _get_eps_n_ox(rocket_inputs)
event_oxidizer_depleted_during_gaseous_blowdown.terminal = True
event_oxidizer_depleted_during_gaseous_blowdown.direction = -1
def transition_oxidizer_depleted_during_gaseous_blowdown(state, rocket_inputs, current_time, live):
    state["n_v"] = 0.0
    state["T_C"] = live.get("T_c", 3000.0)
    return state, "phase_4c", _capture_burnout_metadata(current_time, live)

# rocket has very little thrust to weight ratio
def event_thrust_below_floor_during_gaseous_blowdown(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    k = rocket_inputs.get("min_thrust_to_weight", 0.02)
    nozzle_fn = cv_funcs.get("CV5_nozzle")
    if k <= 0.0 or nozzle_fn is None:
        return 1.0
    # identical expression to the one in CV6_trajectory
    W_o = constants["nitrous_oxide_molar_mass"]
    m_total = (rocket_inputs["rocket_dry_mass"] + (state["n_l"] + state["n_v"]) * W_o + state["m_o"] + state["m_f"])
    weight = m_total * constants["sea_level_gravity"]
    live = dict(get_atmosphere_properties(state["sy_R"]))
    return nozzle_fn(t, state, rocket_inputs, live, constants)["F_thrust"] - k * weight
event_thrust_below_floor_during_gaseous_blowdown.terminal = True
event_thrust_below_floor_during_gaseous_blowdown.direction = -1
def transition_thrust_below_floor_during_gaseous_blowdown(state, rocket_inputs, current_time, live):
    state["n_l"] = 0.0
    state["T_C"] = live.get("T_c", 3000.0)
    return state, "phase_5", _capture_burnout_metadata(current_time, live)  # engine is done, skip the purge

# ========================================================
# =================== PHASE 4a & 4c ======================
# ========================================================
def event_chamber_near_ambient_after_burnout(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    p_amb = get_atmosphere_properties(state["sy_R"])["p_amb"]
    return state["p_C"] - (rocket_inputs.get("k_amb", 1.05) * p_amb)
event_chamber_near_ambient_after_burnout.terminal = True
event_chamber_near_ambient_after_burnout.direction = -1
def transition_chamber_near_ambient_after_burnout(state, rocket_inputs, current_time, live):
    return state, "phase_5", {}

# Note: we reuse event_apogee_reached from Phase 5 to jump straight to Phase 6  if apogee happens during the engine shutdown bleed.


# ========================================================
# ======================= PHASE 5 ========================
# ========================================================

def event_landing_before_apogee(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    return state["sy_R"] - rocket_inputs["launch_site_altitude_asl"]
event_landing_before_apogee.terminal = True
event_landing_before_apogee.direction = -1
def transition_landing_before_apogee(state, rocket_inputs, current_time, live):
    state["sy_R"] = rocket_inputs["launch_site_altitude_asl"]
    return state, "terminal_success_landed", {}

def event_apogee_reached(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    launch_asl = rocket_inputs.get("launch_site_altitude_asl", 0.0)
    # apogee can only happen if the rocket has taken off
    if state["sy_R"] < launch_asl + 1.0:
        return 1.0 # dummy; ensures the event is ignored if on the pad
    return state["vy_R"]
event_apogee_reached.terminal = True
event_apogee_reached.direction = -1
def transition_apogee_reached(state, rocket_inputs, current_time, live):
    return state, "phase_6", {}


# ========================================================
# ======================= PHASE 6 ========================
# ========================================================

def event_landing_before_main_deploy(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    return state["sy_R"] - rocket_inputs["launch_site_altitude_asl"]
event_landing_before_main_deploy.terminal = True
event_landing_before_main_deploy.direction = -1
def transition_landing_before_main_deploy(state, rocket_inputs, current_time, live):
    state["sy_R"] = rocket_inputs["launch_site_altitude_asl"]
    return state, "terminal_success_landed", {}

def event_main_deployment_altitude_reached_descending(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    launch_asl = rocket_inputs.get("launch_site_altitude_asl", 0.0)
    deploy_agl = rocket_inputs.get("main_parachute_deployment_altitude_agl", 450.0)
    target_deploy_asl = launch_asl + deploy_agl
    return state["sy_R"] - target_deploy_asl
event_main_deployment_altitude_reached_descending.terminal = True
event_main_deployment_altitude_reached_descending.direction = -1
def transition_main_deployment_altitude_reached_descending(state, rocket_inputs, current_time, live):
    return state, "phase_7", {}


# ========================================================
# ======================= PHASE 7 ========================
# ========================================================

def event_landing_reached(t, y, rocket_inputs, cv_funcs, constants, phase_metadata):
    state = StateVector.unpack(y)
    return state["sy_R"] - rocket_inputs["launch_site_altitude_asl"]
event_landing_reached.terminal = True
event_landing_reached.direction = -1
def transition_landing_reached(state, rocket_inputs, current_time, live):
    state["sy_R"] = rocket_inputs["launch_site_altitude_asl"]
    return state, "terminal_success_landed", {}


# ========================================================
# ====================== REGISTRY ========================
# ========================================================
TRANSITION_REGISTRY = {
    "phase_1": {
        "events": [event_fuel_burnout_during_ignition, 
                   event_liquid_depleted_during_ignition, 
                   event_ignition_pressure_reached, 
                   event_apogee_abort],
        "handlers": [transition_fuel_burnout_during_ignition, 
                     transition_liquid_depleted_during_ignition, 
                     transition_ignition_pressure_reached, 
                     transition_apogee_abort]
    },
    "phase_2": {
        "events": [event_fuel_burnout_during_liquid_blowdown, 
                   event_oxidizer_depleted_during_liquid_blowdown, 
                   event_liquid_depleted, 
                   event_apogee_abort],
        "handlers": [transition_fuel_burnout_during_liquid_blowdown, 
                     transition_oxidizer_depleted_during_liquid_blowdown, 
                     transition_liquid_depleted, 
                     transition_apogee_abort]
    },
    "phase_3": {
        "events": [event_fuel_burnout_during_gaseous_blowdown, 
                   event_chamber_near_ambient_during_gaseous_blowdown, 
                   event_oxidizer_depleted_during_gaseous_blowdown, 
                   event_apogee_abort, 
                   event_thrust_below_floor_during_gaseous_blowdown],
        "handlers": [transition_fuel_burnout_during_gaseous_blowdown, 
                     transition_chamber_near_ambient_during_gaseous_blowdown, 
                     transition_oxidizer_depleted_during_gaseous_blowdown, 
                     transition_apogee_abort, 
                     transition_thrust_below_floor_during_gaseous_blowdown]
    },
    "phase_4a": {
        "events": [event_chamber_near_ambient_after_burnout, event_apogee_reached],
        "handlers": [transition_chamber_near_ambient_after_burnout, transition_apogee_reached]
    },
    "phase_4c": {
        "events": [event_chamber_near_ambient_after_burnout, event_apogee_reached],
        "handlers": [transition_chamber_near_ambient_after_burnout, transition_apogee_reached]
    },
    "phase_5": {
        "events": [event_landing_before_apogee, event_apogee_reached],
        "handlers": [transition_landing_before_apogee, transition_apogee_reached]
    },
    "phase_6": {
        "events": [event_landing_before_main_deploy, 
                   event_main_deployment_altitude_reached_descending],
        "handlers": [transition_landing_before_main_deploy, 
                     transition_main_deployment_altitude_reached_descending]
    },
    "phase_7": {
        "events": [event_landing_reached],
        "handlers": [transition_landing_reached]
    }
}



# ========================================================
# ================== TERMINAL STATES =====================
# ========================================================
"""
Records what each way of ending a run means. Kept here with transitions so that adding a new terminal state and describing it only require changing one file. 
Each terminal state has: 
    code: unique identifier for that state
    completed_nominally: T/F whether the simulation ran normally or had to abort
    severity: the warning severity, see warnings.py
    message: a message describing the state
    console: what gets printed to the console
"""

TERMINAL_STATES = {
    "terminal_success_landed": {
        "code": "success_landed",
        "completed_nominally": True,
        "severity": "advisory",
        "message": "Rocket completed the full flight and landed.",
        "console": "[SUCCESS] Rocket landed",
    },
    "terminal_liquid_quench": {
        "code": "liquid_quench",
        "completed_nominally": False,
        "severity": "critical",
        "message": "Fuel grain burned through while liquid oxidizer was still flowing. Raw oxidizer entering a chamber with no fuel left destroys the motor, so the simulation stops rather than guessing at a trajectory afterwards. Any performance figures in this file are computed from a truncated run.",
        "console": "[ABORT] Catastrophic liquid quench detected. Execution stopped.",
    },
    "terminal_apogee_abort": {
        "code": "apogee_abort",
        "completed_nominally": False,
        "severity": "critical",
        "message": "Apogee was reached while the engine was still supposed to be firing. The vehicle went up and came back down mid-burn, which means the configuration is not flyable as written.",
        "console": "[ABORT] Apogee reached during powered ascent. Execution stopped.",
    },
    "terminal_phase_timeout": {
        "code": "phase_timeout",
        "completed_nominally": False,
        "severity": "critical",
        "message": "A phase ran out its phase_max_times budget without any transition event firing, so the run stops partway through. The state at that moment is real, but nothing after it exists.",
        "console": "[ABORT] A phase exceeded its time budget. Execution stopped.",
    },
}

_UNKNOWN_TERMINAL = {
    "code": "unknown",
    "completed_nominally": False,
    "severity": "critical",
    "message": "The simulation ended in a terminal state with no entry in TERMINAL_STATES. This is a bug in the engine, not in the rocket configuration.",
    "console": "[ABORT] Unrecognised terminal state. Execution stopped.",
}

# returns info corresponding to ending state or unknown state if not fonud
def terminal_state_info(terminal_state: str) -> dict:
    return TERMINAL_STATES.get(terminal_state, _UNKNOWN_TERMINAL)