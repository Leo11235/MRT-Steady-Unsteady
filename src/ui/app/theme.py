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
MRT_RED_HOVER  = ("#7a131a", "#a01a26")

# Slate-blue accent — used for affirmative buttons that aren't
# "run a simulation" (which is green).  Pairs with the brand red
# without competing.  White text stays highly readable on it.
ACCENT_SLATE       = ("#3d5a80", "#3d5a80")
ACCENT_SLATE_HOVER = ("#2f4666", "#4a6a94")


# -----------------------------------------------------------------------------
# Semantic colour tokens
#
# Two-tuples are (light-theme colour, dark-theme colour) — CustomTkinter picks
# the right one automatically.  Use these instead of hard-coding hex strings
# so success/warning/error styling stays consistent across pages.
# -----------------------------------------------------------------------------
SUCCESS         = ("#2a9d8f", "#5eead4")
SUCCESS_HOVER   = ("#21867a", "#21867a")
WARNING         = ("#f4a261", "#f4a261")
WARNING_STRONG  = ("#e76f51", "#ff9e7a")
ERROR           = ("#b00020", "#ff6b6b")

# Neutral / faded text
TEXT_MUTED      = ("gray35", "gray65")
TEXT_FAINT      = ("gray40", "gray60")
TEXT_LOCKED     = ("gray55", "gray55")

# Panel / card backgrounds
CARD_BG         = ("gray90", "gray18")
CARD_HOVER      = ("gray85", "gray25")
DIVIDER         = ("gray75", "gray30")

# Terminal (loading screen)
TERMINAL_BG     = ("#101418", "#101418")
TERMINAL_FG     = ("#c5e1a5", "#c5e1a5")
