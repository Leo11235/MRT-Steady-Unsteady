"""
The Right-Hand Side (RHS) master derivative functions for the ODE solver
Separated by flight phase to maintain continuous mathematics and optimize execution speed
"""

import math
from src.backend.unsteady.engine.objects import StateVector
from src.backend.unsteady.physics.atmosphere.atmosphere import get_atmosphere_properties
from src.backend.unsteady.physics.N2O_properties.N2O_properties import get_N2O_property

EVAL_COUNTER = 0 # global evaluation counter

# helpers
def _initialize_rhs_step(y):
    """Helper to initialize the derivatives dictionary and live state."""
    global EVAL_COUNTER
    EVAL_COUNTER += 1
    return StateVector.unpack(y), {var: 0.0 for var in StateVector.VARIABLES}, {}

def _eval_helper(t, state_vector, live, derivs):
    if EVAL_COUNTER % 100 == 0:
        thrust = live.get("F_thrust", 0.0)
        print(f"[Eval {EVAL_COUNTER:5d}] Sim Time: {t:6.4f}s | Tank P: {live.get('p_T', 0.0)/1e5:5.2f} bar | "
              f"Chamber P: {state_vector['p_C']/1e5:5.2f} bar | n_l: {state_vector['n_l']:6.1f} mol | n_v: {state_vector['n_v']:6.1f} | "
              f"dp_C_dt: {derivs.get('p_C', 0.0)/1e5:+6.1f} bar/s | Thrust: {thrust:6.1f} N")


# ==============================================================================
# PHASE 1: IGNITION & STARTUP
# ==============================================================================
def rhs_phase1_ignition(t: float, y: list, rocket_inputs: dict, cv_funcs: dict, constants: dict, phase_metadata: dict) -> list:
    state_vector, derivs, live = _initialize_rhs_step(y)
    
    live.update(get_atmosphere_properties(state_vector["sy_R"]))
    live["p_T"] = get_N2O_property("p", state_vector["T_T"])
    live["v_l"] = get_N2O_property("v_l", state_vector["T_T"])
    live["v_v"] = get_N2O_property("v_v", state_vector["T_T"])
    
    if cv_funcs.get("CV2_valve"): live.update(cv_funcs["CV2_valve"](t, state_vector, rocket_inputs, live, constants))
    if cv_funcs.get("CV3_injector"): live.update(cv_funcs["CV3_injector"](t, state_vector, rocket_inputs, live, constants))
    
    if cv_funcs.get("CV1_tank"):
        tank_out = cv_funcs["CV1_tank"](t, state_vector, rocket_inputs, live, constants)
        derivs["n_v"], derivs["n_l"], derivs["T_T"] = tank_out["dn_v_dt"], tank_out["dn_l_dt"], tank_out["dT_T_dt"]
    
    if cv_funcs.get("CV5_nozzle"): live.update(cv_funcs["CV5_nozzle"](t, state_vector, rocket_inputs, live, constants))
    
    if cv_funcs.get("CV4_chamber"):
        chamber_out = cv_funcs["CV4_chamber"](t, state_vector, rocket_inputs, live, constants)
        derivs["r_f"], derivs["m_o"], derivs["m_f"], derivs["p_C"] = chamber_out["dr_f_dt"], chamber_out["dm_o_dt"], chamber_out["dm_f_dt"], chamber_out["dp_C_dt"]
    
    if cv_funcs.get("CV6_trajectory"):
        traj_out = cv_funcs["CV6_trajectory"](t, state_vector, rocket_inputs, live, constants)
        derivs["sx_R"], derivs["sy_R"], derivs["vx_R"], derivs["vy_R"] = traj_out["vx_R"], traj_out["vy_R"], traj_out["ax_R"], traj_out["ay_R"] 
    
    _eval_helper(t, state_vector, live, derivs)
    
    return StateVector.to_array(derivs)


