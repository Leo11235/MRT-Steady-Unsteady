'''
Contains functions used to generate the interpolation table 

Documentation: 
https://github.com/Leo11235/pypropep 
'''

import pypropep as ppp
import pandas as pd 
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

ppp.init() # initialize pypropep once for many calls
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# load lookup table
def load_lookup_table():
    json_path = _ROOT_DIR / "Backend" / "Static_data" / "pypropep_lookup_table.json"
    return pd.read_json(json_path, orient="table")
ppp_df_loaded = load_lookup_table()

# calls PROPEP for a single (OF, CP) combination (CP = chamber pressure)
def call_PROPEP(OF, CP, CP_units = "psi", fuel_type = "EICOSANE (PARAFFIN)", oxidizer_type = "NITROUS OXIDE"): 
    # oxidizer to fuel ratio and chamber pressure; units can also be Pa, psi, or atm and the conversion will be handled automatically
    
    # convert CP unit to atm if needed
    if CP_units.lower() == "psi":
        CP = CP/14.696 # convert from psi to atm
    elif CP_units.lower() == "pa":
        CP = CP/101325 # convert from Pa to atm
    elif CP_units.lower() == "atm":
        None
    else:
        raise ValueError("Provide a valid argument for CP_unit")
    
    # make sure the propellants match nicely
    try:
        fuel = ppp.PROPELLANTS[fuel_type.upper()]
        oxidizer = ppp.PROPELLANTS[oxidizer_type.upper()]
    except KeyError as e:
        return {"error": f"Invalid propellant name: {e}"}
    
    # create equilibrium object
    eq = ppp.Equilibrium()
    try: 
        # add propellants
        eq.add_propellants_by_mass([(fuel, 1.0), (oxidizer, OF)])
        # set chamber state
        eq.set_state(P=CP)
    except Exception as e:
        return {"error": f"Error setting up equilibrium state: {e}"}
    
    # get chamber temp, molar weight, and heat ratio
    try: 
        properties = eq.properties
        chamber_temp = getattr(properties, "T", None)
        molar_weight = getattr(properties, "M", None) / 1000 # convert to kg/mol
        # heat ratio is a bit more complicated
        Cp = getattr(properties, "Cp", None)
        Cv = getattr(properties, "Cv", None)
        heat_ratio = Cp / Cv if Cp is not None and Cv is not None else None
        
        return (chamber_temp, molar_weight, heat_ratio)

    except Exception as e:
        return {"error": f"pyPROPEP - Error extracting properties: {e}"}

def generate_pyPROPEP_lookup_table(OF_low_end, OF_high_end, OF_step_size, 
                                   CP_low_end, CP_high_end, CP_step_size, CP_unit,
                                   where_to_save = _ROOT_DIR / "Backend" / "Static_data" / "pypropep_lookup_table.json"):
    pypropep_data = []
    
    # compute the table
    print("OF: ")
    for OF in np.arange(OF_low_end, OF_high_end+OF_step_size, OF_step_size):
        print(OF)
        for CP in np.arange(CP_low_end, CP_high_end+CP_step_size, CP_step_size):
            chamber_temp, molar_weight, heat_ratio = call_PROPEP(OF, CP, CP_units=CP_unit)
            pypropep_data.append({
                'OF': OF, #just to make the indexing ok
                'CP': CP,
                'chamber_temp': chamber_temp,
                'molar_weight': molar_weight,
                'heat_ratio': heat_ratio
            })
    
    # save as json
    ppp_df = pd.DataFrame(pypropep_data)
    ppp_df.set_index(['OF', 'CP'], inplace=True)
    ppp_df.to_json(where_to_save, orient="table", indent = 2)
    
# example use:
temp_path = _ROOT_DIR / "Backend" / "PROPEP" / "temp_pypropep_lookup_file.json"
generate_pyPROPEP_lookup_table(.1, 25, 0.1, 
                               68947.6, # 10 psi lower bound
                               68947600, # 1000 psi upper bound
                               68947.6, # 10 psi step size
                               "Pa", # chamber pressure unit type
                               temp_path) # DONT do this, PROPEP becomes nonsensical with OF values below 1

# plots OF vs CP vs PROPEP output
def plot_surface_multiindex_numeric(df, z_col):
    if z_col not in df.columns:
        raise ValueError(f"{z_col} not in dataframe columns: {df.columns}")

    temp = df.reset_index()

    temp["OF"] = temp["OF"].astype(float)
    temp["CP"] = temp["CP"].astype(float)
    temp[z_col] = temp[z_col].astype(float)

    pivot = temp.pivot(index="CP", columns="OF", values=z_col)

    X, Y = np.meshgrid(pivot.columns.values, pivot.index.values)
    Z = pivot.values

    fig = plt.figure(figsize=(10,7))
    ax = fig.add_subplot(111, projection='3d')

    surf = ax.plot_surface(X, Y, Z, cmap="viridis", edgecolor='k', linewidth=0.5)

    ax.set_xlabel("OF")
    ax.set_ylabel("CP")
    ax.set_zlabel(z_col)

    ax.set_xlim(float(X.min()), float(X.max()))
    ax.set_ylim(float(Y.min()), float(Y.max()))
    ax.set_zlim(float(Z.min()), float(Z.max()))

    fig.colorbar(surf, label=z_col)
    plt.title(f"3D Surface of {z_col} vs OF & CP")
    
# to check if the increments are too large
plot_surface_multiindex_numeric(ppp_df_loaded, "chamber_temp")
plot_surface_multiindex_numeric(ppp_df_loaded, "molar_weight")
plot_surface_multiindex_numeric(ppp_df_loaded, "heat_ratio")

plt.show()