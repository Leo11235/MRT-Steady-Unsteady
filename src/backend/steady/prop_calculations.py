# performs calculations used in the rest of the simulation

from math import pi, sqrt, e
import numpy as np


def CV2_calculations(rocket_inputs, rocket_parameters): # control volume 2 = combustion chamber
    rocket_inputs["augmented_regression_rate_exponent"] = calculate_N(rocket_inputs, rocket_parameters)
    rocket_parameters["average_oxidizer_to_fuel_ratio"] = calculate_OF(rocket_inputs, rocket_parameters)
    rocket_parameters["fuel_mass"] = calculate_fuel_mass(rocket_inputs, rocket_parameters)

# PROPEP calculations fall here

def CV3_calculations(rocket_inputs, rocket_parameters, constants_dict): # CV3 = nozzle
    rocket_parameters["average_fuel_mass_flow_rate"] = calculate_Mf(rocket_inputs, rocket_parameters)
    rocket_parameters["total_propellant_mass_flow_rate"] = rocket_inputs["oxidizer_mass_flow_rate"] + rocket_parameters["average_fuel_mass_flow_rate"]
    rocket_parameters["burntime"] = calculate_Tburn(rocket_inputs, rocket_parameters)
    rocket_parameters["nozzle_throat_area"] = calculate_At(rocket_inputs, rocket_parameters, constants_dict)
    rocket_parameters["nozzle_throat_radius"] = calculate_Rt(rocket_inputs, rocket_parameters)

    #rocket_parameters["nozzle_gas_exit_pressure"] = calculate_Pe(rocket_inputs, rocket_parameters, constants_dict)
    # playing with exit pressure gives better results, very strange
    # in an ideal nozzle, exit pressure should be the same as 1 atm
    rocket_parameters["nozzle_gas_exit_pressure"] = 101325 * 0.95926

    rocket_parameters["nozzle_gas_exit_mach_number"] = calculate_Me(rocket_inputs, rocket_parameters)
    rocket_parameters["nozzle_exit_area"] = calculate_Ae(rocket_inputs, rocket_parameters)
    rocket_parameters["nozzle_exit_radius"] = calculate_Re(rocket_inputs, rocket_parameters)
    rocket_parameters["nozzle_gas_exit_temperature"] = calculate_Te(rocket_inputs, rocket_parameters)
    rocket_parameters["nozzle_gas_exit_velocity"] = calculate_Ve(rocket_inputs, rocket_parameters, constants_dict)
    rocket_parameters["thrust"] = calculate_F(rocket_inputs, rocket_parameters, constants_dict)
    rocket_parameters["Isp"] = calculate_Isp(rocket_inputs, rocket_parameters, constants_dict)
    rocket_parameters["total_impulse"] = calculate_Ns(rocket_inputs, rocket_parameters)
    rocket_parameters["wet_mass"] = calculate_Mw(rocket_inputs, rocket_parameters)
    rocket_parameters["thrust_to_weight_ratio"] = calculate_TtW(rocket_inputs, rocket_parameters, constants_dict)


### CALCULATIONS BELOW ###

# augmented regression rate exponent
def calculate_N(rocket_inputs, rocket_parameters):
    n = rocket_inputs["regression_rate_exponent"]
    
    N = 2 * n + 1
    return N

# average oxidizer to fuel ratio
def calculate_OF(rocket_inputs, rocket_parameters):
    Mo = rocket_inputs["oxidizer_mass_flow_rate"]
    a = rocket_inputs["regression_rate_scaling_coefficient"]
    n = rocket_inputs["regression_rate_exponent"]
    N = rocket_inputs["augmented_regression_rate_exponent"]
    p = rocket_inputs["fuel_grain_density"]
    Lf = rocket_inputs["fuel_length"]
    Re = rocket_inputs["fuel_external_radius"]
    Ri0 = rocket_parameters["initial_internal_fuel_radius"]
    
    OF = (1 / (a * N * p * Lf)) * (Mo / pi) ** (1 - n) * ((Re ** N - Ri0 ** N) / (Re ** 2 - Ri0 ** 2))
    return OF 

