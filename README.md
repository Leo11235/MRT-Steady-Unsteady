# McGill Rocket Team -- Steady-Unsteady Flight Model

A Python tool for modelling, simulating, and optimising a self-pressurising
hybrid rocket engine using liquid nitrous oxide as oxidiser and paraffin
wax as fuel. Supports both steady-state and unsteady (transient)
simulations, parametric design studies, flight-trajectory prediction, and
validation against experimental hot-fire test data.

This guide gets the code running on **Windows**, **macOS**, and **Linux**.

---

## Quick start guide

### Prerequisites
Python 3.13 (https://www.python.org/downloads/)

Git (https://git-scm.com/install/)

### First time setup

First, clone the repository to your local machine and navigate into the project directory:

```bash
git clone https://github.com/Leo11235/MRT-Steady-Unsteady
cd MRT-Steady-Unsteady
```

Open a terminal in the project's root directory (the folder containing requirements.txt; on Windows you can right click on an empty space in the folder and select "Open in Terminal").

Create a virtual environment and install the required dependencies by running the following commands: 

```
# Windows  (PowerShell or cmd)
py -3.13 -m venv .venv
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
.venv\Scripts\activate
python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.txt
python main.py

# macOS / Linux
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.txt
python main.py
```
Note: if `.venv\Scripts\activate` gives an error, try `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` first. 

### Subsequent usage 
After the program has run for the first time, the following commands suffice to run the program: 

```
# Windows  (PowerShell or cmd)
.venv\Scripts\activate
python main.py

# macOS / Linux
source .venv/bin/activate
python main.py
```


## Usage & Configuration

The simulation physics are decoupled from the rocket parameters. You do not need to modify the core Python scripts to test a new engine or flight profile.

All rocket configurations are stored as `.jsonc` files.
1. Navigate to `user_data/simulation_configs/`. You will see a folder for steady configs and one for unsteady configs. 
2. Duplicate `(un)steady_input_template.jsonc` and adjust the parameters. 
3. Update the execution target in `main.py`

### Expected output & Analysis

Runtime Dashboard: During execution, the program will continuously print updated information in your terminal. This dashboard visualizes the active phase, live telemetry (chamber pressure, O/F ratio, thrust), an ASCII schematic of the tank and chamber regression, and a rolling event log.

Data Export:
Upon completion, the solver outputs a highly detailed .json file containing all initial conditions, phase-by-phase performance metrics, warnings, and time-series arrays for every state variable. These are automatically saved to user_data/simulation_results/.

Plotting Tools:
To visualize the results, utilize the provided analysis scripts. For example, run plotter.py located in src/backend/unsteady/analysis/ to generate matplotlib graphs (e.g., Thrust vs. Time) directly from the exported JSON files.


