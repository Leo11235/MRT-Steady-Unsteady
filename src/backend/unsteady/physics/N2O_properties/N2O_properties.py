"""
N2O saturated-phase thermodynamic property lookup

Data source
The lookup table N2O_properties_table.jsonc is taken from
Appendix A of Jean-Philippe (2023), which was derived from the
NIST Chemistry WebBook.  It covers T ∈ [182 K, 309.52 K] on a
non-uniform grid (27 points).

Properties returned by get_N2O_property(T)
===================================================
    p           |  [Pa]          |  saturated pressure
    d_p/d_T     |  [Pa/K]        |  derivative of saturated pressure
                |                |                                  
    v_l         |  [m³/mol]      |  liquid molar volume
    v_v         |  [m³/mol]      |  vapour molar volume
                |                |                                  
    u_l         |  [J/mol]       |  liquid internal energy
    u_v         |  [J/mol]       |  vapour internal energy
                |                |                                  
    h_l         |  [J/mol]       |  liquid molar enthalpy
    h_v         |  [J/mol]       |  vapour molar enthalpy
                |                |                                  
    c_v_v       |  [J/(mol·K)]   |  vapour heat capacity (constant volume)
    c_p_v       |  [J/(mol·K)]   |  vapour heat capacity (constant pressure)
                |                |                                  
    Z           |  [-]           |  vapour compressibility factor  Z = p·v_v/(R_u·T)
                |                |                                  
    d_v_l/d_T   |  [m³/(mol·K)]  |  derivative of liquid molar volume
    d_v_v/d_T   |  [m³/(mol·K)]  |  derivative of vapour molar volume
                |                |                                  
    d_u_l/d_T   |  [J/(mol·K)]   |  derivative of liquid internal energy
    d_u_v/d_T   |  [J/(mol·K)]   |  derivative of vapour internal energy
                |                |                                  
    d_h_l/d_T   |  [J/(mol·K)]   |  derivative of liquid molar enthalpy
    d_h_v/d_T   |  [J/(mol·K)]   |  derivative of vapour molar enthalpy
                |                |                                  
    d_c_v_v/d_T |  [J/(mol·K²)]  |  derivative of vapour heat capacity (constant volume)
    d_c_p_v/d_T |  [J/(mol·K²)]  |  derivative of vapour heat capacity (constant pressure)
                |                |                                  
    d_Z/d_T     |  [1/K]         |  derivative of vapour compressibility factor
"""

import re, json, math, bisect
from pathlib import Path

_STATIC = Path(__file__).resolve().parents[2] / "static_data"
_N2O_FILE = _STATIC / "N2O_properties_table.jsonc"

# returns N2O properties dict
def initialize_N2O_properties_dict(N2O_data_filepath = _N2O_FILE):
    # get N2O properties file (located under project src/static_data)
    with open(N2O_data_filepath, 'r') as f:
        content = f.read()
    # remove comments
    cleaned = re.sub(r'//.*', '', content)
    cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
    # parse cleaned file into dicr
    N2O_properties_dict = json.loads(cleaned)
    
    # some quantities are in [.../(kmol)], need to be converted to [.../mol] for SI units
    N2O_properties_dict["v_v"] = [x / 1000 for x in N2O_properties_dict["v_v"]]
    N2O_properties_dict["d_v_v/d_T"] = [x / 1000 for x in N2O_properties_dict["d_v_v/d_T"]]
    N2O_properties_dict["d_u_l/d_T"] = [x / 1000 for x in N2O_properties_dict["d_u_l/d_T"]]
    N2O_properties_dict["d_h_l/d_T"] = [x / 1000 for x in N2O_properties_dict["d_h_l/d_T"]]
    N2O_properties_dict["d_u_v/d_T"] = [x / 1000 for x in N2O_properties_dict["d_u_v/d_T"]]
    N2O_properties_dict["d_h_v/d_T"] = [x / 1000 for x in N2O_properties_dict["d_h_v/d_T"]]
    N2O_properties_dict["d_c_v_v/d_T"] = [x / 1000 for x in N2O_properties_dict["d_c_v_v/d_T"]]
    N2O_properties_dict["d_c_p_v/d_T"] = [x / 1000 for x in N2O_properties_dict["d_c_p_v/d_T"]]
    
    # some quantities are in [kJ/...], need to be converted to [J/...]
    N2O_properties_dict["u_l"] = [x * 1000 for x in N2O_properties_dict["u_l"]]
    N2O_properties_dict["h_l"] = [x * 1000 for x in N2O_properties_dict["h_l"]]
    N2O_properties_dict["u_v"] = [x * 1000 for x in N2O_properties_dict["u_v"]]
    N2O_properties_dict["h_v"] = [x * 1000 for x in N2O_properties_dict["h_v"]]
    N2O_properties_dict["c_v_v"] = [x * 1000 for x in N2O_properties_dict["c_v_v"]]
    N2O_properties_dict["c_p_v"] = [x * 1000 for x in N2O_properties_dict["c_p_v"]]
    
    return N2O_properties_dict

