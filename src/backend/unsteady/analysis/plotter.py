"""
plotter.py
Utility script to visualize time-series data from unsteady simulation JSON exports.
"""

import json
import math
import matplotlib.pyplot as plt
from pathlib import Path

def plot_vs_time(json_filename: str, json_filepath: str | Path, y_variable: str):
    """
    Reads a simulation JSON file and plots a specified variable against time.
    
    Args:
        json_filename (str): The name of the JSON file (e.g., '2026_05_24_19_04_26.json')
        json_filepath (str | Path): The directory containing the JSON file.
        y_variable (str): The exact key name of the variable to plot (e.g., 'F_thrust', 'p_C')
    """
    # 1. Resolve path and load JSON
    full_path = Path(json_filepath) / json_filename
    
    if not full_path.exists():
        print(f"Error: File not found at {full_path}")
        return
        
    print(f"Loading data from {full_path}...")
    with open(full_path, 'r', encoding='utf-8') as f:
        sim_results = json.load(f)
        
    # 2. Extract data block
    data = sim_results.get("data", {})
    
    if "time" not in data:
        print("Error: 'time' array not found in the JSON data.")
        return
        
    if y_variable not in data:
        print(f"Error: Variable '{y_variable}' not found in the JSON data.")
        print(f"Available variables: {', '.join(data.keys())}")
        return
        
    # 3. Process arrays
    t_data_raw = data["time"]
    y_data_raw = data[y_variable]
    
    # Convert JSON nulls (Python None) back to float('nan') 
    # This prevents Matplotlib from crashing and correctly plots breaks in the data
    t_data = [float('nan') if val is None else val for val in t_data_raw]
    y_data = [float('nan') if val is None else val for val in y_data_raw]
    
    # Optional: Automatically scale pressure to Bar for readability
    y_label = y_variable
    if y_variable in ["p_C", "p_T", "p_amb", "delta_p"]:
        y_data = [val / 1e5 if not math.isnan(val) else val for val in y_data]
        y_label = f"{y_variable} [Bar]"
    
    # 4. Plot
    plt.figure(figsize=(10, 6))
    plt.plot(t_data, y_data, label=y_variable, color='#1f77b4', linewidth=2)
    
    # Formatting
    plt.xlabel("Time [s]", fontsize=12)
    plt.ylabel(y_label, fontsize=12)
    plt.title(f"Simulation Result: {y_variable} vs Time", fontsize=14, pad=15)
    plt.grid(True, which='both', linestyle='--', alpha=0.7)
    plt.legend(loc="best")
    plt.tight_layout()
    
    plt.show()

# ==========================================
# Example Usage Block
# ==========================================
if __name__ == "__main__":
    # Point to the simulation_results folder
    project_root = Path(__file__).resolve().parents[4]
    results_dir = project_root / "user_data" / "simulation_results"
    
    # Replace with your actual JSON file name
    target_file = "2026_05_25_16_23_58.json" 
    
    # Test a few plots
    plot_vs_time(target_file, results_dir, "F_thrust")
    plot_vs_time(target_file, results_dir, "p_C")
    plot_vs_time(target_file, results_dir, "OF")