# ==============================================================================
# PHASE 2: LIQUID BLOWDOWN
# ==============================================================================
def rhs_phase2_liquid(t: float, y: list, rocket_inputs: dict, cv_funcs: dict, constants: dict, phase_metadata: dict) -> list:
    state_vector, derivs, live = _initialize_rhs_step(y)
    
    live.update(get_atmosphere_properties(state_vector["sy_R"]))
    live["p_T"] = get_N2O_property("p", state_vector["T_T"])
    live["v_l"] = get_N2O_property("v_l", state_vector["T_T"])
    live["v_v"] = get_N2O_property("v_v", state_vector["T_T"])
    
    if cv_funcs.get("CV2_valve"): live.update(cv_funcs["CV2_valve"](t, state_vector, rocket_inputs, live, constants))
    if cv_funcs.get("CV3_injector"): live.update(cv_funcs["CV3_injector"](t, state_vector, rocket_inputs, live, constants))
    
    if cv_funcs.get("CV1_tank"):
        tank_out = cv_funcs["CV1_tank"](t, state_vector, rocket_inputs, live, constants)
        derivs["n_v"], derivs["n_l"], derivs["T_T"] = tank_out["dn_v_dt"], tank_out["dn_l_dt"], tank_out["dT_T_dt"]
    
    if cv_funcs.get("CV5_nozzle"): live.update(cv_funcs["CV5_nozzle"](t, state_vector, rocket_inputs, live, constants))
    
    if cv_funcs.get("CV4_chamber"):
        chamber_out = cv_funcs["CV4_chamber"](t, state_vector, rocket_inputs, live, constants)
        derivs["r_f"], derivs["m_o"], derivs["m_f"], derivs["p_C"] = chamber_out["dr_f_dt"], chamber_out["dm_o_dt"], chamber_out["dm_f_dt"], chamber_out["dp_C_dt"]
    
    if cv_funcs.get("CV6_trajectory"):
        traj_out = cv_funcs["CV6_trajectory"](t, state_vector, rocket_inputs, live, constants)
        derivs["sx_R"], derivs["sy_R"], derivs["vx_R"], derivs["vy_R"] = traj_out["vx_R"], traj_out["vy_R"], traj_out["ax_R"], traj_out["ay_R"] 

    _eval_helper(t, state_vector, live, derivs)

    return StateVector.to_array(derivs)


# ==============================================================================
# PHASE 3: GASEOUS BLOWDOWN
# ==============================================================================
def rhs_phase3_gas(t: float, y: list, rocket_inputs: dict, cv_funcs: dict, constants: dict, phase_metadata: dict) -> list:
    state_vector, derivs, live = _initialize_rhs_step(y)
    
    live.update(get_atmosphere_properties(state_vector["sy_R"]))
    live["p_T"] = get_N2O_property("p", state_vector["T_T"])
    live["v_l"] = get_N2O_property("v_l", state_vector["T_T"])
    live["v_v"] = get_N2O_property("v_v", state_vector["T_T"])
    
    if cv_funcs.get("CV2_valve"): live.update(cv_funcs["CV2_valve"](t, state_vector, rocket_inputs, live, constants))
    if cv_funcs.get("CV3_injector"): live.update(cv_funcs["CV3_injector"](t, state_vector, rocket_inputs, live, constants))
    
    if cv_funcs.get("CV1_tank"):
        tank_out = cv_funcs["CV1_tank"](t, state_vector, rocket_inputs, live, constants)
        derivs["n_v"], derivs["n_l"], derivs["T_T"] = tank_out["dn_v_dt"], tank_out["dn_l_dt"], tank_out["dT_T_dt"]
    
    if cv_funcs.get("CV5_nozzle"): live.update(cv_funcs["CV5_nozzle"](t, state_vector, rocket_inputs, live, constants))
    
    if cv_funcs.get("CV4_chamber"):
        chamber_out = cv_funcs["CV4_chamber"](t, state_vector, rocket_inputs, live, constants)
        derivs["r_f"], derivs["m_o"], derivs["m_f"], derivs["p_C"] = chamber_out["dr_f_dt"], chamber_out["dm_o_dt"], chamber_out["dm_f_dt"], chamber_out["dp_C_dt"]
    
    if cv_funcs.get("CV6_trajectory"):
        traj_out = cv_funcs["CV6_trajectory"](t, state_vector, rocket_inputs, live, constants)
        derivs["sx_R"], derivs["sy_R"], derivs["vx_R"], derivs["vy_R"] = traj_out["vx_R"], traj_out["vy_R"], traj_out["ax_R"], traj_out["ay_R"] 
    
    _eval_helper(t, state_vector, live, derivs)

    return StateVector.to_array(derivs)


