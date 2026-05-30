"""
Handles combustion chamber models for the unsteady solver.

All chamber functions return a dictionary containing the state variable derivatives:
    - dr_f_dt [m/s]
    - dm_o_dt [kg/s]
    - dm_f_dt [kg/s]
    - dp_C_dt [Pa/s]

As well as useful diagnostic metrics like O/F ratio, intermediate mass flows, and geometry.
"""

import numpy as np
import math


################################### JOEL'S MODEL
# phases 1, 2, 3: unsteady combustion chamber
def chamber_joel_unsteady(t: float, state_vector: dict, rocket_inputs: dict, live: dict, constants: dict):
    """
    Joel's unsteady combustion chamber model, active throughout all burn phases.
    Assumptions:
        - Quasi-steady chemical equilibrium (CEA properties evaluate instantly at current P and O/F)
        - Uniform 1D radial fuel regression
        - Chamber gas mixture is perfectly mixed
        - m_dot_n has already been computed downstream by the nozzle CV to avoid numerical lag
    """
    
    # unpack values
    r_f = state_vector["r_f"]
    m_o = state_vector["m_o"]
    m_f = state_vector["m_f"]
    p_C = state_vector["p_C"]
    n_dot_ox = live["n_dot_ox"]
    m_dot_n = live["m_dot_n"]
    T_c = live["T_c"]
    W_c = live["W_c"]
    gamma = live["gamma"]
    dT_dOF = live["dT_dOF"]
    dW_dOF = live["dW_dOF"]
    dT_dp = live["dT_dp"]
    dW_dp = live["dW_dp"]
    OF = live["OF"]
    chamber_fuel_density = rocket_inputs["chamber_fuel_density_kgm3"]
    chamber_fuel_length = rocket_inputs["chamber_fuel_length_m"]
    chamber_regression_rate_a = rocket_inputs["chamber_regression_rate_scaling_constant"]
    chamber_regression_rate_n = rocket_inputs["chamber_regression_rate_exponent"]
    pre_chamber_volume = rocket_inputs["pre_chamber_volume_m3"]
    post_chamber_volume = rocket_inputs["post_chamber_volume_m3"]
    W_o = constants["nitrous_oxide_molar_mass"]
    R_u = constants["universal_gas_constant"]
    
    # avoid division by zero on the first frame before regression starts
    r_f_safe = max(r_f, 1e-10) 
    
    # oxidizer mass flow IN
    m_dot_o_in = W_o * n_dot_ox
    
    # fuel regression rate (dr_f/dt)
    dr_f_dt = chamber_regression_rate_a * ((m_dot_o_in) / (np.pi * r_f_safe**2)) ** chamber_regression_rate_n
    
    # fuel mass flow IN
    m_dot_f_in = chamber_fuel_density * 2.0 * np.pi * r_f_safe * chamber_fuel_length * dr_f_dt

    # mass flow OUT (split the total nozzle flow into oxidizer and fuel components based on current mixture)
    if m_dot_n > 0.0 and OF > 0.0:
        m_dot_o_out = m_dot_n / (1.0 + 1.0 / OF)
        m_dot_f_out = m_dot_n / (1.0 + OF)
    else:
        m_dot_o_out = 0.0
        m_dot_f_out = 0.0

    # chamber mass storage derivatives
    dm_o_dt = m_dot_o_in - m_dot_o_out
    dm_f_dt = m_dot_f_in - m_dot_f_out
    
    # current chamber volume and its derivative
    V_c = pre_chamber_volume + post_chamber_volume + (np.pi * r_f_safe**2 * chamber_fuel_length)
    dV_c_dt = 2.0 * np.pi * r_f_safe * chamber_fuel_length * dr_f_dt

    # total gas mass inside the chamber and its derivative
    m_c = m_o + m_f
    dm_c_dt = m_dot_o_in + m_dot_f_in - m_dot_n

    # derivative of O/F ratio (WITH PHYSICAL BOUNDS)
    if m_f > 1e-5:
        dOF_dt = (1.0 / m_f) * (dm_o_dt - OF * dm_f_dt)
        # Physically bound the rate of change to prevent numerical explosions.
        dOF_dt = np.clip(dOF_dt, -50.0, 50.0)
    else:
        dOF_dt = 0.0

    # chamber pressure derivative (dp_C/dt) (most error prone part)
    # calculate Equation A: Nominal Unsteady Pressure Derivative
    m_c_safe = max(m_c, 1e-4) # Prevent division-by-near-zero from solver step exploration
    numerator = (dm_c_dt / m_c_safe) - (dV_c_dt / V_c) + dOF_dt * ((dT_dOF / T_c) + (dW_dOF / W_c))
    
    # grid boundary safeguard (if you haven't added the clipping bounds here yet):
    thermal_slope_term = np.clip(dT_dp / T_c, -0.15 / p_C, 0.15 / p_C)
    molar_slope_term = np.clip(dW_dp / W_c, -0.15 / p_C, 0.15 / p_C)
    denominator = (1.0 / p_C) - thermal_slope_term + molar_slope_term
    
    dp_C_dt_unsteady = numerator / denominator

    # calculate Equation B: Damped Ideal Gas Fill-up Phase Derivative
    dm_dt_fill = m_dot_o_in + m_dot_f_in - m_dot_n
    dp_C_dt_fill = dm_dt_fill * (R_u / W_c) * (T_c / V_c)

    # compute blending facgtor (Smooth Sigmoid Transition based on mass)
    # center the transition around m_c = 5e-4 kg with a smooth scaling width
    mass_center = 5e-4  # kg
    mass_transition_width = 1e-4  # kg
    
    # Sigmoid function: smoothly climbs from 0 to 1 as mass accumulates
    alpha = 1.0 / (1.0 + np.exp(-(m_c - mass_center) / mass_transition_width))

    # blend the derivatives continuously to avoid step-discontinuities
    dp_C_dt = (1.0 - alpha) * dp_C_dt_fill + alpha * dp_C_dt_unsteady

    return {
        "dr_f_dt": dr_f_dt, # rate of change of fuel grain internal radius [m/s]
        "dm_o_dt": dm_o_dt, # rate of change of oxidizer mass in the chamber [kg/s]
        "dm_f_dt": dm_f_dt, # rate of change of fuel mass in the chamber [kg/s]
        "dp_C_dt": dp_C_dt, # rate of change of combustion chamber pressure [Pa/s]
        
        "OF": OF, # instantaneous oxidizer-to-fuel ratio inside the chamber [-]
        "dOF_dt": dOF_dt, # rate of change of O/F ratio [1/s]
        "m_dot_o_in": m_dot_o_in, # oxidizer mass flow rate entering chamber [kg/s]
        "m_dot_f_in": m_dot_f_in, # fuel mass flow rate entering chamber via regression [kg/s]
        "m_dot_o_out": m_dot_o_out, # oxidizer mass flow rate exiting chamber via nozzle [kg/s]
        "m_dot_f_out": m_dot_f_out, # fuel mass flow rate exiting chamber via nozzle [kg/s]
        "m_c": m_c, # total gas mass in the chamber [kg]
        "V_c": V_c, # current chamber volume [m^3]
        "T_c": T_c, # chamber flame temperature [K]
        "W_c": W_c, # chamber gas molecular weight [kg/mol]
        "gamma": gamma # chamber gas heat capacity ratio [-]
    }

