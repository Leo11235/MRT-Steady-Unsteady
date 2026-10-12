"""
Handles injector flow models for the unsteady solver.

All injector functions return oxidizer molar flow rate:
    - n_dot_ox [mol/s]

Valve effects are applied here by multiplying the fully-open injector flow by valve_open_fraction:
    - n_dot_ox = valve_open_fraction * n_dot_ox_ideal
"""

import numpy as np


################################### JOEL'S MODEL
# phases 1 & 2: liquid blowdown
def injector_joel_liquid_blowdown(t: float, state_vector: dict, rocket_inputs: dict, live: dict, constants: dict):    
    """
    Joel's injector model for liquid-phase blowdown, used in phases 1 and 2
    Assumptions:
        - oxidizer upstream of the injector is liquid
        - injector flow is computed from the Joel liquid blowdown relation
        - valve effects are applied as a multiplicative throttling factor on the fully-open flow
        - if the effective pressure drop is nonpositive, injector flow is zero
    """
    # unpack values
    p_C = state_vector["p_C"]
    p_T = live["p_T"]
    v_l = live["v_l"]
    valve_open_fraction = live["valve_open_fraction"]
    injector_discharge_coefficient = rocket_inputs["injector_discharge_coefficient"]
    injector_number_of_holes = rocket_inputs["injector_number_of_holes"]
    injector_hole_area_m2 = rocket_inputs["injector_hole_area"]
    feed_pressure_loss = rocket_inputs["feed_pressure_loss"]
    W_o = constants["nitrous_oxide_molar_mass"]

    # effective pressure drop across the injector/feed system
    delta_p = p_T - feed_pressure_loss - p_C

    # define a small transition region (e.g., 0.1 bar = 10,000 Pa)
    # this is small enough to not affect nominal 50-psi operation, but large enough to stabilize the solver.
    dp_transition = 10000.0 

    ##### Nominal region (standard square root)
    if delta_p > dp_transition:
        n_dot_ox_ideal = (injector_discharge_coefficient * injector_number_of_holes * injector_hole_area_m2 * np.sqrt(2.0 * delta_p / (W_o * v_l)))

    ##### transition region
    elif delta_p > 0.0:
        # flow at transition point
        f_trans = (injector_discharge_coefficient * injector_number_of_holes * injector_hole_area_m2 * np.sqrt(2.0 * dp_transition / (W_o * v_l)))
        
        # quadratic through the origin that also meets the sqrt branch in both value and slope at dp_transition
        # g(0) = 0 (no flow at no pressure drop)
        # g(dp_t) = f_trans (continuous with the sqrt)
        # g'(dp_t) = 0.5 * f_trans / dp_t (same slope as the sqrt)
        # solving those gives the constants below:
        a = -0.5 * f_trans / (dp_transition**2)
        b = 1.5 * f_trans / dp_transition
        c = 0.0
        
        n_dot_ox_ideal = a * delta_p**2 + b * delta_p + c
    
    ###### dead zone
    else:
        n_dot_ox_ideal = 0.0

    # actual injector flow after valve throttling
    n_dot_ox = valve_open_fraction * n_dot_ox_ideal

    return {
        "n_dot_ox": n_dot_ox, # actual oxidizer molar flow rate [mol/s]
        "n_dot_ox_ideal": n_dot_ox_ideal, # fully-open oxidizer molar flow rate before valve throttling [mol/s]
        "delta_p": delta_p, # effective pressure drop across the injector/feed system [Pa]
    }

# phases 3 & 4: gaseous blowdown
def injector_joel_gaseous_blowdown(t: float, state_vector: dict, rocket_inputs: dict, live: dict, constants: dict):
    """
    Joel's injector model for gaseous blowdown, used in phases 3 and 4.
    Assumptions:
        - oxidizer upstream of the injector is vapor
        - injector flow is computed from the gas-phase analogue of the Joel injector relation
        - valve effects are applied as a multiplicative throttling factor on the fully-open flow
        - if the effective pressure drop is nonpositive, injector flow is zero
    """
    
    # unpack values
    p_C = state_vector["p_C"]
    p_T = live["p_T"]
    v_v = live["v_v"]
    valve_open_fraction = live["valve_open_fraction"]
    injector_discharge_coefficient = rocket_inputs["injector_discharge_coefficient"]
    injector_number_of_holes = rocket_inputs["injector_number_of_holes"]
    injector_hole_area_m2 = rocket_inputs["injector_hole_area"]
    feed_pressure_loss = rocket_inputs["feed_pressure_loss"]
    W_o = constants["nitrous_oxide_molar_mass"]

    # effective pressure drop across the injector/feed system
    delta_p = p_T - feed_pressure_loss - p_C

    # define a small transition region
    dp_transition = 10000.0 

    ###### nominal region (standard square root)
    if delta_p > dp_transition:
        n_dot_ox_ideal = (injector_discharge_coefficient * injector_number_of_holes * injector_hole_area_m2 * np.sqrt(2.0 * delta_p / (W_o * v_v)))

    ###### transition region (Quadratic Parabola)
    elif delta_p > 0.0:
        # flow at transition point
        f_trans = (injector_discharge_coefficient * injector_number_of_holes * injector_hole_area_m2 * np.sqrt(2.0 * dp_transition / (W_o * v_v)))
        
        # quadratic through the origin that also meets the sqrt branch in both value and slope at dp_transition
        # g(0) = 0 (no flow at no pressure drop)
        # g(dp_t) = f_trans (continuous with the sqrt)
        # g'(dp_t) = 0.5 * f_trans / dp_t (same slope as the sqrt)
        # solving those gives the constants below:
        a = -0.5 * f_trans / (dp_transition**2)
        b = 1.5 * f_trans / dp_transition
        c = 0.0
        
        n_dot_ox_ideal = a * delta_p**2 + b * delta_p + c
    
    ###### dead zone
    else:
        n_dot_ox_ideal = 0.0

    # actual injector flow after valve throttling
    n_dot_ox = valve_open_fraction * n_dot_ox_ideal

    return {
        "n_dot_ox": n_dot_ox, # actual oxidizer molar flow rate [mol/s]
        "n_dot_ox_ideal": n_dot_ox_ideal, # fully-open oxidizer molar flow rate before valve throttling [mol/s]
        "delta_p": delta_p, # effective pressure drop across the injector/feed system [Pa]
    }
    


##################################### NHNE MODEL
# phases 1 & 2
def injector_nhne_liquid_blowdown():
    """
    NHNE injector model for liquid-phase blowdown, used in phases 1 and 2.
    """

# phases 3 & 4
def injector_nhne_gaseous_blowdown():
    """
    NHNE injector model for gaseous blowdown, used in phases 3 and 4.
    """

