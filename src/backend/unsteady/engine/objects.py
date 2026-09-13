"""
All the main objects of the simulation are created here
"""

from datetime import datetime
from pathlib import Path
import json, math, numpy as np

from src.common.plotting.unsteady_plots import unsteady_results

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
        
        # how the run ended; filled in by phase_runner once it knows
        # these values should get updated by the simulation before returning to user, otherwise raises an error
        self.terminal_state = "unknown"
        self.completed_nominally = False
        self.terminal_reason = "Simulation did not report a terminal state."
    
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

    # record an event with the appropriate timestep
    def log_event(self, t: float, event_type: str, message: str):
        # PHASE_TRANSITION and any ABORT_* event get logged the same way
        if event_type == "PHASE_TRANSITION" or event_type.startswith("ABORT"): 
            self.events_log.append({
                "t": t,
                "event_type": event_type,
                "message": message})

        else: 
            raise ValueError(f"Unrecognized event type: '{event_type}'.")
    
    # record how the run ended, from the TERMINAL_STATES entry in transitions.py
    def set_terminal_state(self, terminal_info: dict, t: float):
        self.terminal_state = terminal_info["code"]
        self.completed_nominally = terminal_info["completed_nominally"]
        self.terminal_reason = terminal_info["message"]
        self.t_terminal = t
    
    # helper functions for performance calculations
    # extracts the maximum value from an array using a boolean mask, ignoring NaNs
    def _safe_max(self, array: np.ndarray, mask: np.ndarray) -> float | None:
        valid_values = array[mask]
        valid_values = valid_values[~np.isnan(valid_values)]
        return float(np.max(valid_values)) if len(valid_values) > 0 else None

    # extracts the mean average from an array using a boolean mask, ignoring NaNs
    def _safe_mean(self, array: np.ndarray, mask: np.ndarray) -> float | None:
        valid_values = array[mask]
        valid_values = valid_values[~np.isnan(valid_values)]
        return float(np.mean(valid_values)) if len(valid_values) > 0 else None

    # time-weighted mean of a series over a window
    def _time_average(self, time_array: np.ndarray, value_array: np.ndarray, mask: np.ndarray) -> float | None:
        indices = np.where(mask)[0]
        if len(indices) < 2:
            return self._safe_mean(value_array, mask)
        span = float(time_array[indices[-1]] - time_array[indices[0]])
        if span <= 0:
            return self._safe_mean(value_array, mask)
        return self._integrate_time_series(time_array, value_array, mask) / span

    # average O/F as the ratio of the masses actually consumed
    def _mass_ratio_OF(self, ox_consumed: float, fuel_consumed: float, OF: np.ndarray, mask: np.ndarray) -> float | None:
        if fuel_consumed and fuel_consumed > 1e-12 and ox_consumed is not None:
            return float(ox_consumed / fuel_consumed)
        return self._safe_mean(OF, mask)

    # performs numerical integration for a given set of values over time, used primarily to calculate total impulse from the thrust curve
    def _integrate_time_series(self, time_array: np.ndarray, value_array: np.ndarray, mask: np.ndarray) -> float:
        valid_indices = np.where(mask)[0]
        if len(valid_indices) < 2:
            return 0.0
        # np.trapezoid replaces the deprecated np.trapz in NumPy 2.0+
        return float(np.trapezoid(value_array[valid_indices], time_array[valid_indices]))
    
    # peak TtW ratio and how far off the pad the rocket got
    def launch_metrics(self) -> dict:
        t = self.time_series["time"]
        if not t:
            return {
                "peak_thrust": 0.0, 
                "peak_thrust_to_weight": None, 
                "altitude_gain": 0.0,
                "reached_operating_point": False,
            }

        ri = self.static_data
        F = self.derived_series.get("F_thrust", [])
        peak_thrust = max((v for v in F if v is not None and not math.isnan(v)), default=0.0)

        ox_mass_initial = ri.get("tank_oxidizer_mass", 0.0)
        r_f = self.time_series["r_f"]
        fuel_mass_initial = ri.get("chamber_fuel_mass", math.pi * ri.get("chamber_fuel_density", 900.0) * ri.get("chamber_fuel_length", 0.0) * (ri.get("chamber_fuel_external_radius", 0.0) ** 2 - float(r_f[0]) ** 2)) if r_f else 0.0
        initial_mass = ri.get("rocket_dry_mass", 0.0) + ox_mass_initial + fuel_mass_initial

        sy_R = self.time_series["sy_R"]
        launch_alt = ri.get("launch_site_altitude_asl", 0.0)

        # anything past phase_1 means ignition succeeded and the engine reached its operating point
        phases = self.time_series.get("phase", [])
        reached_operating_point = any(p not in (None, "phase_1") for p in phases)

        return {
            "peak_thrust": peak_thrust,
            "initial_mass": initial_mass,
            "peak_thrust_to_weight": (peak_thrust / (initial_mass * 9.80665)) if (initial_mass > 0 and peak_thrust > 1) else None,
            "altitude_gain": (max(sy_R) - launch_alt) if sy_R else 0.0,
            "reached_operating_point": reached_operating_point,
        }
    
    
    def compute_performance(self) -> dict:
        """
        Computes overall and per-phase performance metrics from the logged time series
        """
        if not self.time_series["time"]:
            return {}

        #### convert time series lists to NumPy arrays for vectorized math
        t = np.array(self.time_series["time"])
        phases = np.array(self.time_series.get("phase", [None] * len(t)))
        n_v = np.array(self.time_series["n_v"]) # vapor moles in tank
        n_l = np.array(self.time_series["n_l"]) # liquid moles 
        p_C = np.array(self.time_series["p_C"]) # chamber pressure
        r_f = np.array(self.time_series["r_f"]) # inner fuel radius
        m_o_c = np.array(self.time_series["m_o"]) # ox mass
        m_f_c = np.array(self.time_series["m_f"]) # fuel mass
        cstar = np.array(self.derived_series.get("cstar", np.full(len(t), np.nan))) # cstar efficiency
        F_thrust = np.array(self.derived_series.get("F_thrust", np.zeros(len(t)))) # thrust
        OF = np.array(self.derived_series.get("OF", np.full(len(t), np.nan))) # OF ratio
        T_c = np.array(self.derived_series.get("T_c", np.full(len(t), np.nan))) # chamber temp
        sx_R = np.array(self.time_series["sx_R"]) # horizontal distance from launchsite
        sy_R = np.array(self.time_series["sy_R"]) # altitude
        vx_R = np.array(self.time_series["vx_R"]) # horizontal velocity
        vy_R = np.array(self.time_series["vy_R"]) # vertical velocity
        ax_R = np.array(self.derived_series.get("ax_R", np.full(len(t), np.nan))) # horizontal acceleration
        ay_R = np.array(self.derived_series.get("ay_R", np.full(len(t), np.nan))) # vertical acceleration
        a_mag = np.sqrt(ax_R**2 + ay_R**2) # acceleration magnitude
        
        #### extract initial constants
        ri = self.static_data
        launch_alt = ri.get("launch_site_altitude_asl", 0.0)
        ox_mass_initial = ri.get("tank_oxidizer_mass", 0.0)
        n_ox_0 = float(n_v[0] + n_l[0]) if len(n_v) > 0 else 0.0
        W_o = ox_mass_initial / n_ox_0 if n_ox_0 > 0 else 0.044013

        R_f = ri.get("chamber_fuel_external_radius", 0.0)
        rho_f = ri.get("chamber_fuel_density", 900.0)
        L_f = ri.get("chamber_fuel_length", 0.0)
        
        if len(r_f) > 0:
            fuel_mass_initial = ri.get("chamber_fuel_mass", math.pi * rho_f * L_f * (R_f**2 - float(r_f[0])**2))
        else:
            fuel_mass_initial = 0.0

        #### categorize phase groups
        BURN_PHASES = {"phase_1", "phase_2", "phase_3", "phase_4a", "phase_4c"}
        ALL_PHASES = ["phase_1", "phase_2", "phase_3", "phase_4a", "phase_4c", "phase_5", "phase_6", "phase_7"]

        burn_mask = np.isin(phases, list(BURN_PHASES))
        burn_indices = np.where(burn_mask)[0]
        burnout_idx = int(burn_indices[-1]) if len(burn_indices) > 0 else -1

        #### calculate overall metrics
        burntime = float(t[burnout_idx] - t[0]) if burnout_idx >= 0 else 0.0
        total_impulse = self._integrate_time_series(t, F_thrust, burn_mask)
        peak_thrust = self._safe_max(F_thrust, burn_mask) or 0.0
        
        pad_T_W = self.launch_metrics()["peak_thrust_to_weight"]

        n_ox_burnout = float(n_v[burnout_idx] + n_l[burnout_idx]) if burnout_idx >= 0 else n_ox_0
        ox_consumed = (n_ox_0 - n_ox_burnout) * W_o
        
        r_f_burnout = float(r_f[burnout_idx]) if burnout_idx >= 0 else (float(r_f[0]) if len(r_f) > 0 else 0.0)
        fuel_remaining = math.pi * rho_f * L_f * (R_f**2 - r_f_burnout**2)
        fuel_consumed = fuel_mass_initial - fuel_remaining

        # peak acceleration during burn
        peak_acceleration = self._safe_max(a_mag, burn_mask) or 0.0

        # Isp (total)
        g0 = 9.80665
        propellant_consumed = ox_consumed + fuel_consumed
        specific_impulse = (total_impulse / (g0 * propellant_consumed)) if propellant_consumed > 1e-9 else 0.0

        # c* is only meaningful once there is actually gas in the chamber. ignore portions of the run where CV5 assumes 1000 m/s
        combusting = burn_mask & (m_o_c >= 1e-4) & (m_f_c >= 1e-4)
        # logged series is the real c*
        eta_cstar = ri.get("chamber_cstar_efficiency", 1.0) or 1.0
        average_cstar_actual = self._time_average(t, cstar, combusting)
        average_cstar_theoretical = ((average_cstar_actual / eta_cstar) if average_cstar_actual is not None else None)

        #### calculate per-phase mtrics
        by_phase = {}
        for phase_name in ALL_PHASES:
            mask = (phases == phase_name)
            if not mask.any():
                continue
        
            idx = np.where(mask)[0]
            phase_duration = float(t[idx[-1]] - t[idx[0]])
            phase_v = np.sqrt(vx_R[mask]**2 + vy_R[mask]**2)
            
            entry = {
                "t_start": float(t[idx[0]]),
                "t_end": float(t[idx[-1]]),
                "duration": phase_duration,
                "peak_velocity": float(np.max(phase_v)) if len(phase_v) > 0 else 0.0,
                "terminal_velocity": float(phase_v[-1]) if len(phase_v) > 0 else 0.0,
                "peak_acceleration": self._safe_max(a_mag, mask) or 0.0,
            }

            if phase_name in BURN_PHASES:
                phase_impulse = self._integrate_time_series(t, F_thrust, mask)
                phase_ox_consumed = (float(n_v[idx[0]] + n_l[idx[0]]) - float(n_v[idx[-1]] + n_l[idx[-1]])) * W_o
                phase_fuel_consumed = math.pi * rho_f * L_f * (float(r_f[idx[-1]])**2 - float(r_f[idx[0]])**2)

                entry.update({
                    "total_impulse": phase_impulse,
                    "peak_thrust": self._safe_max(F_thrust, mask) or 0.0,
                    "average_thrust": (phase_impulse / phase_duration) if phase_duration > 0 else 0.0,
                    "peak_chamber_pressure": self._safe_max(p_C, mask) or 0.0,
                    "average_OF_ratio": self._mass_ratio_OF(phase_ox_consumed, phase_fuel_consumed, OF, mask),
                    "peak_chamber_temperature": self._safe_max(T_c, mask),
                    "ox_mass_consumed": float(phase_ox_consumed),
                    "fuel_mass_consumed": float(phase_fuel_consumed),
                })

            by_phase[phase_name] = entry

        return {
            "overall": {
                "burntime": burntime,
                "total_impulse": total_impulse,
                "peak_thrust": peak_thrust,
                "average_thrust": (total_impulse / burntime) if burntime > 0 else 0.0,
                "peak_chamber_pressure": self._safe_max(p_C, burn_mask) or 0.0,
                "peak_chamber_temperature": self._safe_max(T_c, burn_mask),
                "average_OF_ratio": self._mass_ratio_OF(ox_consumed, fuel_consumed, OF, burn_mask),
                "peak_acceleration": peak_acceleration,
                "specific_impulse": specific_impulse,
                "average_cstar_actual": average_cstar_actual,
                "average_cstar_theoretical": average_cstar_theoretical,
                "pad_thrust_to_weight": pad_T_W,
                "apogee_asl": float(np.max(sy_R)) if len(sy_R) > 0 else 0.0,
                "apogee_agl": (float(np.max(sy_R)) - launch_alt) if len(sy_R) > 0 else 0.0,
                "landing_downrange": float(abs(sx_R[-1])) if len(sx_R) > 0 else 0.0,
                "ox_mass_available": ox_mass_initial,
                "fuel_mass_available": fuel_mass_initial,
                "ox_mass_consumed": float(ox_consumed),
                "fuel_mass_consumed": float(fuel_consumed),
                "ox_mass_remaining": float(n_ox_burnout * W_o),
                "fuel_mass_remaining": float(fuel_remaining),
                "total_propellant_available": ox_mass_initial + fuel_mass_initial,
                "total_propellant_consumed": float(ox_consumed + fuel_consumed),
            },
            "by_phase": by_phase
        }
    
    def compute_metadata(self) -> dict:
        """
        Calculates administrative simulation metrics
        """
        # initialize metadata dict
        metadata = {
            "terminal_state": self.terminal_state,
            "completed_nominally": self.completed_nominally,
            "terminal_reason": self.terminal_reason,
        }
        
        # if no timesteps recorded, return early
        if not self.time_series["time"]:
            return metadata
        # otherwise, record timestep related info
        metadata["total_timesteps"] = len(self.time_series["time"])
        metadata["total_simulation_time"] = self.time_series["time"][-1]
        return metadata

    def export(self, rocket_inputs: dict, finalized_warnings: dict, rocket_inputs_metadata: dict, output_dir_filepath: Path) -> dict:
        """
        Sends results to JSON storage
        """
        
        # YYYY_MM_DD_HH_MM_SS folder houses output data or <simulation_name> if the user gave one
        foldername = str(rocket_inputs_metadata.get("simulation_name") or "").strip()
        if not foldername:
            foldername = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        
        # project anchor & target directory pathing
        output_dir = Path(output_dir_filepath) / foldername
        output_dir.mkdir(parents=True, exist_ok=True)
        output_json_name = "sim_data.json"
        file_path = output_dir / output_json_name
        
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
        
        # build the folder in <output_dir>/<run_name>, then write sim_data.json inside
        # write to JSON
        with open(file_path, "w") as f:
            json.dump(sim_results, f, indent=4)
            
        print(f"\nSimulation data exported")
        
        # optional outputs, both off by default because rendering every plot adds roughly half a minute to a run that is otherwise seconds long
        save_to_pdf = bool(rocket_inputs_metadata.get("save_to_pdf"))
        save_to_png = bool(rocket_inputs_metadata.get("save_to_png"))

        if save_to_png:
            print(f"\nSaving graphs as PNGs...")
            unsteady_results(
                json_filename=output_json_name,
                json_filepath=output_dir,
                save_to_pdf=False,
                save_to_png=True
            )

        if save_to_pdf:
            # outputs full run report PDF: inputs, performance, phases, events, warnings, graphs, etc
            # independent of any other graphing stuff
            print(f"\nGenerating PDF report...")
            from src.common.unsteady_PDF_report import generate_report
            generate_report(output_dir, sim_results)

        return file_path