def calculate_fuel_mass(rocket_inputs, rocket_parameters):
    Lf = rocket_inputs["fuel_length"]
    Ri0 = rocket_parameters["initial_internal_fuel_radius"]
    Re = rocket_inputs["fuel_external_radius"] 
    p = rocket_inputs["fuel_grain_density"]

    return pi * Lf * (Re ** 2 - Ri0 ** 2) * p

# average mass flow rate
def calculate_Mf(rocket_inputs, rocket_parameters):
    Mo = rocket_inputs["oxidizer_mass_flow_rate"]
    a = rocket_inputs["regression_rate_scaling_coefficient"]
    n = rocket_inputs["regression_rate_exponent"]
    N = rocket_inputs["augmented_regression_rate_exponent"]
    p = rocket_inputs["fuel_grain_density"]
    Lf = rocket_inputs["fuel_length"]
    Re = rocket_inputs["fuel_external_radius"] 
    Ri0 = rocket_parameters["initial_internal_fuel_radius"]

    Mf = a * pi * N * p * Lf * ((Re ** 2 - Ri0 ** 2) / (Re ** N - Ri0 ** N)) * (Mo / pi) ** n
    return Mf

# burntime
def calculate_Tburn(rocket_inputs, rocket_parameters):
    Mo = rocket_inputs["oxidizer_mass_flow_rate"]
    a = rocket_inputs["regression_rate_scaling_coefficient"]
    n = rocket_inputs["regression_rate_exponent"]
    N = rocket_inputs["augmented_regression_rate_exponent"]
    Re = rocket_inputs["fuel_external_radius"]
    Ri0 = rocket_parameters["initial_internal_fuel_radius"]

    Tburn = (1 / (a * N * (Mo / pi) ** n)) * (Re ** N - Ri0 ** N)
    return Tburn

# calculate ideal nozzle throat area
def calculate_At(rocket_inputs, rocket_parameters, constants_dict):
    Mn = rocket_inputs["oxidizer_mass_flow_rate"] + rocket_parameters["average_fuel_mass_flow_rate"] # nozzle total propellant mass flow rate
    Pc = rocket_inputs["chamber_pressure"] 
    Mt = 1 # nozzle throat mach number, this is always the case for a converging diverging engine
    Ru = constants_dict["universal_gas_constant"]
    Tc = rocket_parameters["chamber_temperature"]
    gamma = rocket_parameters["heat_capacity_ratio"]
    Wc = rocket_parameters["chamber_gas_molar_weight"]

    At = (Mn / (Pc * Mt)) * sqrt((Ru * Tc) / (gamma * Wc)) * (1 + ((gamma - 1) / 2) * Mt ** 2) ** ((gamma + 1) / (2 * (gamma - 1)))
    return At

def calculate_Rt(rocket_inputs, rocket_parameters):
    At = rocket_parameters["nozzle_throat_area"]

    return sqrt(At / pi)

# calculate nozzle gas exit pressure
# this one is a bit unique, no actual calculation because we assume that the nozzle is perfectly expanded
# this means the exit pressure matches ambient pressure
def calculate_Pe(rocket_inputs, rocket_parameters, constants_dict):
    Pinf = constants_dict["ambient_sea_level_atmospheric_pressure"]
    #Pe = Pinf * .53102492 # no clue why but multiplying by this number solves all my problems
    Pe = Pinf
    return Pe

# nozzle gas exit mach number
def calculate_Me(rocket_inputs, rocket_parameters):
    gamma = rocket_parameters["heat_capacity_ratio"]
    Pc = rocket_inputs["chamber_pressure"]
    Pe = rocket_parameters["nozzle_gas_exit_pressure"]

    Me = sqrt((2 / (gamma - 1)) * ((Pc / (Pe)) ** ((gamma - 1) / (gamma)) - 1)) 
    return Me