# ==============================================================================
# PHASE 4a & 4c: UNIFIED ENGINE SHUTDOWN
# ==============================================================================
def _rhs_engine_shutdown_base(t: float, y: list, rocket_inputs: dict, cv_funcs: dict, constants: dict, phase_metadata: dict) -> list:
    """Shared physics executor for Phase 4a (Vapor Purge) and Phase 4c (Dry Blowdown)."""
    state_vector, derivs, live = _initialize_rhs_step(y)
    
    # 1. Environment & Subsystems
    live.update(get_atmosphere_properties(state_vector["sy_R"]))
    live["p_T"] = get_N2O_property("p", state_vector["T_T"])
    live["v_l"] = get_N2O_property("v_l", state_vector["T_T"])
    live["v_v"] = get_N2O_property("v_v", state_vector["T_T"])
    
    # Let residual feed system keep flowing (In 4c, these cv_funcs will be None and skip safely)
    if cv_funcs.get("CV2_valve"): live.update(cv_funcs["CV2_valve"](t, state_vector, rocket_inputs, live, constants))
    if cv_funcs.get("CV3_injector"): live.update(cv_funcs["CV3_injector"](t, state_vector, rocket_inputs, live, constants))
    
    if cv_funcs.get("CV1_tank"):
        tank_out = cv_funcs["CV1_tank"](t, state_vector, rocket_inputs, live, constants)
        derivs["n_v"], derivs["n_l"], derivs["T_T"] = tank_out["dn_v_dt"], tank_out["dn_l_dt"], tank_out["dT_T_dt"]
    
    # 2. Extract Frozen Variables from Phase Metadata
    t_burnout = phase_metadata.get("t_burnout", 0.0)
    T_C_burnout = phase_metadata.get("T_c_burnout", 3000.0)
    W_c = phase_metadata.get("W_c_burnout", 0.025)
    gamma = phase_metadata.get("gamma_burnout", 1.15)
    
    # Target Temperature (Ambient or Feed)
    T_feed = 290.0 if state_vector["n_v"] <= 0.0 else state_vector["T_T"]
    
    # 3. Dynamic Residence Time (Tau) Calculation
    if "nozzle_throat_radius_m" in rocket_inputs:
        r_t = rocket_inputs["nozzle_throat_radius_m"]
    else:
        r_t = rocket_inputs.get("nozzle_throat_diameter_m", 0.05) / 2.0
        
    A_t = math.pi * (r_t**2)
    R_spec = constants.get("universal_gas_constant", 8.31446) / W_c
    Gamma = math.sqrt(gamma * (2.0 / (gamma + 1))**((gamma + 1) / (gamma - 1)))
    
    V_C = math.pi * (state_vector["r_f"]**2) * rocket_inputs["chamber_fuel_length_m"]
    T_C_safe = max(T_C_burnout, 1.0)
    
    tau = max(V_C / (A_t * Gamma * math.sqrt(R_spec * T_C_safe)), 0.001)
    
    # 4. The Exponential Flush
    dt_phase = max(t - t_burnout, 0.0)
    T_C_current = T_feed + (T_C_burnout - T_feed) * math.exp(-dt_phase / tau)
    dT_C_dt = -(1.0 / tau) * (T_C_burnout - T_feed) * math.exp(-dt_phase / tau)
    
    # Inject frozen properties and dynamic temp into live for CV4 and CV5 to read
    live["T_c"] = T_C_current
    live["dT_c_dt"] = dT_C_dt
    live["W_c"] = W_c
    live["gamma"] = gamma
    
    # 5. Boundary & State Assembly
    if cv_funcs.get("CV5_nozzle"): live.update(cv_funcs["CV5_nozzle"](t, state_vector, rocket_inputs, live, constants))
    
    if cv_funcs.get("CV4_chamber"):
        chamber_out = cv_funcs["CV4_chamber"](t, state_vector, rocket_inputs, live, constants)
        derivs["m_o"], derivs["m_f"], derivs["p_C"] = chamber_out["dm_o_dt"], chamber_out["dm_f_dt"], chamber_out["dp_C_dt"]
    derivs["r_f"] = 0.0 # Force no regression
    
    if cv_funcs.get("CV6_trajectory"):
        traj_out = cv_funcs["CV6_trajectory"](t, state_vector, rocket_inputs, live, constants)
        derivs["sx_R"], derivs["sy_R"], derivs["vx_R"], derivs["vy_R"] = traj_out["vx_R"], traj_out["vy_R"], traj_out["ax_R"], traj_out["ay_R"] 
    
    _eval_helper(t, state_vector, live, derivs)

    return StateVector.to_array(derivs)

