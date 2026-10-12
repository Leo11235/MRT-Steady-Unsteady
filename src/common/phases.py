"""
Phase vocabulary for the unsteady simulator
Used by plotting and UI
"""

from __future__ import annotations


PHASE_ORDER = ["phase_1", "phase_2", "phase_3", "phase_4a", "phase_4c", "phase_5", "phase_6", "phase_7",]

PHASE_COLORS = {
    "phase_1": "#e63946",
    "phase_2": "#f4a261",
    "phase_3": "#f3c623",
    "phase_4a": "#9d4edd",
    "phase_4c": "#5a189a",
    "phase_5": "#2a9d8f",
    "phase_6": "#118ab2",
    "phase_7": "#073b4c",
}

# colon-separated (saves space in the per-phase table)
PHASE_LABELS = {
    "phase_1": "1: Ignition",
    "phase_2": "2: Liquid blowdown",
    "phase_3": "3: Gaseous blowdown",
    "phase_4a": "4a: Vapor purge",
    "phase_4c": "4c: Dry blowdown",
    "phase_5": "5: Coast",
    "phase_6": "6: Drogue descent",
    "phase_7": "7: Main descent",
}

BURN_PHASES = {"phase_1", "phase_2", "phase_3", "phase_4a", "phase_4c"}
DESCENT_PHASES = {"phase_5", "phase_6", "phase_7"}

