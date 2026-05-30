"""
Bicubic interpolator for the CEA lookup table in src/backend/unsteady/static_data
Uses use a Bivariate Bicubic Spline via SciPy's RectBivariateSpline to quickly access CEA values while avoiding step function derivatives
"""

import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.interpolate import RectBivariateSpline

# ensure project root is in the system path for clean internal imports
project_root = Path(__file__).resolve().parents[5]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.backend.unsteady.physics.CEA.NASA_CEA import runCEA

# static database path
_STATIC   = Path(__file__).resolve().parents[2] / "static_data"
_CEA_FILE = _STATIC / "CEA_table.json"



# load lookup table
# uses the flat precomputed JSON records to reconstruct the 2D grid axes; fits independent continuous bivariate bicubic splines for each property
def _initialize_spline_tables():
    with open(_CEA_FILE, "r") as f:
        table = json.load(f)
    df = pd.DataFrame(table["records"])

    # get sorted grid axes from the data strings
    of_axis = np.sort(df["OF"].unique())
    p_axis = np.sort(df["p_C"].unique())
    # reshape colums into matrices for scipy
    # OF -> rows, p_C -> columns
    T_grid = df.pivot(index="OF", columns="p_C", values="T_C").to_numpy()
    W_grid = df.pivot(index="OF", columns="p_C", values="W_C").to_numpy()
    gamma_grid = df.pivot(index="OF", columns="p_C", values="gamma").to_numpy()
    cstar_grid = df.pivot(index="OF", columns="p_C", values="cstar").to_numpy()
    
    # create & return spline structure
    return {
        "T_c": RectBivariateSpline(of_axis, p_axis, T_grid, kx=3, ky=3), # kx, ky = 3 forces a cubic fit, should create smooth derivatives
        "W_c": RectBivariateSpline(of_axis, p_axis, W_grid, kx=3, ky=3),
        "gamma": RectBivariateSpline(of_axis, p_axis, gamma_grid, kx=3, ky=3),
        "cstar": RectBivariateSpline(of_axis, p_axis, cstar_grid, kx=3, ky=3),
        "bounds": {
            "OF_min": of_axis.min(), "OF_max": of_axis.max(),
            "p_min": p_axis.min(), "p_max": p_axis.max()
        }
    }
_SPLINES = _initialize_spline_tables()


def CEA_interpolation_lookup(OF: float, p_C: float, splines=_SPLINES):
    """
    Return interpolated combustion properties at (OF, p_C) and their partial derivatives
    
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
    b = splines["bounds"]
    
    # run CEA if this entry is out of bounds
    if (OF < b["OF_min"] or OF > b["OF_max"] or p_C < b["p_min"] or p_C > b["p_max"]):
        T, W, gamma, cstar = runCEA(OF, p_C)
        # compute local derivatives
        d_OF, d_p = 0.05, 1000.0
        T_op, W_op, *_ = runCEA(OF + d_OF, p_C)
        T_om, W_om, *_ = runCEA(max(OF - d_OF, 0.5), p_C)
        T_pp, W_pp, *_ = runCEA(OF, p_C + d_p)
        T_pm, W_pm, *_ = runCEA(OF, max(p_C - d_p, 1.0))
        # return all
        return (float(T), float(W), 
                float(gamma), float(cstar), 
                float((T_op - T_om) / (2 * d_OF)), 
                float((T_pp - T_pm) / (2 * d_p)), 
                float((W_op - W_om) / (2 * d_OF)), 
                float((W_pp - W_pm) / (2 * d_p)))
    
    # if the entry is within table bounds, interpolate
    T_c   = splines["T_c"](OF, p_C)[0][0]
    W_c   = splines["W_c"](OF, p_C)[0][0]
    gamma = splines["gamma"](OF, p_C)[0][0]
    cstar = splines["cstar"](OF, p_C)[0][0]
    # get local derivatives (dx=1, dy=0 means first derivative with respect to X (O/F), etc)
    dT_dOF = splines["T_c"](OF, p_C, dx=1, dy=0)[0][0]
    dW_dOF = splines["W_c"](OF, p_C, dx=1, dy=0)[0][0]
    dT_dp  = splines["T_c"](OF, p_C, dx=0, dy=1)[0][0]
    dW_dp  = splines["W_c"](OF, p_C, dx=0, dy=1)[0][0]
    
    return (T_c, W_c, gamma, cstar, dT_dOF, dT_dp, dW_dOF, dW_dp)



# helper function for warnings.py, retrieves the min/max OF/p_C input range. 
def get_CEA_table_bounds():
    with open(_CEA_FILE) as f:
        table = json.load(f)

    OF_MIN = table["OF_min"]
    OF_MAX = table["OF_max"]
    p_C_MIN = table["p_C_min"]
    p_C_MAX = table["p_C_max"]
    
    return (OF_MIN, OF_MAX, p_C_MIN, p_C_MAX)