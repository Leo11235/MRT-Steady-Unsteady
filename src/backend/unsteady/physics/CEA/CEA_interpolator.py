"""
Bicubic interpolator for the CEA lookup table in src/backend/unsteady/static_data
Uses use a Bivariate Bicubic Spline via SciPy's RectBivariateSpline to quickly access CEA values while avoiding step function derivatives
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import NamedTuple
import numpy as np
from scipy.interpolate import RectBivariateSpline

_STATIC = Path(__file__).resolve().parents[2] / "static_data"
_CEA_FILE = _STATIC / "CEA_table.json"


class ChamberProperties(NamedTuple):
    """
    combustion products at one operating point, and how they vary
    """
    # do not change this order
    T_c: float # chamber temperature, K
    W_c: float # mean molar mass, kg/mol
    gamma: float # ratio of specific heats
    cstar: float # characteristic velocity, m/s
    dT_dOF: float # K per unit O/F
    dT_dp: float # K per Pa
    dW_dOF: float # (kg/mol) per unit O/F
    dW_dp: float # (kg/mol) per Pa

# load CEA table
def _load_table() -> dict:
    if not _CEA_FILE.exists():
        raise FileNotFoundError(f"CEA table not found at {_CEA_FILE}")

    with open(_CEA_FILE, "r", encoding="utf-8") as f:
        table = json.load(f)

    if "OF_axis" not in table:
        raise ValueError(f"{_CEA_FILE} is likely in the old flat-records format")

    of_axis = np.asarray(table["OF_axis"], dtype=float)
    p_axis = np.asarray(table["p_C_axis"], dtype=float)

    splines = {
        name: RectBivariateSpline(of_axis, p_axis, np.asarray(table[name], dtype=float), kx=3, ky=3) for name in ("T_C", "W_C", "gamma", "cstar")
    }
    splines["bounds"] = {
        "OF_min": float(of_axis.min()), "OF_max": float(of_axis.max()),
        "p_min": float(p_axis.min()), "p_max": float(p_axis.max()),
    }
    splines["meta"] = table.get("meta", {})
    return splines


_SPLINES = _load_table()
_BOUNDS = _SPLINES["bounds"]


# envelope log
# module level because the RHS is called from deep inside scipy with no route to pass state back out
_EXCURSIONS: dict[str, dict] = {}

def reset_envelope_log() -> None:
    """
    Cleans up CEA env between sims
    """
    _EXCURSIONS.clear()


def envelope_excursions() -> dict:
    """
    What this run pushed past the table edge, biggest overshoot first
    Keyed "<axis> <direction>"
    Empty dict means every query landed inside the table
    """
    return {k: dict(v) for k, v in sorted(_EXCURSIONS.items(), key=lambda kv: -kv[1]["overshoot"])}


def _record(axis: str, requested: float, clamped: float, limit: str) -> None:
    key = f"{axis} {limit}"
    entry = _EXCURSIONS.get(key)
    overshoot = abs(requested - clamped)

    if entry is None:
        _EXCURSIONS[key] = {
            "axis": axis, "limit": limit, "table_edge": clamped,
            "worst_requested": requested, "overshoot": overshoot, "count": 1,
        }
        return

    entry["count"] += 1
    if overshoot > entry["overshoot"]:
        entry["worst_requested"] = requested
        entry["overshoot"] = overshoot







def CEA_interpolation_lookup(OF: float, p_C: float) -> ChamberProperties:
    """
    Chamber properties and their local derivatives

    OF: mixture ratio
    p_C: chamber pressure in Pa

    Queries outside the table are clamped to the nearest edge and recorded
    """
    
    OF = float(OF)
    p_C = float(p_C)

    OF_q = min(max(OF, _BOUNDS["OF_min"]), _BOUNDS["OF_max"])
    p_q = min(max(p_C, _BOUNDS["p_min"]), _BOUNDS["p_max"])

    if OF_q != OF:
        _record("O/F", OF, OF_q, "below table minimum" if OF < OF_q else "above table maximum")
    if p_q != p_C:
        _record("chamber pressure", p_C, p_q, "below table minimum" if p_C < p_q else "above table maximum")

    T_c = _SPLINES["T_C"](OF_q, p_q)[0][0]
    W_c = _SPLINES["W_C"](OF_q, p_q)[0][0]
    gamma = _SPLINES["gamma"](OF_q, p_q)[0][0]
    cstar = _SPLINES["cstar"](OF_q, p_q)[0][0]

    # derives a fitted surface
    # dx=1 differentiates with respect to the first axis (O/F), dy=1 with respect to the second (p_C)
    # at a clamped point these are the edge derivatives
    dT_dOF = _SPLINES["T_C"](OF_q, p_q, dx=1, dy=0)[0][0]
    dT_dp = _SPLINES["T_C"](OF_q, p_q, dx=0, dy=1)[0][0]
    dW_dOF = _SPLINES["W_C"](OF_q, p_q, dx=1, dy=0)[0][0]
    dW_dp = _SPLINES["W_C"](OF_q, p_q, dx=0, dy=1)[0][0]

    return ChamberProperties(
        float(T_c), float(W_c), float(gamma), float(cstar),
        float(dT_dOF), float(dT_dp), float(dW_dOF), float(dW_dp))


def get_CEA_table_bounds() -> tuple[float, float, float, float]:
    """
    (OF_min, OF_max, p_C_min, p_C_max), pressures in Pa.

    Used by warnings.py to bound its input checks against the same table the physics reads
    """
    return (_BOUNDS["OF_min"], _BOUNDS["OF_max"], _BOUNDS["p_min"], _BOUNDS["p_max"])


def table_info() -> dict:
    """
    Returns identifying table info. 
    """
    return {
        **dict(_SPLINES["meta"]),
        "OF_min": _BOUNDS["OF_min"], "OF_max": _BOUNDS["OF_max"],
        "p_C_min": _BOUNDS["p_min"], "p_C_max": _BOUNDS["p_max"],
        "path": str(_CEA_FILE),
    }