N2O_properties_dict = initialize_N2O_properties_dict()

# returns property_name interpolated at tank_temp for any property_name in N2O_properties_dict
def get_N2O_property(property_name, tank_temp, N2O_properties_dict=N2O_properties_dict):
    _check_temperature_range(tank_temp)
    
    # some variables have functions rather than relying on the lookup table
    if property_name == 'p':
        return _p_sat(tank_temp) # saturated pressure of N2O, Pa
    elif property_name == 'd_p/d_T':
        return _dp_sat_dT(tank_temp) # saturated pressure of N2O with respect to tank temp, dPa/dT
    elif property_name == 'v_l':
        return _v_l_sat(tank_temp)/1000 # saturated liquid molar volume of nitrous, m^3/mol
    elif property_name == 'd_v_l/d_T':
        return _dv_l_sat_dT(tank_temp)/1000 # saturated liquid molar volume of nitrous with respect to tank temp, d(m^3/mol)/dT
    elif property_name == "Z": 
        return _Z_sat(tank_temp) # saturated vapor compressibility factor
    elif property_name == "d_Z/d_T":
        return _dZ_sat_dT(tank_temp) # saturated vapor compressibility factor w.r.t. temperature
    
    T_list = N2O_properties_dict['T']
    
    # for given tank_temp, find the two 'neighboring' points
    # eg if tank_temp = 196, low_index = 195 and high_index = 200
    # _position --> position of item within the list
    # _value --> value of item within that position
    bisect_val = bisect.bisect_left(T_list, tank_temp)
    low_index_position = bisect_val-1
    low_index_value = T_list[low_index_position]
    high_index_position = bisect_val
    high_index_value = T_list[high_index_position]
    
    # find how far tank_temp is from either end of the indices
    low_index_diff = abs(low_index_value - tank_temp)
    high_index_diff = abs(high_index_value - tank_temp)
    
    # if either index = 0, simply evaluate property_name at that index
    if high_index_diff == 0:
        return N2O_properties_dict[property_name][high_index_position]
    elif low_index_diff == 0:
        return N2O_properties_dict[property_name][low_index_position]
    else:
        # interpolate best match for input tank_temp
        # match will be somewhere between low_index and high_index
        return (high_index_diff * N2O_properties_dict[property_name][low_index_position] + 
                low_index_diff * N2O_properties_dict[property_name][high_index_position]) / (high_index_diff + low_index_diff)

# HELPERS
# valid saturation-table range from Appendix A
def _check_temperature_range(T: float) -> None:
    T_MIN_N2O = 182.33
    T_MAX_N2O = 309.52
    if not (T_MIN_N2O <= T <= T_MAX_N2O):
        raise ValueError(
            f"N2O saturated-property lookup valid only for "
            f"{T_MIN_N2O:.2f} K <= T <= {T_MAX_N2O:.2f} K.")
        

def _p_sat(T):
    # from literature
    c_1 = 96.512
    c_2 = -4045
    c_3 = -12.277
    c_4 = 0.00002886
    c_5 = 2
    
    exponent = c_1 + c_2 / T + c_3 * math.log(T) + c_4 * T ** c_5
    return math.exp(exponent)

def _dp_sat_dT(T):
    c_2 = -4045
    c_3 = -12.277
    c_4 = 0.00002886
    c_5 = 2
    
    return _p_sat(T) * (-c_2/T**2 + c_3/T + c_4*c_5*T**(c_5-1))

def _v_l_sat(T):
    c_1 = 2.781
    c_2 = 0.27244
    c_3 = 309.57
    c_4 = 0.2882
    
    term_1 = 1 + (1 - T/c_3) ** c_4
    term_2 = c_2 ** term_1
    return term_2 / c_1

def _dv_l_sat_dT(T):
    c_2 = 0.27244
    c_3 = 309.57
    c_4 = 0.2882
    
    term_1 = (c_4 / c_3) * math.log(c_2) * _v_l_sat(T)
    term_2 = (1 - T/c_3) ** (c_4 - 1)
    return term_1 * term_2

R_U = 8.314462618  # J/(mol·K)
def _Z_sat(T):
    """
    Saturated vapor compressibility factor Z = p * nu_v / (R_u * T) [-]
    """
    p = _p_sat(T)
    nu_v = get_N2O_property("v_v", T)  # expects m^3/mol
    return p * nu_v / (R_U * T)

def _dZ_sat_dT(T):
    """
    dZ/dT = Z * [ (1/p) dp/dT + (1/nu_v) dnu_v/dT - 1/T ]
    """
    p = _p_sat(T)
    dp_dT = _dp_sat_dT(T)
    nu_v = get_N2O_property("v_v", T) # m^3/mol
    dnu_v_dT = get_N2O_property("d_v_v/d_T", T) # m^3/(mol·K)
    Z = p * nu_v / (R_U * T)

    return Z * ((dp_dT / p) + (dnu_v_dT / nu_v) - (1.0 / T))

# test
#print(get_N2O_property("p", 300))