"""
All the main objects of the simulation are created here:
"""

from datetime import datetime
from pathlib import Path
import json, math, numpy as np

class StateVector:
    """
    Tracks essential variables across timesteps. 
    Acts as a translator between the ODE solver's flat math arrays and the named variables required by the physics functions.
    """
    # To add a new variable in the future, just add its name to this list
    VARIABLES = [
        "n_v",  # tank vapor molar amount [mol]
        "n_l",  # tank liquid molar amount [mol]
        "T_T",  # tank temperature [K]
        "m_o",  # oxidizer mass currently inside the chamber [kg]
        "m_f",  # fuel mass currently inside the chamber [kg]
        "p_C",  # chamber pressure [Pa]
        "r_f",  # fuel port inner radius [m]
        "sx_R", # horizontal position [m]
        "sy_R", # altitude ASL [m]
        "vx_R", # horizontal velocity [m/s]
        "vy_R"  # vertical velocity [m/s]
    ]
    
    # converts dict of state variables into 1-D array; required by solve_ivp
    @classmethod
    def to_array(cls, state_dict: dict) -> list:
        try:
            return [state_dict[var] for var in cls.VARIABLES]
        except KeyError as e:
            raise KeyError(f"Cannot pack state vector array. Missing required variable: {e}")

    # takes 1-D array of state variables & uses the VARIABLES list to make a dict of state variables
    @classmethod
    def unpack(cls, y: list) -> dict:
        if len(y) != len(cls.VARIABLES):
            raise ValueError(f"State vector length mismatch. Expected {len(cls.VARIABLES)}, got {len(y)}.")
        # zip pairs the variable names with the numbers in the array seamlessly
        return dict(zip(cls.VARIABLES, y))
    
    
