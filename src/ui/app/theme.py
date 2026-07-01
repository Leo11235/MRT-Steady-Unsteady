"""
Centralized design tokens for the simulator UI.

Every page imports from here so we can adjust the look in one place.
"""

from __future__ import annotations

# -----------------------------------------------------------------------------
# Window
# -----------------------------------------------------------------------------
APP_TITLE   = "MRT Steady-Unsteady Simulator"
WINDOW_W    = 1100
WINDOW_H    = 720
MIN_WINDOW  = (820, 580)

# -----------------------------------------------------------------------------
# CustomTkinter global appearance
# -----------------------------------------------------------------------------
APPEARANCE   = "system"   # "light", "dark", or "system"
COLOR_THEME  = "blue"     # built-in CTk themes: "blue", "dark-blue", "green"

# -----------------------------------------------------------------------------
# Spacing (in pixels)
# -----------------------------------------------------------------------------
PAD_XS = 4
PAD_S  = 8
PAD_M  = 14
PAD_L  = 22
PAD_XL = 36

# -----------------------------------------------------------------------------
# Type sizes
#
# Tk font families fall back gracefully across OSes; specifying a tuple lets
# Tk pick a system default when the named family is absent.
# -----------------------------------------------------------------------------
SIZE_HERO   = 32
SIZE_TITLE  = 24
SIZE_H1     = 20
SIZE_H2     = 16
SIZE_BODY   = 13
SIZE_SMALL  = 11

# -----------------------------------------------------------------------------
# Top-bar
# -----------------------------------------------------------------------------
TOP_BAR_HEIGHT = 52

# -----------------------------------------------------------------------------
# Brand colors
#
# MRT_RED is sampled directly from the MRT letters in the logo PNG; the dark
# tone is a slightly lighter version so the text stays readable on the dark
# CTk background.  CustomTkinter accepts tuples of (light, dark).
# -----------------------------------------------------------------------------
MRT_RED        = "#981820"
MRT_RED_BRIGHT = "#d4232f"
MRT_RED_THEMED = (MRT_RED, MRT_RED_BRIGHT)
