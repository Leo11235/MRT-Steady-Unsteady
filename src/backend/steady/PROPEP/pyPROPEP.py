'''
Documentation: 
https://github.com/Leo11235/pypropep 
'''


import pypropep as ppp

# takes dictionaries, extracts relevant information, returns
# chamber temperature (T), chamber gas molar weight (Wc), and heat capacity ratio (y)
def runPROPEP(rocket_inputs, rocket_parameters):
    # get values from dictionaries
    fuel_name = rocket_inputs["solid_fuel_type"]
    oxidizer_name = rocket_inputs["liquid_oxidizer_type"]
    OF_ratio = rocket_parameters["average_oxidizer_to_fuel_ratio"]
    chamber_pressure = rocket_inputs["chamber_pressure"] / 101325 # convert from pascal to atm

    # calculations
    ppp.init() # initialize pypropep

    # make sure the propellants match nicely
    try:
        fuel = ppp.PROPELLANTS[fuel_name.upper()]
        oxidizer = ppp.PROPELLANTS[oxidizer_name.upper()]
    except KeyError as e:
        return {"error": f"Invalid propellant name: {e}"}
    
    # create equilibrium object
    eq = ppp.Equilibrium()
    try: 
        # add propellants
        eq.add_propellants_by_mass([(fuel, 1.0), (oxidizer, OF_ratio)])
        # set chamber state
        eq.set_state(P=chamber_pressure)
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

        # add new values to rocket_parameters
        rocket_parameters["chamber_temperature"] = chamber_temp
        rocket_parameters["chamber_gas_molar_weight"] = molar_weight
        rocket_parameters["heat_capacity_ratio"] = heat_ratio

    except Exception as e:
        return {"error": f"pyPROPEP - Error extracting properties: {e}"}