class History:
    """
    Contains a full account of all rocket constants, time-changing derived variables, simulation events
    """
    
    def __init__(self, rocket_inputs: dict):
        # static variables (never change during the simulation)
        self.static_data = rocket_inputs
        
        # time-series data (appended to every timestep)
        self.time_series = {"time": [], "phase": []}
        for var in StateVector.VARIABLES:
            self.time_series[var] = []
            
        # derived variables added in to the main time_series dict in the export() function below
        self.derived_series = {}
        
        # log warnings, phase transitions, etc
        self.events_log = []
    
    # for debugging purposes
    def print_self(self):
        print(self.time_series)
        print(self.derived_series)
        print(self.events_log)
    
    # add a single timestep of the simulation to history
    def log_timestep(self, t: float, state_dict: dict, derived_dict: dict = None, phase: str = None):
        # log time & phase
        self.time_series["time"].append(t)
        self.time_series["phase"].append(phase)
        
        # log all state variables
        for var, value in state_dict.items():
            self.time_series[var].append(value)
            
        # log all derived variables (thrust, O/F ratio, etc)
        if derived_dict:
            for key, value in derived_dict.items():
                if key not in self.derived_series:
                    self.derived_series[key] = [] # Create the list if we haven't seen this variable yet
                self.derived_series[key].append(value)

    def log_event(self, t: float, event_type: str, message: str):
        """
        Records an event with the appropriate timestep
        """
        if event_type == "PHASE_TRANSITION": 
            self.events_log.append({
                "t_s": t,
                "event_type": event_type,
                "message": message})
            
        elif event_type == "WARNING":
            return ##### need to finish

        else: 
            raise ValueError(f"Unrecognized event type: '{event_type}'.")
    
    
    def compute_performance(self) -> dict:
        """
        Computes overall and per-phase performance metrics from the logged time series.
        """
        if not self.time_series["time"]:
            return {}

        t = np.array(self.time_series["time"])
        phases = self.time_series.get("phase", [None] * len(t))
        n_v = np.array(self.time_series["n_v"])
        n_l = np.array(self.time_series["n_l"])
        p_C = np.array(self.time_series["p_C"])
        r_f = np.array(self.time_series["r_f"])
        sy_R = np.array(self.time_series["sy_R"])
        vx_R = np.array(self.time_series["vx_R"])
        vy_R = np.array(self.time_series["vy_R"])

        F_thrust = np.array(self.derived_series.get("F_thrust", np.zeros(len(t))))
        OF = np.array(self.derived_series.get("OF", np.full(len(t), np.nan)))
        T_c = np.array(self.derived_series.get("T_c", np.full(len(t), np.nan)))

        ri = self.static_data
        g_SL = 9.80665
        launch_alt = ri.get("launch_site_altitude_asl_m", 0.0)

        # Molar weight of oxidizer: derived from initial conditions to avoid needing constants dict
        ox_mass_initial = ri.get("tank_oxidizer_mass_kg", 0.0)
        n_ox_0 = float(n_v[0] + n_l[0])
        W_o = ox_mass_initial / n_ox_0 if n_ox_0 > 0 else 0.044013

        # Fuel grain geometry
        R_f    = ri.get("chamber_fuel_external_radius_m", 0.0)
        rho_f  = ri.get("chamber_fuel_density_kgm3", 900.0)
        L_f    = ri.get("chamber_fuel_length_m", 0.0)
        fuel_mass_initial = ri.get("chamber_fuel_mass_kg", math.pi * rho_f * L_f * (R_f**2 - float(r_f[0])**2))

        # -------------------------------------------------------------------------
        # Helper functions
        # -------------------------------------------------------------------------
        def phase_mask(name):
            return np.array([p == name for p in phases])

        def safe_max(arr, mask):
            vals = arr[mask]
            vals = vals[~np.isnan(vals)]
            return float(np.max(vals)) if len(vals) > 0 else None

        def safe_mean(arr, mask):
            vals = arr[mask]
            vals = vals[~np.isnan(vals)]
            return float(np.mean(vals)) if len(vals) > 0 else None

        def trapz_phase(values, mask):
            idx = np.where(mask)[0]
            if len(idx) < 2:
                return 0.0
            return float(np.trapz(values[idx], t[idx]))

        BURN_PHASES    = {"phase_1", "phase_2", "phase_3", "phase_4a", "phase_4c"}
        DESCENT_PHASES = {"phase_5", "phase_6", "phase_7"}
        ALL_PHASES     = ["phase_1", "phase_2", "phase_3", "phase_4a", "phase_4c",
                          "phase_5", "phase_6", "phase_7"]

        burn_mask    = np.array([p in BURN_PHASES for p in phases])
        burn_indices = np.where(burn_mask)[0]
        burnout_idx  = int(burn_indices[-1]) if len(burn_indices) > 0 else -1

        # -------------------------------------------------------------------------
        # Overall metrics
        # -------------------------------------------------------------------------
        burntime        = float(t[burnout_idx] - t[0]) if burnout_idx >= 0 else 0.0
        total_impulse   = trapz_phase(F_thrust, burn_mask)
        peak_thrust     = safe_max(F_thrust, burn_mask) or 0.0
        avg_thrust      = total_impulse / burntime if burntime > 0 else 0.0
        peak_p_C        = safe_max(p_C, burn_mask) or 0.0
        peak_T_c        = safe_max(T_c, burn_mask)
        avg_OF          = safe_mean(OF, burn_mask)

        dry_mass            = ri.get("rocket_dry_mass_kg", 0.0)
        initial_rocket_mass = dry_mass + ox_mass_initial + fuel_mass_initial
        pad_T_W             = (peak_thrust / (initial_rocket_mass * g_SL)
                               if initial_rocket_mass > 0 else None)

        apogee_asl = float(np.max(sy_R))
        apogee_agl = apogee_asl - launch_alt

        n_ox_burnout    = float(n_v[burnout_idx] + n_l[burnout_idx]) if burnout_idx >= 0 else n_ox_0
        ox_consumed     = (n_ox_0 - n_ox_burnout) * W_o
        ox_remaining    = n_ox_burnout * W_o
        r_f_burnout     = float(r_f[burnout_idx]) if burnout_idx >= 0 else float(r_f[0])
        fuel_remaining  = math.pi * rho_f * L_f * (R_f**2 - r_f_burnout**2)
        fuel_consumed   = fuel_mass_initial - fuel_remaining

        # -------------------------------------------------------------------------
        # Per-phase metrics
        # -------------------------------------------------------------------------
        by_phase = {}
        for phase_name in ALL_PHASES:
            mask = phase_mask(phase_name)
            if not mask.any():
                continue

            idx            = np.where(mask)[0]
            phase_t_start  = float(t[idx[0]])
            phase_t_end    = float(t[idx[-1]])
            phase_duration = phase_t_end - phase_t_start

            entry = {
                "t_start_s":  phase_t_start,
                "t_end_s":    phase_t_end,
                "duration_s": phase_duration,
            }

            if phase_name in BURN_PHASES:
                phase_impulse   = trapz_phase(F_thrust, mask)
                phase_pk_thrust = safe_max(F_thrust, mask) or 0.0
                phase_avg_thrust = (phase_impulse / phase_duration
                                    if phase_duration > 0 else 0.0)

                # Ox consumed: from molar amounts at phase boundaries
                phase_n_ox_start = float(n_v[idx[0]]  + n_l[idx[0]])
                phase_n_ox_end   = float(n_v[idx[-1]] + n_l[idx[-1]])
                phase_ox_consumed = (phase_n_ox_start - phase_n_ox_end) * W_o

                # Fuel consumed: from fuel port radius change
                # m_f = π * ρ_f * L_f * (R_f² - r_f²); as r_f grows, m_f shrinks
                phase_fuel_consumed = (math.pi * rho_f * L_f *
                                       (float(r_f[idx[-1]])**2 - float(r_f[idx[0]])**2))

                entry.update({
                    "total_impulse_Ns":          phase_impulse,
                    "peak_thrust_N":             phase_pk_thrust,
                    "average_thrust_N":          phase_avg_thrust,
                    "peak_chamber_pressure_Pa":  safe_max(p_C, mask) or 0.0,
                    "average_OF_ratio":          safe_mean(OF, mask),
                    "peak_chamber_temperature_K": safe_max(T_c, mask),
                    "ox_mass_consumed_kg":       float(phase_ox_consumed),
                    "fuel_mass_consumed_kg":     float(phase_fuel_consumed),
                })

            elif phase_name in DESCENT_PHASES:
                v_mag = np.sqrt(vx_R[mask]**2 + vy_R[mask]**2)
                entry.update({
                    "peak_velocity_ms":     float(np.max(v_mag)) if len(v_mag) > 0 else 0.0,
                    "terminal_velocity_ms": float(v_mag[-1])    if len(v_mag) > 0 else 0.0,
                })

            by_phase[phase_name] = entry

        return {
            "overall": {
                "burntime_s":                   burntime,
                "total_impulse_Ns":             total_impulse,
                "peak_thrust_N":                peak_thrust,
                "average_thrust_N":             avg_thrust,
                "peak_chamber_pressure_Pa":     peak_p_C,
                "peak_chamber_temperature_K":   peak_T_c,
                "average_OF_ratio":             avg_OF,
                "pad_thrust_to_weight":         pad_T_W,
                "apogee_m_asl":                 apogee_asl,
                "apogee_m_agl":                 apogee_agl,
                "ox_mass_available_kg":         ox_mass_initial,
                "fuel_mass_available_kg":       fuel_mass_initial,
                "ox_mass_consumed_kg":          float(ox_consumed),
                "fuel_mass_consumed_kg":        float(fuel_consumed),
                "ox_mass_remaining_kg":         float(ox_remaining),
                "fuel_mass_remaining_kg":       float(fuel_remaining),
                "total_propellant_available_kg": ox_mass_initial + fuel_mass_initial,
                "total_propellant_consumed_kg": float(ox_consumed + fuel_consumed),
            },
            "by_phase": by_phase
        }
    
    def compute_metadata(self) -> dict:
        """
        Helper for the export function. Computes things like total burntime, total produced impulse, etc
        """
        if not self.time_series["time"]:
            return {"null"}
        total_simulation_time = self.time_series["time"][-1]        
        return {
            "total_timesteps": len(self.time_series["time"]),
            "total_simulation_time": total_simulation_time, 
        }

    def export(self, rocket_inputs: dict, finalized_warnings: dict = None) -> dict:
        """
        Sends results to JSON storage
        """
        # project anchor & target directory pathing
        project_root = Path(__file__).resolve().parents[4] 
        output_dir = project_root / "user_data" / "simulation_results"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # timestamp name signature: YYYY_MM_DD_HH_MM_SS.json
        if rocket_inputs.get("metadata", {}).get("simulation_name") != ("" or None):
            file_path = output_dir / rocket_inputs["metadata"]["simulation_name"]
        else:
            file_path = output_dir / f"{datetime.now().strftime("%Y_%m_%d_%H_%M_%S")}.json"
        
        # helper to convert NaNs to None for JSON compatibility
        def sanitize_nans(array):
            return [None if isinstance(x, float) and math.isnan(x) else x for x in array]
        
        # put all time-changing data into one dict
        changing_data = {}
        for key, val in self.time_series.items():
            changing_data[key] = sanitize_nans(val)
        for key, val in self.derived_series.items():
            changing_data[key] = sanitize_nans(val)
        
        # assemble json
        sim_results = {
            "metadata": self.compute_metadata(),
            "performance": self.compute_performance(),
            "static": {"rocket_inputs": rocket_inputs},
            "event_log": self.events_log,
            "warnings": finalized_warnings if finalized_warnings else "disabled",
            "data": changing_data,
        }
        
        # write to JSON
        with open(file_path, "w") as f:
            json.dump(sim_results, f, indent=4)
            
        print(f"\nSimulation data exported to:\n -> {file_path}")
        return file_path