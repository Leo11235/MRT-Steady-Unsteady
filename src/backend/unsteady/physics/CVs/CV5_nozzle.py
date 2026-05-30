"""
Handles nozzle flow regimes and mass flow calculations.
Returns the nozzle mass flow rate, exit velocity, and total thrust produced.
"""

import numpy as np
import math
from src.backend.unsteady.physics.CEA.CEA_interpolator import CEA_interpolation_lookup

################################# JOEL'S MODEL
def nozzle_joel_unsteady(t: float, state_vector: dict, rocket_inputs: dict, live: dict, constants: dict):
    
    # unpack values
    p_C = state_vector["p_C"]
    p_amb = live["p_amb"]
    r_t = rocket_inputs["nozzle_throat_radius_m"]
    r_e = rocket_inputs["nozzle_exit_radius_m"]
    R_u = constants["universal_gas_constant"]
    
    A_t = np.pi * r_t**2
    A_e = np.pi * r_e**2
    A_ratio = A_e / A_t
    
    # if chamber pressure drops below ambient, no thrust or mass flow can be generated
    # we add a 100 Pa buffer to prevent solver chatter right at the boundary
    if p_C <= p_amb + 100.0:
        return {
            "m_dot_n": 0.0,
            "F_thrust": 0.0,
            "p_e": p_amb,
            "v_e": 0.0,
            "M_e": 0.0,
            "flow_regime": "sub_ambient_cutoff"
        }

    m_o = state_vector["m_o"]
    m_f = state_vector["m_f"]
    
    # if the chamber has no gas yet, use realistic fallback parameters 
    if m_f < 1e-6 or m_o < 1e-6:
        OF = 7.0 
        T_c = rocket_inputs["tank_temperature_K"] 
        W_c = 0.029 
        gamma = 1.4 
        cstar = 1000.0
        dT_dOF, dT_dp, dW_dOF, dW_dp = 0.0, 0.0, 0.0, 0.0
    else:
        OF = m_o / m_f
        T_c, W_c, gamma, cstar, dT_dOF, dT_dp, dW_dOF, dW_dp = CEA_interpolation_lookup(OF, p_C)

    # If the chamber pressure hasn't significantly exceeded ambient, 
    # there is no meaningful flow or expansion yet.
    if p_C <= p_amb + 1000.0:
        return {
            "m_dot_n": 0.0, "F_thrust": 0.0, "p_e": p_amb,
            "M_e": 0.0, "v_e": 0.0, "flow_regime": "unstarted",
            # Dump the thermodynamics onto the live blackboard for CV4 to use!
            "OF": OF, "T_c": T_c, "W_c": W_c, "gamma": gamma, "cstar": cstar,
            "dT_dOF": dT_dOF, "dW_dOF": dW_dOF, "dT_dp": dT_dp, "dW_dp": dW_dp
        }

    # critical Mach and Pressure Calculations (ANALYTICAL BYPASS)
    G = (gamma + 1.0) / (2.0 * (gamma - 1.0))
    
    # subsonic M1 (Newton-Raphson)
    M_1 = 0.1 # robust initial guess
    for _ in range(10):
        term_inner = (2.0 / (gamma + 1.0)) * (1.0 + (gamma - 1.0) / 2.0 * M_1**2)
        F = (1.0 / M_1) * term_inner**G
        f = F - A_ratio
        dF_dM = -(1.0 / M_1**2) * term_inner**G + (1.0 / M_1) * G * term_inner**(G-1.0) * (2.0 / (gamma + 1.0)) * (gamma - 1.0) * M_1
        # Clip to prevent the solver from wandering into negative or supersonic territory
        M_1 = np.clip(M_1 - f / dF_dM, 0.0001, 0.9999)

    # supersonic M2x (Newton-Raphson)
    M_2x = 3.0 # robust initial guess
    for _ in range(10):
        term_inner = (2.0 / (gamma + 1.0)) * (1.0 + (gamma - 1.0) / 2.0 * M_2x**2)
        F = (1.0 / M_2x) * term_inner**G
        f = F - A_ratio
        dF_dM = -(1.0 / M_2x**2) * term_inner**G + (1.0 / M_2x) * G * term_inner**(G-1.0) * (2.0 / (gamma + 1.0)) * (gamma - 1.0) * M_2x
        # Clip to prevent the solver from wandering into subsonic territory
        M_2x = np.clip(M_2x - f / dF_dM, 1.0001, 15.0)

    # calculate critical pressures
    gamma_ratio = gamma / (gamma - 1.0)
    term_1 = (1.0 + (gamma - 1.0) / 2.0 * M_1**2) ** gamma_ratio
    term_2x = (1.0 + (gamma - 1.0) / 2.0 * M_2x**2) ** gamma_ratio
    
    p_1 = p_C / term_1
    p_2x = p_C / term_2x
    p_2 = p_2x * ((2.0 * gamma * M_2x**2 - (gamma - 1.0)) / (gamma + 1.0))
    
    sqrt_arg = (2.0 + (gamma - 1.0) * M_2x**2) / (2.0 * gamma * M_2x**2 - (gamma - 1.0))
    M_2 = np.sqrt(max(sqrt_arg, 1e-6))
    
    # regime determination
    TOL = 1e-3
    M_t = 1.0 
    flow_regime = "unknown"

    if p_2 >= p_1:
        p_e, M_e, M_t = p_amb, 0.0, 0.0
        flow_regime = "error_p2_p1"
    elif abs(p_amb - p_1) < TOL:
        p_e, M_e = p_amb, M_1
        flow_regime = "choked_subsonic_diverging"
    elif abs(p_amb - p_2) < TOL:
        p_e, M_e = p_amb, M_2
        flow_regime = "shock_at_exit"
    elif p_amb < p_2:
        p_e, M_e = p_2x, M_2x
        flow_regime = "fully_supersonic"
    elif p_2 < p_amb < p_1:
        p_e, M_e = p_amb, M_2 
        flow_regime = "shock_inside"
    elif p_amb > p_1:
        p_e, M_e, M_t = p_amb, M_1, M_1 
        flow_regime = "fully_subsonic"
    else:
        p_e, M_e = p_amb, 0.0
        flow_regime = "logic_error"

    # mass Flow and Thrust Calculation
    if M_t > 0.0:
        T_e = T_c / (1.0 + ((gamma - 1.0) / 2.0) * M_e**2)
        v_e = M_e * np.sqrt((gamma * R_u * T_e) / W_c)
        term_mdot = (1.0 + ((gamma - 1.0) / 2.0) * M_t**2) ** (-(gamma + 1.0) / (2.0 * (gamma - 1.0)))
        m_dot_n = A_t * p_C * M_t * np.sqrt((gamma * W_c) / (R_u * T_c)) * term_mdot
        F_thrust = (m_dot_n * v_e) + ((p_e - p_amb) * A_e)
    else:
        m_dot_n, v_e, F_thrust = 0.0, 0.0, 0.0

    return {
        "m_dot_n": m_dot_n, "F_thrust": max(F_thrust, 0.0), "p_e": p_e,
        "v_e": v_e, "M_e": M_e, "flow_regime": flow_regime,
        "OF": OF, "T_c": T_c, "W_c": W_c, "gamma": gamma, "cstar": cstar,
        "dT_dOF": dT_dOF, "dW_dOF": dW_dOF, "dT_dp": dT_dp, "dW_dp": dW_dp
    }


