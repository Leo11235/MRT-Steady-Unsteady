from src.backend.steady.prop_calculations import calculate_air_density, calculate_gravity
from math import pi, cos, radians

def simulate_rocket_ascent(rocket_inputs, rocket_parameters, simulation_settings, constants_dict):
    # setup variables
    dt = rocket_parameters["burntime"] / constants_dict["number_of_timesteps"]
    t_burn = rocket_parameters["burntime"]
    m_dot = rocket_parameters["total_propellant_mass_flow_rate"]
    m_0 = rocket_parameters["wet_mass"]
    h_0 = rocket_inputs["launch_site_altitude"]
    
    launch_angle_rad = radians(rocket_inputs["launch_angle"])
    vertical_thrust = rocket_parameters["thrust"] * cos(launch_angle_rad)
    
    # drag constant
    A_ref = pi * (rocket_inputs["rocket_external_radius"])**2
    drag_constant = 0.5 * rocket_inputs["drag_coefficient"] * A_ref
    
    ##