"""
Bilinear interpolation for the precomputed CEA lookup table (defunct; this way of handling CEA causes solve_ivp to freak)
"""
import pandas as pd 
import numpy as np
import json
from pathlib import Path
import sys

project_root = Path(__file__).resolve().parents[5]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.backend.unsteady.physics.CEA.NASA_CEA import runCEA

_STATIC   = Path(__file__).resolve().parents[2] / "static_data"
_CEA_FILE = _STATIC / "CEA_table.json"

# load lookup table
def _load_lookup_table(_CEA_FILE=_CEA_FILE):
    with open(_CEA_FILE) as f:
        table = json.load(f)
    df = pd.DataFrame(table["records"])
    df = df.set_index(["OF", "p_C"])
    return df
_cea_table = _load_lookup_table()

def CEA_interpolation_lookup(OF: float, 
                             p_C: float, # in Pa
                             lookup_table=_cea_table):
    """
    Return interpolated combustion properties at (OF, p_C)
    
    Parameters
    OF: float → O/F mass ratio
    p_C: float → Chamber pressure [Pa]
    
    Returns tuple object: 
    (
    T_C → Chamber temperature
    W_C → Molar mass
    gamma → Heat capacity ratio
    cstar → Ideal characteristic velocity
    dT_dOF → Chamber temperature derivative w.r.t. OF
    dT_dp → Chamber temperature derivative w.r.t. p_C
    dW_dOF → Molar mass derivative w.r.t. OF
    dW_dp → Molar mass derivative w.r.t. p_C
    )
    
    All input & output units in SI
    """
    
    OF = float(OF)
    p_C = float(p_C)
    
    try: 
        row = lookup_table.loc[(OF, p_C)]
        return (
            row["T_C"], row["W_C"], row["gamma"], row["cstar"],
            row["dT_dOF"], row["dT_dp"], row["dW_dOF"], row["dW_dp"]
        )
    except KeyError:
        pass
    
    OF_array = np.sort(lookup_table.index.get_level_values("OF").unique().astype(float))
    p_array = np.sort(lookup_table.index.get_level_values("p_C").unique().astype(float))
    
    # max/min bounds of table
    OF_min, OF_max = OF_array.min(), OF_array.max()
    p_min, p_max = p_array.min(), p_array.max()
    
    # if outside table bounds, run CEA 
    if (OF < OF_min or OF > OF_max or p_C < p_min or p_C > p_max):
        T, W, gamma, cstar = runCEA(OF, p_C)
        
        delta_OF: float = 0.05
        delta_p: float = 1000.0
        T_op, W_op, *_ = runCEA(OF + delta_OF, p_C)
        T_om, W_om, *_ = runCEA(max(OF - delta_OF, 0.5), p_C)
        T_pp, W_pp, *_ = runCEA(OF, p_C + delta_p)
        T_pm, W_pm, *_ = runCEA(OF, max(p_C - delta_p, 1.0))
        dT_dOF = (T_op - T_om) / (2 * delta_OF)
        dW_dOF = (W_op - W_om) / (2 * delta_OF)
        dT_dp  = (T_pp - T_pm) / (2 * delta_p) # K/Pa
        dW_dp  = (W_pp - W_pm) / (2 * delta_p) # (kg/mol)/Pa
        
        return (float(T), float(W), float(gamma), float(cstar), float(dT_dOF), float(dT_dp), float(dW_dOF), float(dW_dp))
    
    # check for exact match with table values
    try:
        row = lookup_table.loc[(OF, p_C)]
        return (
            row["T_C"], row["W_C"], row["gamma"], row["cstar"],
            row["dT_dOF"], row["dT_dp"], row["dW_dOF"], row["dW_dp"]
        )
    except KeyError:
        pass
    
    # find grid bounds
    OF_low = OF_array[OF_array <= OF].max()
    OF_high = OF_array[OF_array >= OF].min()
    p_low = p_array[p_array <= p_C].max()
    p_high = p_array[p_array >= p_C].min()
    
    # helper to fetch corners
    def get_corner(o, p):
        row = lookup_table.loc[(o, p)]
        return np.array([
            row["T_C"],
            row["W_C"],
            row["gamma"],
            row["cstar"],
            row["dT_dOF"],
            row["dT_dp"],
            row["dW_dOF"],
            row["dW_dp"],
        ])
    Q11 = get_corner(OF_low, p_low)
    Q12 = get_corner(OF_low, p_high)
    Q21 = get_corner(OF_high, p_low)
    Q22 = get_corner(OF_high, p_high)
    
    if OF_low == OF_high and p_low == p_high:
        result = Q11

    elif OF_low == OF_high:
        result = Q11 + (Q12 - Q11) * (p_C - p_low) / (p_high - p_low)

    elif p_low == p_high:
        result = Q11 + (Q21 - Q11) * (OF - OF_low) / (OF_high - OF_low)

    else:
        denom = (OF_high - OF_low) * (p_high - p_low)

        term1 = Q11 * (OF_high - OF) * (p_high - p_C)
        term2 = Q21 * (OF - OF_low) * (p_high - p_C)
        term3 = Q12 * (OF_high - OF) * (p_C - p_low)
        term4 = Q22 * (OF - OF_low) * (p_C - p_low)

        result = (term1 + term2 + term3 + term4) / denom

    return tuple(map(float, result))