def nozzle_residual_blowdown(t: float, state_vector: dict, rocket_inputs: dict, live: dict, constants: dict) -> dict:
    """
    PHASE 4a & 4c: Non-Reacting Nozzle Discharge
    Uses frozen thermodynamic properties to calculate mass flow.
    Includes sub-ambient diode clamping and subsonic unchoking logic.
    """
    p_C = state_vector["p_C"]
    p_amb = live.get("p_amb", 101325.0)
    
    # if chamber pressure drops below ambient, force mass flow to 0 to prevent solver chatter
    if p_C <= p_amb + 100.0:
        return {
            "m_dot_n": 0.0,
            "F_thrust": 0.0,
            "p_e": p_amb,
            "v_e": 0.0,
            "M_e": 0.0,
            "flow_regime": "sub_ambient_cutoff"
        }
        
    # unpack Frozen Thermodynamics passed from RHS
    gamma = live.get("gamma", 1.15)
    W_c = live.get("W_c", 0.025)
    T_C = live.get("T_c", 3000.0)
    R_u = constants.get("universal_gas_constant", 8.314462618)
    R_spec = R_u / W_c
    
    # geometry
    r_t = rocket_inputs["nozzle_throat_radius_m"]
    A_t = math.pi * (r_t**2)
    
    # choking threshold
    p_crit = p_amb * ((gamma + 1) / 2.0)**(gamma / (gamma - 1))
    
    if p_C > p_crit:
        # REGIME A: Choked Flow
        Gamma = math.sqrt(gamma * (2.0 / (gamma + 1))**((gamma + 1) / (gamma - 1)))
        m_dot_n = (p_C * A_t * Gamma) / math.sqrt(R_spec * T_C)
        
        # Isentropic exit velocity (assuming shock separation effectively clamps pe to p_amb)
        v_e_ideal = math.sqrt(((2 * gamma) / (gamma - 1)) * R_spec * T_C * (1 - (p_amb / p_C)**((gamma - 1) / gamma)))
        F_thrust = m_dot_n * v_e_ideal
        p_e = p_amb
        flow_regime = "choked_residual"
        
    else:
        # REGIME B: Unchoked Subsonic Flow
        rho_C = p_C / (R_spec * T_C)
        
        # subsonic orifice mass flow equation
        m_dot_n = A_t * math.sqrt(2 * rho_C * (p_C - p_amb))
        
        # simplified momentum thrust for low delta-P
        v_e = math.sqrt(2 * (p_C - p_amb) / rho_C)
        F_thrust = m_dot_n * v_e
        p_e = p_amb
        flow_regime = "unchoked_subsonic"
        
    return {
        "m_dot_n": m_dot_n,
        "F_thrust": F_thrust,
        "p_e": p_e,
        "v_e": F_thrust / max(m_dot_n, 1e-9),
        "flow_regime": flow_regime
    }