# Phase 4a & 4c model for computing non-combusting residual blowdown
def chamber_residual_blowdown(t: float, state_vector: dict, rocket_inputs: dict, live: dict, constants: dict) -> dict:
    """
    PHASE 4a & 4c: Non-Combusting Residual Blowdown
    Calculates chamber pressure decay using the differentiated ideal gas law.
    Handles continuous mass tracking for vapor purges (4a) and dry blowdowns (4c).
    """
    R_u = constants["universal_gas_constant"]
    W_o = constants["nitrous_oxide_molar_mass"]
    
    # Read frozen thermodynamics and dynamic temperature passed down from RHS
    W_c = live.get("W_c", 0.025)
    T_C = live.get("T_c", 3000.0) 
    dT_C_dt = live.get("dT_c_dt", 0.0)
    
    # Read current state masses (clamped to prevent division by zero)
    m_o = max(state_vector["m_o"], 1e-9)
    m_f = max(state_vector["m_f"], 1e-9)
    m_C = m_o + m_f
    
    # Read boundary flows
    # Safe .get() ensures Phase 4c (where CV3 is disabled) naturally evaluates to 0.0
    n_dot_ox = live.get("n_dot_ox", 0.0) 
    m_dot_in = n_dot_ox * W_o # Inflow from injector [kg/s]
    m_dot_out = live.get("m_dot_n", 0.0) # Outflow from nozzle [kg/s]
    
    # Calculate fixed chamber volume (frozen at burnout)
    r_f = state_vector["r_f"]
    L_f = rocket_inputs["chamber_fuel_length_m"]
    V_C = math.pi * (r_f**2) * L_f
    
    # --- MASS DERIVATIVES ---
    # Gas leaves proportionally to its mass fraction in the chamber mixture
    f_o = m_o / m_C
    f_f = m_f / m_C
    
    dm_o_dt = m_dot_in - (m_dot_out * f_o)
    dm_f_dt = 0.0 - (m_dot_out * f_f)
    dm_C_dt = dm_o_dt + dm_f_dt
    
    # --- PRESSURE DERIVATIVE ---
    # Differentiated ideal gas law: pV = mRT -> dp/dt = (R/WV) * [ (dm/dt)T + m(dT/dt) ]
    dp_C_dt = (R_u / (W_c * V_C)) * (dm_C_dt * T_C + m_C * dT_C_dt)
    
    return {
        "dr_f_dt": 0.0, # Combustion is halted
        "dm_o_dt": dm_o_dt,
        "dm_f_dt": dm_f_dt,
        "dp_C_dt": dp_C_dt
    }

