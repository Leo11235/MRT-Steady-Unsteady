# McGill Rocket Team Steady-Unsteady-Flight-Model

### Steady-State and Unsteady Models for Nitrous Oxide/Paraffin Wax Hybrid Rocket Engine

This repository contains the computational framework developed by the McGill Rocket Team (MRT) to model, simulate, and optimize the performance of a self-pressurizing hybrid rocket engine using liquid nitrous oxide (N₂O) as oxidizer and paraffin wax as fuel. The tool supports both steady-state and transient (unsteady) simulations, enabling parametric design studies, flight trajectory prediction, and validation against experimental hot-fire test data.

## 🚀 Quick Start Guide

Follow these steps to get the code running on your own computer.

### 1. Prerequisites

*   **Python 3.13+**
*   **Git**

**Check your Python version:**
```bash
# Windows
python --version

# Mac/Linux
python3 --version
```

### 2. Clone this repository
```bash
git clone https://github.com/Leo11235/Steady-Unsteady-Flight-Model
cd Steady-Unsteady-Flight-Model
```

### 3. Set up your environment
Windows
```bash
# Create virtual environment
python -m venv venv

# Activate it
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

Mac/Linux
```bash
# Create virtual environment
python3 -m venv venv

# Activate it  
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Verify your setup
Run the verification test to make sure everything works:
```bash
# Windows
python backend/steady_venv_testing.py

# Mac/Linux  
python3 backend/steady_venv_testing.py
```
You should see simulation loops running with apogee calculations, ending with:
```bash
LOOP 9 - FINAL APOGEE: 13715.2 meters (0.81256 meters off from target)
```
If you see this, your setup is complete and working!

## Development workflow

Always start by activating your environment:
```bash
# Windows
venv\Scripts\activate

# Mac/Linux  
source venv/bin/activate
```
Run the simulations:
```bash
# Windows
python backend/steady_main.py
python backend/unsteady_main.py

# Mac/Linux  
python3 backend/steady_main.py
python3 backend/unsteady_main.py
```
