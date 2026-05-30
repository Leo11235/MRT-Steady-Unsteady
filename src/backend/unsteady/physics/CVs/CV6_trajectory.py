"""
Handles rocket kinematics, partitioned by phase
"""

import numpy as np

####################### 2-DOF model
# helper function that calculates acceleration from forces
def _calculate_forces(t, state_vector, rocket_inputs, live, constants, F_thrust=0.0, C_d=None, A_ref=None):
    g = constants["sea_level_gravity"]
    W_o = constants["nitrous_oxide_molar_mass"]
    
    # kinematics
    vx_R = state_vector["vx_R"]
    vy_R = state_vector["vy_R"]
    v_mag = np.sqrt(vx_R**2 + vy_R**2)
    
    # mass
    m_total = rocket_inputs["rocket_dry_mass_kg"] + (state_vector["n_l"] + state_vector["n_v"]) * W_o + state_vector["m_o"] + state_vector["m_f"]
    
    # drag
    rho_amb = live["rho_amb"]
    C_d = C_d if C_d is not None else rocket_inputs["rocket_drag_coefficient"]
    A_ref = A_ref if A_ref is not None else rocket_inputs["rocket_frontal_area_m2"]
    D_mag = 0.5 * rho_amb * (v_mag**2) * C_d * A_ref
    
    D_x = D_mag * (vx_R / v_mag) if v_mag > 1e-6 else 0.0
    D_y = D_mag * (vy_R / v_mag) if v_mag > 1e-6 else 0.0
    
    # thrust
    theta_rad = np.radians(rocket_inputs["rocket_launch_angle_deg"])
    F_x = F_thrust * np.sin(theta_rad)
    F_y = F_thrust * np.cos(theta_rad)
    
    # Net forces
    F_net_x = F_x - D_x
    F_net_y = F_y - D_y - (m_total * g)
    
    # normal force guard (so the rocket doesn't fall in the first few ms)
    launch_asl = rocket_inputs.get("launch_site_altitude_asl_m", 0.0)
    is_on_pad = state_vector["sy_R"] <= launch_asl + 1e-4

    if is_on_pad and F_net_y < 0.0:
        ax_R = 0.0
        ay_R = 0.0
        vx_R = 0.0
        vy_R = 0.0
    else:
        ax_R = F_net_x / m_total
        ay_R = F_net_y / m_total

    return {
        # velocity
        "vx_R": vx_R, # x direction
        "vy_R": vy_R, # y direction
        # acceleration
        "ax_R": ax_R,
        "ay_R": ay_R
    }

# phases 1-4
def trajectory_powered_ascent(t, state_vector, rocket_inputs, live, constants):
    return _calculate_forces(t, state_vector, rocket_inputs, live, constants, 
                             F_thrust=live["F_thrust"])

# phase 5
def trajectory_coasting(t, state_vector, rocket_inputs, live, constants):
    return _calculate_forces(t, state_vector, rocket_inputs, live, constants, 
                             F_thrust=0.0)

# phase 6
def trajectory_drogue_descent(t, state_vector, rocket_inputs, live, constants):
    return _calculate_forces(t, state_vector, rocket_inputs, live, constants, 
                             F_thrust=0.0, 
                             C_d=rocket_inputs["drogue_parachute_drag_coefficient"], 
                             A_ref=rocket_inputs["drogue_parachute_frontal_area_m2"])

# phase 7
def trajectory_main_descent(t, state_vector, rocket_inputs, live, constants):
    return _calculate_forces(t, state_vector, rocket_inputs, live, constants, 
                             F_thrust=0.0, 
                             C_d=rocket_inputs["main_parachute_drag_coefficient"], 
                             A_ref=rocket_inputs["main_parachute_frontal_area_m2"])