"""Memoised wrappers around results_units so the results pages stop
walking the explicit-table + suffix-table on every single kv row.

Keys are strings; results are pure functions of the key + the current
unit system.  Small memory footprint, big win on results panels that
render hundreds of rows.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from src.ui.app.results_units import (
    get_field_info as _get_field_info,
    unit_for_system as _unit_for_system,
    format_unit_label as _format_unit_label,
)


@lru_cache(maxsize=4096)
def get_field_info(key: str) -> tuple[str, Optional[str], str]:
    """(pretty_name, kind, si_unit).  See results_units.get_field_info."""
    return _get_field_info(key)


@lru_cache(maxsize=4096)
def unit_for_system(field_name: str, kind: Optional[str], system: str) -> str:
    return _unit_for_system(field_name, kind, system)


@lru_cache(maxsize=256)
def format_unit_label(unit: str) -> str:
    return _format_unit_label(unit)
