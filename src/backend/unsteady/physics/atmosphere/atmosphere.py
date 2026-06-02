"""
Handles ambient atmospheric properties based on the NASA atmospheric model. Accurate to 25km. 
Used by the nozzle (CV5) for pressure regimes and the trajectory (CV6) for aerodynamic drag.
"""

import numpy as np

def get_atmosphere_properties(altitude_asl: float # absolute elevation above sea level [m]
                              ):
    """
    Calculates atmospheric temperature, pressure, and density given current altitude asl
    Based on NASA atmospheric model constants provided in Joel's report (Section 3.1.5)
    """
    
    # safeguard against negative altitudes
    h = max(altitude_asl, 0.0)
    
    # dry air specific gas constant [J/(kg*K)]
    R_air = 287.05 
    
    if h < 11000.0:
        # Troposphere
        T = -0.00649 * h + 288.19
        p = 101290.0 * (T / 288.08) ** 5.256
    elif h < 25000.0:
        # Lower Stratosphere
        T = 216.69
        p = 22650.0 * np.exp(1.73 - 0.000157 * h)
    else:
        # approximation for h >= 25,000m 
        T = 216.69 + 0.00299 * (h - 25000.0)
        p = 2488.0 * (T / 216.6) ** -11.388

    # calculate density using Ideal Gas Law for air
    rho = p / (R_air * T)

    return {
        "T_amb": T, # Ambient temperature [K]
        "p_amb": p, # Ambient pressure [Pa]
        "rho_amb": rho # Ambient density [kg/m^3]
    }