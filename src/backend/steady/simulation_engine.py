from src.backend.steady.PROPEP.pyPROPEP import runPROPEP
from src.backend.steady import kinematics, prop_calculations

def simulate_hotfire(rocket_inputs, rocket_parameters, simulation_settings, constants_dict):
    # step 1
    prop_calculations.CV2_calculations(rocket_inputs, rocket_parameters)
    # step 2: propep
    runPROPEP(rocket_inputs, rocket_parameters)
    # step 3
    prop_calculations.CV3_calculations(rocket_inputs, rocket_parameters, constants_dict)
    # output
    return rocket_parameters

# converges on an ideal fuel mass given a target apogee; returns rocket_inputs, rocket_parameters, flight_dict
def simulate_fuel_mass_convergence(rocket_inputs, rocket_parameters, simulation_settings, constants_dict):
    # set initial bogus values so the while loop can start
    lower_bound = 0 # lower bound for inner fuel radius
    upper_bound = rocket_inputs["fuel_external_radius"] # upper bound
    rocket_parameters = {
        "reached_apogee" : float("-inf"),
        "initial_internal_fuel_radius": max(rocket_inputs["fuel_external_radius"]/2, 0.01) # initial internal fuel radius guess     
    }
    
    # fetch algorithm constraints safely
    tolerance = simulation_settings["tolerated_apogee_difference"]
    smallest_radius = simulation_settings["smallest_allowed_inner_fuel_radius"]
    
    # run simulation with a certain fuel mass, check apogee, refine guess, run again, .... until the final apogee reaches the desired value
    i=1
    while(True):
        # simulate rocket
        rocket_parameters = simulate_hotfire(rocket_inputs, rocket_parameters, simulation_settings, constants_dict)
        flight_dict = kinematics.simulate_rocket_ascent(rocket_inputs, rocket_parameters, simulation_settings, constants_dict)
        
        # get apogee
        rocket_parameters["reached_apogee"] = flight_dict["altitude"][-1]
        if correct_apogee_reached(rocket_inputs, rocket_parameters, tolerance):
            print(f'    LOOP {i} - FINAL APOGEE: {round(rocket_parameters["reached_apogee"], 1)} meters ({round(abs(rocket_parameters["reached_apogee"] - rocket_inputs["target_apogee"]), 5)} meters off from target)')
            return (rocket_parameters, flight_dict)
        else: 
            # check if rocket failed to reach apogee even with lowest allowed internal fuel radius
            if rocket_parameters["initial_internal_fuel_radius"] == smallest_radius: # AND not reached apogee, but that possibility has already been filtered out
                # if the code makes it to here, the rocket cannot reach the target apogee
                print(f"    ROCKET CANNOT REACH APOGEE (final apogee reached: {rocket_parameters["reached_apogee"]} meters)")
                return (rocket_parameters, flight_dict)
            # refine inner fuel radius guess and try again
            if rocket_parameters["reached_apogee"] > rocket_inputs["target_apogee"]:
                lower_bound = rocket_parameters["initial_internal_fuel_radius"] # if the rocket flies too high, increase inner radius (less fuel)
            elif rocket_parameters["reached_apogee"] < rocket_inputs["target_apogee"]:
                upper_bound = rocket_parameters["initial_internal_fuel_radius"] # & vice versa
            else: 
                print("ERROR: this should be impossible")
        
        print(f'    Loop {i} of simulation, apogee achieved: {round(rocket_parameters["reached_apogee"], 1)} meters')
        
        # reset rocket parameters and re-guess initial internal fuel radius
        rocket_parameters = {"initial_internal_fuel_radius": (upper_bound + lower_bound) / 2}
        
        # if the initial internal fuel radius dips below the smallest allowed amount, run the simulation with the smallest allowed amount instead
            # if that still fails, that means the rocket cannot reach the apogee and the simulation is aborted
        if rocket_parameters["initial_internal_fuel_radius"] < smallest_radius:
            rocket_parameters["initial_internal_fuel_radius"] = smallest_radius
            lower_bound = smallest_radius
        
        i+=1

# helper function to check whether the desired apogee was reached for the rocket
def correct_apogee_reached(rocket_inputs, rocket_parameters, tolerance):
    return abs(rocket_parameters["reached_apogee"] - rocket_inputs["target_apogee"]) <= tolerance
