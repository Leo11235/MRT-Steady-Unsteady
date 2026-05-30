"""
All valve functions return a single dimensionless open fraction:
    - 0.0 = fully closed
    - 1.0 = fully open
    - or somewhere in between
The N2O flow through the injector is multiplied by this fraction
"""

import numpy as np

###################### linear ramp valve opening model
def valve_linear_ramp(t: float, state_vector: dict, rocket_inputs: dict, live: dict, constants: dict):
    """
    Linear valve opening model
    Assumptions:
        - valve is fully closed at t_phase = 0
        - valve opens linearly with time
        - valve is fully open once t_phase >= valve_time_constant_s
        - if valve_time_constant_s <= 0, the valve is treated as instantly fully open. 
    """
    valve_time_constant_s = rocket_inputs["valve_time_constant_s"]
    t_phase = t

    # special case: instantaneous opening
    if valve_time_constant_s <= 0.0:
        valve_open_fraction = 1.0
    else:
        valve_open_fraction = t_phase / valve_time_constant_s
        valve_open_fraction = np.clip(valve_open_fraction, 0.0, 1.0)

    return {
        "valve_open_fraction": valve_open_fraction, # [0.0-1.0], fraction of N2O flow allowed through the valve
    }

################# sigmoid ramp valve opening model
def valve_sigmoid_ramp(t: float, state_vector: dict, rocket_inputs: dict, live: dict, constants: dict):
    """
    Sigmoid valve opening model
    Assumptions:
        - valve opening follows a logistic / sigmoid curve
        - valve_open_fraction = 0.5 when t_phase = sigmoid_half_time_s
        - larger sigmoid_steepness makes the opening transition sharper
        - smaller sigmoid_steepness makes the opening transition more gradual
    """
    sigmoid_half_time_s = rocket_inputs["sigmoid_half_time_s"]
    sigmoid_steepness = rocket_inputs["sigmoid_steepness"]
    t_phase = t

    valve_open_fraction = 1.0 / (1.0 + np.exp(-sigmoid_steepness * (t_phase - sigmoid_half_time_s)))
    valve_open_fraction = np.clip(valve_open_fraction, 0.0, 1.0)

    return {
        "valve_open_fraction": valve_open_fraction, # [0.0-1.0], fraction of N2O flow allowed through the valve
    }