def rhs_phase4a_vapor_purge(t: float, y: list, rocket_inputs: dict, cv_funcs: dict, constants: dict, phase_metadata: dict) -> list:
    return _rhs_engine_shutdown_base(t, y, rocket_inputs, cv_funcs, constants, phase_metadata)

def rhs_phase4c_dry_blowdown(t: float, y: list, rocket_inputs: dict, cv_funcs: dict, constants: dict, phase_metadata: dict) -> list:
    return _rhs_engine_shutdown_base(t, y, rocket_inputs, cv_funcs, constants, phase_metadata)


# ==============================================================================
# PHASE 5, 6, 7: BALLISTIC & DESCENT PHASES
# ==============================================================================
def _rhs_ballistic_descent_base(t: float, y: list, rocket_inputs: dict, cv_funcs: dict, constants: dict, phase_metadata: dict) -> list:
    """Shared underlying kinematic evaluation for Phases 5, 6, and 7."""
    state_vector, derivs, live = _initialize_rhs_step(y)
    
    live.update(get_atmosphere_properties(state_vector["sy_R"]))
    live["F_thrust"] = 0.0
    
    # Only Trajectory evaluates. Tank, valve, injector, chamber, nozzle are frozen.
    if cv_funcs.get("CV6_trajectory"):
        traj_out = cv_funcs["CV6_trajectory"](t, state_vector, rocket_inputs, live, constants)
        derivs["sx_R"], derivs["sy_R"], derivs["vx_R"], derivs["vy_R"] = traj_out["vx_R"], traj_out["vy_R"], traj_out["ax_R"], traj_out["ay_R"] 
    
    _eval_helper(t, state_vector, live, derivs)

    return StateVector.to_array(derivs)

def rhs_phase5_coast(t: float, y: list, rocket_inputs: dict, cv_funcs: dict, constants: dict, phase_metadata: dict) -> list:
    return _rhs_ballistic_descent_base(t, y, rocket_inputs, cv_funcs, constants, phase_metadata)

def rhs_phase6_drogue_descent(t: float, y: list, rocket_inputs: dict, cv_funcs: dict, constants: dict, phase_metadata: dict) -> list:
    return _rhs_ballistic_descent_base(t, y, rocket_inputs, cv_funcs, constants, phase_metadata)

def rhs_phase7_main_descent(t: float, y: list, rocket_inputs: dict, cv_funcs: dict, constants: dict, phase_metadata: dict) -> list:
    return _rhs_ballistic_descent_base(t, y, rocket_inputs, cv_funcs, constants, phase_metadata)