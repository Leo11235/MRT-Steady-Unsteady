"""
Handles the calculation of the t=0 initial state vector
"""

import json
import re
import numpy
import math
from pathlib import Path
_ENGINE_DIR = Path(__file__).resolve().parent
_STATIC_DATA_DIR = _ENGINE_DIR.parent / "static_data"

def initialize_natural_constants_dict():
    """
    Returns a dict of natural constants used throughout the simulation.
    """
    # find and open file
    file = _STATIC_DATA_DIR / "natural_constants.jsonc"
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    # remove comments
    cleaned = re.sub(r'//.*', '', content)
    cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
    # parse cleaned file into dict
    constants_dict = json.loads(cleaned)
    return constants_dict


def initialize_state_vector(rocket_inputs: dict, constants_dict: dict, get_N2O_property: callable) -> dict:
    """
    Initializes the state vector using either ullage fraction or tank internal length.
    """
    # INITIALIZE CV1: tank state variables [n_v, n_l, T_T]
    # initialize saturated N2O properties
    T_T_0 = rocket_inputs['tank_temperature']
    v_l = get_N2O_property('v_l', T_T_0) 
    v_v = get_N2O_property('v_v', T_T_0) 
    
    m_o_tot_0 = rocket_inputs["tank_oxidizer_mass"]
    W_o = constants_dict["nitrous_oxide_molar_mass"]
    
    # Convert schema radii to diameters for the matrix math
    d_T = rocket_inputs["tank_internal_radius"] * 2.0
    D_dt = rocket_inputs["dip_tube_external_radius"] * 2.0
    d_dt = rocket_inputs["dip_tube_internal_radius"] * 2.0
    
    # decide whether to initialize tank variables using ullage or tank length
    if "tank_internal_length" in rocket_inputs:
        V_l, n_l, n_v, V_V, L_dt = initialize_state_vector_using_tank_length(rocket_inputs, v_l, v_v, m_o_tot_0, W_o, d_T, D_dt, d_dt)
    elif "tank_ullage_fraction" in rocket_inputs:
        V_l, n_l, n_v, L_T, L_dt = initialize_state_vector_using_ullage(rocket_inputs, v_l, v_v, m_o_tot_0, W_o, d_T, D_dt, d_dt)
        rocket_inputs["tank_internal_length"] = float(L_T)
    
    # INITIALIZE CV4: combustion chamber variables [r_f, m_o, m_f, p_C]
    L_f = rocket_inputs["chamber_fuel_length"]
    R_f = rocket_inputs["chamber_fuel_external_radius"]
    
    # get or calculate internal fuel radius
    if "chamber_fuel_internal_radius" in rocket_inputs:
        r_f = rocket_inputs["chamber_fuel_internal_radius"]
    else:
        m_f_tot = rocket_inputs["chamber_fuel_mass"]
        p_f = rocket_inputs["chamber_fuel_density"]
        r_f = math.sqrt(R_f**2 - m_f_tot/(math.pi*p_f*L_f)) 
        
    m_f = 0.0 # initial fuel in the chamber gas
    m_o = 0.0 # initial oxidizer in the chamber gas
    p_C = constants_dict["ambient_sea_level_atmospheric_pressure"]
    
    return {
        'n_v': float(n_v),  
        'n_l': float(n_l),  
        'T_T': T_T_0, 
        'm_o': m_o,  
        'm_f': m_f,  
        'p_C': p_C,  
        'r_f': r_f,  
        'sx_R': 0.0, 
        'sy_R': rocket_inputs["launch_site_altitude_asl"], 
        'vx_R': 0.0, 
        'vy_R': 0.0  
    }

def initialize_state_vector_using_ullage(rocket_inputs, v_l, v_v, m_o_tot_0, W_o, d_T, D_dt, d_dt):
    """
    Uses tank ullage factor to initialize the state vector.
    """
    # get rocket ullage    
    U = rocket_inputs["tank_ullage_fraction"]
    
    # need to solve for x in the A*x=b system below
    A = numpy.array([
        [0,             1,      1,       0,          0                         ],
        [-1,            v_l,    0,       0,          0                         ],
        [-U,            0,      v_v,     0,          0                         ],
        [-4*U/math.pi,  0,      0,       0,          d_T**2 - D_dt**2 + d_dt**2],
        [-4/math.pi,    0,      0,       d_T**2,    -d_T**2                    ]
    ])
    b = numpy.array([m_o_tot_0/W_o,   0, 0, 0, 0])    
    
    # solve the system Ax=b for x
    V_l, n_l, n_v, L_T, L_dt = numpy.linalg.solve(A, b)
    
    return V_l, n_l, n_v, L_T, L_dt

def initialize_state_vector_using_tank_length(rocket_inputs, v_l, v_v, m_o_tot_0, W_o, d_T, D_dt, d_dt):
    """
    Uses tank length to initialize the state vector.
    """
    # unpack rocket length
    L_T = rocket_inputs["tank_internal_length"]
    
    # do the lin alg stuff
    A = numpy.array([
        [0,         1,     1,      0,              0                         ], 
        [-1,        v_l,   0,      0,              0                         ], 
        [0,         0,     v_v,   -1,              0                         ], 
        [0,         0,     0,      -4/math.pi,     d_T**2 - D_dt**2 + d_dt**2], 
        [4/math.pi, 0,     0,      0,              d_T**2                    ]
    ])
    b = numpy.array([m_o_tot_0/W_o,  0, 0, 0, d_T**2 * L_T])
    
    V_l, n_l, n_v, V_V, L_dt = numpy.linalg.solve(A, b)
    
    return V_l, n_l, n_v, V_V, L_dt

def compute_rocket_variables(rocket_inputs):
    """
    Used to compute certain rocket variables such as parachute area, injector hole area, etc, used in the rest of the simulation
    """
    # areas
    rocket_inputs["injector_hole_area"] = math.pi * rocket_inputs["injector_hole_radius"] ** 2
    rocket_inputs["drogue_parachute_frontal_area"] = math.pi * rocket_inputs["drogue_parachute_radius"] ** 2
    rocket_inputs["main_parachute_frontal_area"] = math.pi * rocket_inputs["main_parachute_radius"] ** 2
    rocket_inputs["rocket_frontal_area"] = math.pi * rocket_inputs["rocket_outer_radius"] ** 2
    # volumes
    rocket_inputs["pre_chamber_volume"] = math.pi * rocket_inputs["pre_chamber_radius"] ** 2 * rocket_inputs["pre_chamber_length"]
    rocket_inputs["post_chamber_volume"] = math.pi * rocket_inputs["post_chamber_radius"] ** 2 * rocket_inputs["post_chamber_length"]
    
    return rocket_inputs