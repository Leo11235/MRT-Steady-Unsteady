"""
Pretty forms of unit strings, for anything a person reads.

The canonical spellings are ASCII so they can live safely in JSON, filenames and
dict keys: m^2, kg/m^3, N*s.  Those are correct and unambiguous, and they look
like code.  This module is the one place that turns them into m2, kg/m3, N.s for
display.

Shared by the results page, the PDF report and the figures so the three cannot
drift.  It used to live inside unsteady_PDF_report, which is why the PDF showed
superscripts and the app did not.

Unknown units pass through unchanged, which is the right failure: a unit nobody
has prettified yet should still be readable.
"""

from __future__ import annotations

from typing import Optional


UNIT_LABELS: dict[str, str] = {
    # exponents
    "m^2": "m²", "mm^2": "mm²", "cm^2": "cm²", "in^2": "in²", "ft^2": "ft²",
    "m^3": "m³", "mm^3": "mm³", "cm^3": "cm³", "in^3": "in³", "ft^3": "ft³",
    "m/s^2": "m/s²", "ft/s^2": "ft/s²",
    "kg/m^3": "kg/m³", "g/cm^3": "g/cm³", "lb/ft^3": "lb/ft³", "lb/in^3": "lb/in³",
    # products
    "N*s": "N·s", "lbf*s": "lbf·s",
    # angles and temperatures
    "deg": "°", "C": "°C", "F": "°F",
    # dimensionless shows nothing rather than a full stop
    ".": "",
}


def pretty_unit(unit: Optional[str]) -> str:
    """The readable form of a unit string.  None and unknowns pass through."""
    if unit is None:
        return ""
    return UNIT_LABELS.get(unit, unit)
