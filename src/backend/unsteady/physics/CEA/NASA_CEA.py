"""
Runs NASA-CEA program through a python interface
Documentation:
https://rocketcea.readthedocs.io/

This file contains two main functions: 
runCEA runs the NASA-CEA program
generate_CEA_table calls runCEA to generate a lookup table for the main simulation. 
"""

import json
import numpy as np
from pathlib import Path
print("Caching data temporary NASA-CEA data in ", end="")
from rocketcea.cea_obj import CEA_Obj
from rocketcea.cea_obj import add_new_fuel

_STATIC   = Path(__file__).resolve().parents[2] / "static_data"
_CEA_FILE = _STATIC / "CEA_table.json"

# define our very own fuel
eicosane_card = """
fuel C20H42  C 20 H 42  wt%=100.
h,cal=-249660.0  t(k)=298.15
"""
add_new_fuel("EICOSANE", eicosane_card)

def runCEA(OF_ratio: float, 
           chamber_pressure: float, # in Pa
           fuel_name = "EICOSANE",
           oxidizer_name = "N2O"):
    """
    Runs NASA-CEA for a single CEA(OF, p_C) input. Returns (chamber temp, molar weight, heat ratio, ideal characteristic velocity).
    """
    

    # convert pressure from Pa → psia
    chamber_pressure = chamber_pressure / 6894.757293168


    # create CEA object
    try:
        cea = CEA_Obj(oxName=oxidizer_name, fuelName=fuel_name)
    except Exception as e:
        return {"error": f"Invalid propellant name or CEA initialization failed: {e}"}


    # run calculation
    try:
        # chamber temperature
        chamber_temp = cea.get_Tcomb(Pc=chamber_pressure, MR=OF_ratio)
        # molar weight and gamma
        molar_weight, heat_ratio = cea.get_Chamber_MolWt_gamma(Pc=chamber_pressure, MR=OF_ratio)
        # ideal characteristic velocity
        cstar_ft = cea.get_Cstar(Pc=chamber_pressure, MR=OF_ratio)
        
        # chamber temp: convert Rankine → Kelvin
        chamber_temp = chamber_temp / 1.8
        # molar weight: convert g/mol → kg/mol
        molar_weight = molar_weight / 1000
        # heat capacity ratio doesn't need converting
        # ideal characteristic velocity: convert ft/s → m/s
        cstar = cstar_ft * 0.3048

    except Exception as e:
        return {"error": f"CEA calculation failed: {e}"}

    return (chamber_temp, molar_weight, heat_ratio, cstar)



def generate_CEA_table(
    OF_range: tuple = (1.0, 15.0),
    OF_step: float = 0.25,
    p_C_range: tuple = (344738.0, 6895000.0),
    p_C_step: float = 172369.0,
    output_filepath: Path = _CEA_FILE, 
    delta_OF: float = 0.05,
    delta_p: float = 0.25):
    '''
    Generate a precomputed CEA/PROPEP combustion property lookup table for N2O / eicosane propellants.
    
    Parameters
    ----------
    OF_range  : (low, high)   O/F range (inclusive)
    OF_step   : float         O/F grid spacing
    p_C_range : (low, high)   Chamber pressure range [bar]
    p_C_step  : float         Pressure grid spacing [bar]
    out_file  : Path          Output JSON file path
    delta_OF  : float         Step for numerical ∂/∂OF
    delta_p   : float         Step for numerical ∂/∂p_C [bar]
    
    The table stores an 8-quantity result at each (OF, p_C) grid point:
        T_C      [K]            adiabatic flame temperature
        W_C      [kg/mol]       combustion gas mean molar mass
        gamma    [-]            ratio of specific heats
        cstar    [m/s]          characteristic exhaust velocity
        dT_dOF   [K/-]          ∂T_C/∂OF
        dT_dp    [K/Pa]         ∂T_C/∂p_C
        dW_dOF   [(kg/mol)/-]   ∂W_C/∂OF
        dW_dp    [(kg/mol)/Pa]  ∂W_C/∂p_C
        
    Output is saved to "src/backend/static_data/CEA_table.json"
    '''
    
    OF_vals  = np.arange(OF_range[0],  OF_range[1]  + OF_step / 2, OF_step)
    p_C_vals = np.arange(p_C_range[0], p_C_range[1] + p_C_step / 2, p_C_step)
        
    records = [] # records computations made so far
    count = 0 # how many times runCEA has been called
    n_total = len(OF_vals) * len(p_C_vals)
    
    print(f"Generating CEA table: {len(OF_vals)} x {len(p_C_vals)} = {n_total} points")
    
    for OF in OF_vals:
        for p_C in p_C_vals:
            count += 1
            if count % 20 == 0:
                print(f"  {count}/{n_total}  OF={OF:.2f}  p_C={p_C:.1f} bar")
            try:
                T, W, g, cs = runCEA(OF, p_C)
                
                # compute partials
                T_op, W_op, *_ = runCEA(OF + delta_OF, p_C)
                T_om, W_om, *_ = runCEA(max(OF - delta_OF, 0.5), p_C)
                T_pp, W_pp, *_ = runCEA(OF, p_C + delta_p)
                T_pm, W_pm, *_ = runCEA(OF, max(p_C - delta_p, 1.0))
                
                dT_dOF = (T_op - T_om) / (2 * delta_OF)
                dW_dOF = (W_op - W_om) / (2 * delta_OF)
                dT_dp  = (T_pp - T_pm) / (2 * delta_p * 1e5) # → K/Pa
                dW_dp  = (W_pp - W_pm) / (2 * delta_p * 1e5) # → (kg/mol)/Pa
                
                records.append({
                    "OF": round(float(OF), 4),
                    "p_C": round(float(p_C), 4),
                    "T_C": T, 
                    "W_C": W, 
                    "gamma": g, 
                    "cstar": cs,
                    "dT_dOF": dT_dOF, 
                    "dT_dp": dT_dp,
                    "dW_dOF": dW_dOF, 
                    "dW_dp": dW_dp,
                })
                
            except Exception as e: 
                print(f"Error in OF={OF:.2f}, p_C={p_C:.1f}: {e}")
                exit()
        
    table = {
        "OF_min": float(OF_vals.min()),
        "OF_max": float(OF_vals.max()),
        "OF_step": float(OF_step),
        "p_C_min": float(p_C_vals.min()),
        "p_C_max": float(p_C_vals.max()),
        "p_C_step": float(p_C_step),
        "records": records,
    }
    
    with open(output_filepath, "w") as f:
        json.dump(table, f, indent=2)
                
#generate_CEA_table()