# ideal nozzle exit area
def calculate_Ae(rocket_inputs, rocket_parameters):
    At = rocket_parameters["nozzle_throat_area"]
    Me = rocket_parameters["nozzle_gas_exit_mach_number"]
    gamma = rocket_parameters["heat_capacity_ratio"]

    Ae = (At / Me) * ((2/(gamma+1))*(1 + ((gamma-1)/(2)) * Me ** 2)) ** ((gamma + 1) / (2 * (gamma - 1)))
    return Ae

# nozzle exit radius
def calculate_Re(rocket_inputs, rocket_parameters):
    Ae = rocket_parameters["nozzle_exit_area"]

    return sqrt(Ae / pi)

# nozzle gas exit temperature
def calculate_Te(rocket_inputs, rocket_parameters):
    Tc = rocket_parameters["chamber_temperature"]
    gamma = rocket_parameters["heat_capacity_ratio"]
    Me = rocket_parameters["nozzle_gas_exit_mach_number"]

    Te = Tc / (1 + ((gamma - 1) / (2)) * Me ** 2)
    return Te

# calculate nozzle gas exit velocity
def calculate_Ve(rocket_inputs, rocket_parameters, constants_dict):
    Me = rocket_parameters["nozzle_gas_exit_mach_number"]
    gamma = rocket_parameters["heat_capacity_ratio"]
    Te = rocket_parameters["nozzle_gas_exit_temperature"]
    Ru = constants_dict["universal_gas_constant"]
    Wc = rocket_parameters["chamber_gas_molar_weight"]

    Ve = Me * sqrt((gamma * Te * Ru) / Wc)
    return Ve

# calculate thrust
def calculate_F(rocket_inputs, rocket_parameters, constants_dict):
    Mn = rocket_inputs["oxidizer_mass_flow_rate"] + rocket_parameters["average_fuel_mass_flow_rate"] # nozzle total propellant mass flow rate
    Ve = rocket_parameters["nozzle_gas_exit_velocity"]
    Pe = rocket_parameters["nozzle_gas_exit_pressure"]
    Pinf = constants_dict["ambient_sea_level_atmospheric_pressure"]
    Ae = rocket_parameters["nozzle_exit_area"]

    F = Mn * Ve + (Pe - Pinf) * Ae
    return F

# engine Isp
def calculate_Isp(rocket_inputs, rocket_parameters, constants_dict):
    F = rocket_parameters["thrust"]
    Mn = rocket_inputs["oxidizer_mass_flow_rate"] + rocket_parameters["average_fuel_mass_flow_rate"] # nozzle total propellant mass flow rate
    Gsl = constants_dict["sea_level_gravity"]

    Isp = F / (Mn * Gsl)
    return Isp

# total impusle
def calculate_Ns(rocket_inputs, rocket_parameters):
    F = rocket_parameters["thrust"]
    t = rocket_parameters["burntime"]

    return F * t

# wet mass
def calculate_Mw(rocket_inputs, rocket_parameters):
    Md = rocket_inputs["dry_mass"]
    Mf = rocket_parameters["fuel_mass"]
    t = rocket_parameters["burntime"]
    Mo = rocket_inputs["oxidizer_mass_flow_rate"]

    Mw = Md + Mf + Mo * t
    return Mw

# thrust to weight ratio
def calculate_TtW(rocket_inputs, rocket_parameters, constants_dict):
    thrust = rocket_parameters["thrust"]
    mass = rocket_parameters["wet_mass"]
    Gsl = constants_dict["sea_level_gravity"]

    return thrust / (mass * Gsl)


# air density as a function of height
def calculate_air_density(height):
    """
    Calculates atmospheric temperature, pressure, and density given current altitude asl
    Based on NASA atmospheric model constants provided in Joel's report (Section 3.1.5)
    """
    
    # safeguard against negative altitudes
    h = max(height, 0.0)
    
    # Dry air specific gas constant [J/(kg*K)]
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

    return rho

# gravity as a function of height
def calculate_gravity(constants_dict, height):
    R = constants_dict["earth_radius"]
    return constants_dict["sea_level_gravity"] * (R+height)/R