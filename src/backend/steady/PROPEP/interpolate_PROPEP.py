import pandas as pd 
import numpy as np
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# load lookup table
def load_lookup_table():
    json_path = _ROOT_DIR / "Backend" / "Static_data" / "pypropep_lookup_table.json"
    return pd.read_json(json_path, orient="table")

ppp_df_loaded = load_lookup_table()

def pyPROPEP_interpolation_lookup(OF, CP, lookup_table=ppp_df_loaded):
    '''
    Uses bilinear interpolation to return PROPEP values
    '''
    # standardize input types
    OF = float(OF)
    CP = float(CP)
    
    try: # check if input OF and CP are exact matches
        row = lookup_table.loc[(OF, CP)]
        #chamber_temp, molar_weight, heat_ratio
        return (row["chamber_temp"], row["molar_weight"], row["heat_ratio"])
    except KeyError:
        pass  #interpolate
    
    unique_OF = np.sort(lookup_table.index.get_level_values("OF").unique().astype(float))
    unique_CP = np.sort(lookup_table.index.get_level_values("CP").unique().astype(float))
    
    ###############
    ###### clamp to table bounds to prevent crashes at extreme pressures
    ###############
    OF = np.clip(OF, unique_OF.min(), unique_OF.max())
    CP = np.clip(CP, unique_CP.min(), unique_CP.max())
    
    # boundary checks
    if OF < unique_OF.min() or OF > unique_OF.max():            
        raise ValueError(f"OF={OF} is outside the table bounds [{unique_OF.min()}, {unique_OF.max()}]")
    if CP < unique_CP.min() or CP > unique_CP.max():
        raise ValueError(f"CP={CP} is outside the table bounds [{unique_CP.min()}, {unique_CP.max()}]")
    
    # Clamp to table bounds to prevent crashes at extreme pressures
    # OF = np.clip(OF, unique_OF.min(), unique_OF.max())
    # CP = np.clip(CP, unique_CP.min(), unique_CP.max())
    
    # find bounds
    OF_low  = unique_OF[unique_OF <= OF].max()
    OF_high = unique_OF[unique_OF >= OF].min()
    CP_low  = unique_CP[unique_CP <= CP].max()
    CP_high = unique_CP[unique_CP >= CP].min()
    
    # helper to fetch data
    def get_corner(o, p):
        row = lookup_table.loc[(o, p)]
        return np.array([row["chamber_temp"], row["molar_weight"], row["heat_ratio"]])
    
    # bilinear interpolation calculation
    Q11 = get_corner(OF_low, CP_low)   # bottom left
    Q12 = get_corner(OF_low, CP_high)  # top left
    Q21 = get_corner(OF_high, CP_low)  # bottom right
    Q22 = get_corner(OF_high, CP_high) # top right
    
    # check for exact matches or gridline matches to avoid division by zero
    if OF_low == OF_high and CP_low == CP_high:
        result = Q11
    elif OF_low == OF_high: # vertical linear interpolation
        result = Q11 + (Q12 - Q11) * (CP - CP_low) / (CP_high - CP_low)
    elif CP_low == CP_high: # horizontal linear interpolation
        result = Q11 + (Q21 - Q11) * (OF - OF_low) / (OF_high - OF_low)
    else:
        # standard Bilinear Formula
        # f(x,y) ≈ [f(x1,y1)(x2-x)(y2-y) + f(x2,y1)(x-x1)(y2-y) + f(x1,y2)(x2-x)(y-y1) + f(x2,y2)(x-x1)(y-y1)] / [(x2-x1)(y2-y1)]
        denom = (OF_high - OF_low) * (CP_high - CP_low)
        
        term1 = Q11 * (OF_high - OF) * (CP_high - CP)
        term2 = Q21 * (OF - OF_low) * (CP_high - CP)
        term3 = Q12 * (OF_high - OF) * (CP - CP_low)
        term4 = Q22 * (OF - OF_low) * (CP - CP_low)
        
        result = (term1 + term2 + term3 + term4) / denom

    return (float(result[0]), float(result[1]), float(result[2]))

def get_chamber_properties_with_partials(OF, p_C, delta_OF=0.01, delta_p=1):
    # get base values
    T_base, W_base, gamma_base = pyPROPEP_interpolation_lookup(OF, p_C, lookup_table=ppp_df_loaded)
    
    # Perturb OF (for ∂/∂(OF)) - keep pressure constant
    T_OF_plus, W_OF_plus, _ = pyPROPEP_interpolation_lookup(OF + delta_OF, p_C, lookup_table=ppp_df_loaded)
    T_OF_minus, W_OF_minus, _ = pyPROPEP_interpolation_lookup(OF - delta_OF, p_C, lookup_table=ppp_df_loaded)
    
    # Perturb pressure (for ∂/∂p_C) - keep OF constant  
    T_p_plus, W_p_plus, _ = pyPROPEP_interpolation_lookup(OF, p_C + delta_p, lookup_table=ppp_df_loaded)
    T_p_minus, W_p_minus, _ = pyPROPEP_interpolation_lookup(OF, p_C - delta_p, lookup_table=ppp_df_loaded)
    
    # Calculate partial derivatives (central difference)
    dT_dOF = (T_OF_plus - T_OF_minus) / (2 * delta_OF)
    dW_dOF = (W_OF_plus - W_OF_minus) / (2 * delta_OF)
    
    dT_dp = (T_p_plus - T_p_minus) / (2 * delta_p)
    dW_dp = (W_p_plus - W_p_minus) / (2 * delta_p)
    
    return T_base, W_base, gamma_base, dT_dOF, dW_dOF, dT_dp, dW_dp