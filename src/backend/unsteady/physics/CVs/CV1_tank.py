"""
Handles tank physics. Tank physics active in phases 1-4
"""

import numpy as np
from src.backend.unsteady.physics.N2O_properties.N2O_properties import get_N2O_property
from src.backend.unsteady.physics.CEA.CEA_interpolator import CEA_interpolation_lookup

############################ JOEL'S MODEL
# phases 1 & 2
def tank_liquid_blowdown(t: float, state_vector: dict, rocket_inputs: dict, live: dict, constants: dict):
    """
    Nominal liquid-phase tank model used in phases 1 and 2. 
    Assumptions: 
        - saturated liquid-vapor equilibrium in the tank
        - n_dot_ox has already been computed upstream
    """
    
    # unpack values
    n_v = state_vector["n_v"]
    n_l = state_vector["n_l"]
    T_T = state_vector["T_T"]
    n_dot_ox = live["n_dot_ox"]
    
    # get saturated N2O properties at the current tank temperature
    p_T = get_N2O_property("p", T_T)
    v_l = get_N2O_property("v_l", T_T)
    v_v = get_N2O_property("v_v", T_T)

    u_l = get_N2O_property("u_l", T_T)
    u_v = get_N2O_property("u_v", T_T)
    h_l = get_N2O_property("h_l", T_T)

    dv_l_dT = get_N2O_property("d_v_l/d_T", T_T)
    dv_v_dT = get_N2O_property("d_v_v/d_T", T_T)

    du_l_dT = get_N2O_property("d_u_l/d_T", T_T)
    du_v_dT = get_N2O_property("d_u_v/d_T", T_T)
    
    # solve linear system A*x=b
    A = np.array([
        [1.0,    1.0,                0.0              ],
        [v_v,    v_l,    n_v * dv_v_dT + n_l * dv_l_dT],
        [u_v,    u_l,    n_v * du_v_dT + n_l * du_l_dT],
    ], dtype=float)
    b = np.array([
        -n_dot_ox,
        0.0,
        -n_dot_ox * h_l,
    ], dtype=float)
    
    dn_v_dt, dn_l_dt, dT_T_dt = np.linalg.solve(A, b)
    
    return {
        "dn_v_dt": dn_v_dt, # time derivative of tank vapor molar amount [mol/s]
        "dn_l_dt": dn_l_dt, # time derivative of tank liquid molar amount [mol/s]
        "dT_T_dt": dT_T_dt, # time derivative of tank temperature [K/s]
        "p_T": p_T, # tank pressure [Pa]
        "v_l": v_l, # liquid molar volume [m^3/mol]
        "v_v": v_v, # vapor molar volume [m^3/mol]
        # optional but useful:
        "u_l": u_l, # liquid molar internal energy [J/mol]
        "u_v": u_v, # vapor molar internal energy [J/mol]
        "h_l": h_l, # liquid molar enthalpy of discharged oxidizer [J/mol]
    }

# phase 3
def tank_gaseous_blowdown(t: float, state_vector: dict, rocket_inputs: dict, live: dict, constants: dict):
    """
    Nominal gaseous blowdown tank model used in phase 3.
    Assumptions:
        - vapor-only oxidizer in the tank
        - n_dot_ox has already been computed upstream
        - tank liquid N2O is depleted
    """
    
    # unpack values
    n_v = state_vector["n_v"]
    T_T = state_vector["T_T"]
    n_dot_ox = live["n_dot_ox"]
    R_u = constants["universal_gas_constant"]
    
    # get saturated gas-phase N2O properties at the current tank temperature
    v_v = get_N2O_property("v_v", T_T)
    Z = get_N2O_property("Z", T_T)
    c_p_v = get_N2O_property("c_p_v", T_T)
    c_v_v = get_N2O_property("c_v_v", T_T)
    
    # effective polytropic exponent
    m = c_p_v / c_v_v
    
    # state derivatives
    dn_v_dt = -n_dot_ox # derivative of oxidizer remaining in the tank is the inverse of the oxidizer leaving the tank
    dn_l_dt = 0.0 # no liquid at this stage
    
    # if there is vapor remaining in the tank and leaving it, the tank temperature is dropping
    if n_v > 0.0:
        dT_T_dt = T_T * (m - 1.0) * dn_v_dt / n_v
    else:
        dT_T_dt = 0.0
    
    # tank pressure
    p_T = (Z * R_u * T_T) / v_v
    
    return {
        "dn_v_dt": dn_v_dt, # time derivative of tank vapor molar amount [mol/s]
        "dn_l_dt": dn_l_dt, # time derivative of tank liquid molar amount [mol/s]
        "dT_T_dt": dT_T_dt, # time derivative of tank temperature [K/s]
        "p_T": p_T, # tank pressure [Pa]
        "v_v": v_v, # vapor molar volume [m^3/mol]
        # optional but useful:
        "Z": Z, # vapor compressibility factor [-]
        "c_p_v": c_p_v, # vapor heat capacity at constant pressure [J/(mol-K)]
        "c_v_v": c_v_v, # vapor heat capacity at constant volume [J/(mol-K)]
        "m": m, # effective polytropic exponent [-]
    }

# tank not called for phases 5+
