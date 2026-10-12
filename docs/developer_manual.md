# MRT Steady-Unsteady Flight Simulator Program Reference

--- 

## Table of contents

1. [Introduction](#1-Introduction)
2. [The input system](#2-The-input-system)
3. [Testing suite](#3-Testing-suite)
4. [Backend: Steady](#4-Backend-Steady)
5. [Backend: Unsteady](#4-Backend-Unsteady)

---

## 1. Introduction

Steady operates at a fixed point, neglecting any transient effects. It does algebraic hotfire performance, iterating over the fuel mass to hit a target apogee. It can also run parametric sweeps over inputs. It is useful for comparing a range of possible rocket designs, but any single run has a large margin of error. 

Unsteady is a six control volume ODE integration program that takes the rocket through ignition, the main burn, blowout, and post-burn flight. Takes longer and demands more inputs, but more accurate. 

Both programs take in and output a JSON file. You can find their main entry points in `src\backend\steady\steady_main.py\run_steady()` and `src\backend\unsteady\engine\phase_runner.py\run_unsteady()`, respectively. 

In general, the program is organized into three file trees: 
- `src\`: Contains all of the main code for the backend, UI, and interlinking stuff. 
- `user_data\`: Contains simulation presets, past saved runs, and user settings for the UI. 
- `src\backend\{steady,unsteady}\static_data\` folders: contains N2O saturation data, CEA combustion tables, atmosphere data, the PROPEP table, and more. 

The UI is a customtkinter interface that allows a user to easily interact with both. It never touches the physics or engine and was made by an LLM. The important part is that it works. 


---

## 2. The input system

Inputs to both steady and unsteady are passed entirely through JSONs. **Every physical value in a config file is a `[value, unit]` pair.** For example: 

```jsonc
"chamber_pressure": [3447000, "Pa"],
"launch_angle": [6, "deg"],
"drag_coefficient": [0.641606, "."],
```

All values are converted to SI before being sent to the physics, then back to the user's preferred unit format. The user-facing unit system options are SI (International System), IMP (Imperial), and MRT (mishmash of SI and IMP; MRT's engineers like to use kg for masses, inches for lengths, etc). 

A `"."` for the unit pair symbolizes a dimensionless input. Unused alternatives (the "one or the other" fields) use `null` for the value and keep their unit: `"tank_internal_length": [null, "m"]`. Model selectors in unsteady (e.g., `"model": "SPI"`) and `"liquid_oxidizer_type"` / `"solid_fuel_type"` in steady are and exception to all this and use plain strings rather than pairs. 

### 2.1 `src/common/variable_conversions.py`

`src/common/variable_conversions.py` is responsible for converting all input units to SI, and back to their original unit system. 


Categories include length, area, volume, mass, density, pressure, temperature, time, angle, velocity, acceleration, force, impulse, mass flow, molar mass, dimensionless. The table below shows what the main functions in the file do. 


| Function | Does |
|---|---|
| `to_SI(value, unit)` / `from_SI(value, unit)` | scalar conversion |
| `convert(value, from_unit, to_unit)` | between any two same-category units |
| `pair_to_SI(pair)` | takes a `[value, pair]` list and returns an SI float of the value: `[6, "deg"] --> 0.1047` |
| `pair_from_SI(value, unit)` | the inverse, returns a pair |
| `block_to_SI(block, skip=("model",))` | whole dict of pairs at once |
| `category_of(unit)`, `units_in_category(cat)`, `is_known_unit(unit)` | registry queries |
| `unit_for_system(category, system)` | display unit for SI / IMP / MRT |


### 2.2 Random notes

- One quirk of the program is that all three systems (SI/IMP/MRT) are user oriented rather than science/physics oriented. This means that, using SI as an example, the launch angle is in degrees rather than radians by default. Hardware lengths are in cm, and distances are in meters. Not exactly SI, but easier to use. 
- `"g"` is grams, gravitational acceleration is `"g0"`.
- `"kn"` is knots, kilonewtons are `"kN"`. Case sensitive.
- `"ms"` is milliseconds, velocity is `"m/s"`.
- Users always use diameters, while the physics always uses radii. This conversion also happens in the SI conversion fields via `field_registry.steady_schema_keys()`. 
- Some physical inputs have defaults, for example Fuel grain density at 900 kg/m³. This information is kept in `src/common/static_data/default_inputs.jsonc`. 

---

## 3. Testing suite

There are quite a few backend tests in `tests\`. Running these often while making changes to the backend is recommended. You can run them via `python -m tests.backend_tests`. 

The `backend_tests` function comes with several options:
- `steady_tests_only=True` or `unsteady_tests_only=True` to run only the steady or unsteady tests,
- `only:[str]`to run only some specific tests,
- `timeout:[int]` to abort remaining tests after int seconds have passed, 
- `reports=True` to generate a report of all the tests you ran. 

---

## 4. Backend: Steady

### 4.1 Simulation types

- `hotfire`: one operating point, straight through the algebra.
- `fuel_mass_convergence`: iterate fuel mass until the predicted apogee lands within tolerance of `target_apogee`.
- `parametric_study`: sweep combinations of inputs and record the outputs.

### 4.2 Config 

Top level: `metadata`, `simulation_settings`, `rocket_inputs`, and for sweeps `parametric_study_inputs`.

`rocket_inputs` is split into three blocks: one baso block needed for every simulation type, one "kinematics" block needed by convergence and parametric, and one "hotfire" block needed only by hotfire simulations. The reason for the distinction is that hotfires take in a specified fuel mass and do not run any flight calculations, while convergence and parametric iterate toward the correct fuel mass given a target apogee, hence they have no need for a fuel mass input. 

`output_units` in `simulation_settings` picks the unit system the output JSON uses. Test configs use `"SI"` so the checks can compare against fixed numbers.

### 4.3 Flow

`steady_main.run_steady()` --> 
`variable_initialization` unpacks and converts --> 
`simulation_engine` runs the chosen loop --> 
`prop_calculations` supplies thrust, Isp and chamber conditions (via PROPEP interpolation) --> 
`kinematics` flies the 2-DOF trajectory --> 
results written to `user_data/simulation_results/steady/<name>.json`.

Sweeps go through `parametric_study.py`, which drives the same engine once per combination and collects the results into a grid.

---

## 5. Backend: Unsteady

### 5.1 The six control volumes

| CV | Models available |
|---|---|
| CV1 tank | `saturated_equilibrium` |
| CV2 valve | `instant`, `linear`, `sigmoid` |
| CV3 injector | `SPI` |
| CV4 chamber | `0D_quasi_steady` |
| CV5 nozzle | `1D_frozen` |
| CV6 trajectory | `2dof` |

Each CV block in the config carries a `"model"` string plus that model's inputs. The UI shows only the fields the selected model actually uses: `instant` shows none, `linear` shows the time constant, `sigmoid` shows the half-time and steepness.

### 5.2 Phases

The unsteady simulation is split into chronological phases: ignition, liquid blowdown, gaseous blodown, burnout, coasting, drag parachute descent, and main parachute descent. Each one runs different physics or calculations. Ignition handles roughly the first three milliseconds of combustion, in which time the chamber temperature and pressure explode. This phase runs a conservative integration method (Backward Differentiation Formula) which is slow but relatively insensitive to differential spikes. Liquid and gas blowdown are the most important distinction, as the tank physics changes significantly between the two. 

Phases have a number of ways to start and end. For example, a rocket in the liquid blowdown phase can exit that phase by (1) nominally running out of liquid N2O, in which case it transitions to the gasous blowdown phase, (2) running out of solid fuel, in which case we abort the program since this is a catastrophic error, or (3) exceeding the maximum time allowed for this part of the simulation, which also aborts the program. 

`phase_runner.py` steps the solver phase by phase. `transitions.py` holds the event functions that end each phase; `registry.py` maps a phase to the set of CV functions active during it; `rhs.py` composes those into the derivative function scipy integrates. The integration is handled by scipy's LSODA, which automatically switches between stiff and non-stiff ODE-solving methods. 

### 5.3 Warnings

`engine/warnings.py` has two halves. `warn_initialization_limits()` checks the inputs before anything integrates: ullage fraction bounds, fuel grain length, port radius, geometric possibility, regression coefficients. Runtime warnings accumulate during the integration. Each entry has a severity of `critical`, `caution` or `advisory` and a message.

### 5.4 Output

`objects.export()` writes `user_data/simulation_results/unsteady/<name>/ sim_data.json`, optionally with `graphs.pdf` and a `graphs/` folder of PNGs. The JSON carries `static` (inputs as the physics saw them), `performance` (overall and per-phase), `event_log`, `warnings` and the full time series.

---

