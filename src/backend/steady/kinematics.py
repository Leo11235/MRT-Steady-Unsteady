from src.backend.steady.prop_calculations import calculate_air_density, calculate_gravity
from math import pi, cos, radians

def simulate_rocket_ascent(rocket_inputs, rocket_parameters, simulation_settings, constants_dict):
    # setup variables
    dt = rocket_parameters["burntime"] / simulation_settings["number_of_timesteps"]
    t_burn = rocket_parameters["burntime"]
    m_dot = rocket_parameters["total_propellant_mass_flow_rate"]
    m_0 = rocket_parameters["wet_mass"]
    h_0 = rocket_inputs["launch_site_altitude"]
    
    launch_angle_rad = radians(rocket_inputs["launch_angle"])
    vertical_thrust = rocket_parameters["thrust"] * cos(launch_angle_rad)
    
    # drag constant
    A_ref = pi * (rocket_inputs["rocket_external_radius"])**2
    drag_constant = 0.5 * rocket_inputs["drag_coefficient"] * A_ref
    
    # initialize flight dict
    init_grav = -1.0 * m_0 * calculate_gravity(constants_dict, h_0)
    init_net = vertical_thrust + init_grav
    flight_dict = {
        "time": [0.0],
        "thrust": [vertical_thrust],
        "drag_force": [0.0],
        "grav_force": [init_grav],
        "net_force": [init_net],
        "mass": [m_0],
        "acceleration": [init_net / m_0],
        "velocity": [0.0],
        "altitude": [h_0]
    }
    t = 0.0
    
    # execution loop (runs until velocity drops to 0)
    while flight_dict["velocity"][-1] >= 0.0:
        t += dt
        
        # fetch previous state
        v_prev = flight_dict["velocity"][-1]
        h_prev = flight_dict["altitude"][-1]
        
        # evaluate current state
        if t <= t_burn + 1e-9: 
            current_thrust = vertical_thrust
            current_mass = m_0 - m_dot * t
        else:
            current_thrust = 0.0
            current_mass = m_0 - m_dot * t_burn
        
        # evaluate environmental forces
        rho = calculate_air_density(h_prev)
        g = calculate_gravity(constants_dict, h_prev)
        
        drag = drag_constant * rho * (v_prev**2) * -1.0 
        grav = -1.0 * current_mass * g
        
        # evaluate kinematics
        net_force = current_thrust + drag + grav
        a_new = net_force / current_mass
        v_new = v_prev + a_new * dt
        h_new = h_prev + v_new * dt
        
        # log data
        flight_dict["time"].append(t)
        flight_dict["thrust"].append(current_thrust)
        flight_dict["drag_force"].append(drag)
        flight_dict["grav_force"].append(grav)
        flight_dict["net_force"].append(net_force)
        flight_dict["mass"].append(current_mass)
        flight_dict["acceleration"].append(a_new)
        flight_dict["velocity"].append(v_new)
        flight_dict["altitude"].append(h_new)
    
    return flight_dict