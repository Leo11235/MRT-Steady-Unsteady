"""KVRow — one two-column results-panel row that can update its
unit system WITHOUT being destroyed and rebuilt.

Layout:
    [ Pretty name (unit) .................. ] [ value ............ ]

The `unit` part of the name column DOES change when the user switches
SI/IMP/MRT, so update_system() re-composes the name label too.
"""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app import display as display_mod
from src.ui.app.services.pretty_names import (
    get_field_info,
    unit_for_system,
    format_unit_label,
)


# ---------------------------------------------------------------------------
# Scalar formatting (matches results_utils._format_scalar so on-screen
# values and exports stay in lock-step).
# ---------------------------------------------------------------------------

def _format_scalar(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if abs(v) < 1e-15:
            return "0"
        if abs(v - round(v)) < 1e-9 and abs(v) < 1e15:
            return f"{int(round(v))}"
        if abs(v) < 1e-3:
            return f"{v:.4g}"
        s = f"{v:.4f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s
    if isinstance(v, int):
        return str(v)
    if isinstance(v, dict):
        return f"({len(v)} keys — nested)"
    if isinstance(v, list):
        return f"[{len(v)} items]"
    return str(v)


def _convert(value: Any, key: str, system: str):
    """Return (display_string, unit_label) for a value in the given
    system.  Non-numeric / dimensionless values get unit_label='.'."""
    pretty, kind, si_unit = get_field_info(key)
    if kind is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return _format_scalar(value), "."
    target = unit_for_system(key, kind, system)
    try:
        converted = display_mod.convert(float(value), si_unit, target, kind)
    except Exception:
        converted = value
    return _format_scalar(converted), format_unit_label(target)


def _compose_name(key: str, system: str) -> str:
    """Return `Pretty name (unit)` — the unit part is omitted when the
    field is dimensionless.  Called by both __init__ and update_system."""
    pretty, kind, si_unit = get_field_info(key)
    if kind is None:
        return pretty
    target = unit_for_system(key, kind, system)
    return f"{pretty} ({format_unit_label(target)})"


# ---------------------------------------------------------------------------
# The widget
# ---------------------------------------------------------------------------

class KVRow(ctk.CTkFrame):
    """A two-column row: [ name (unit) | value ].

    Remembers its raw key + raw value so a later `update_system(sys)`
    call can recompute both labels' text without rebuilding widgets.
    """

    _NAME_WIDTH = 340

    def __init__(self, master, key: str, value: Any, system: str,
                 *, name_width: int | None = None,
                 unit_width: int | None = None) -> None:
        # `unit_width` retained for backwards compatibility — ignored now
        # that the unit is merged into the name column.
        super().__init__(master, fg_color="transparent")
        self._raw_key   = key
        self._raw_value = value

        name_w = name_width if name_width is not None else self._NAME_WIDTH

        display_val, _unit_label = _convert(value, key, system)

        # Two labels created once.  update_system() re-configure()s them.
        self._name_label = ctk.CTkLabel(
            self, text=_compose_name(key, system),
            width=name_w, anchor="w",
        )
        self._name_label.pack(side="left", padx=(0, theme.PAD_S))

        self._value_label = ctk.CTkLabel(
            self, text=display_val, anchor="w",
            wraplength=520, justify="left",
        )
        self._value_label.pack(side="left", fill="x", expand=True,
                               padx=(0, theme.PAD_L))

    def update_system(self, system: str) -> None:
        """Recompute the name (with new unit label) and the value string
        for `system`.  Two `.configure(text=…)` calls, no rebuild."""
        display_val, _unit_label = _convert(self._raw_value, self._raw_key, system)
        self._name_label.configure(text=_compose_name(self._raw_key, system))
        self._value_label.configure(text=display_val)

    def matches(self, query: str) -> bool:
        """Case-insensitive substring match on the current name text
        (which includes the unit label), the raw key (so users can
        search JSON field names too), and the current value string."""
        if not query:
            return True
        q = query.lower().strip()
        if not q:
            return True
        try:
            hay = (
                self._name_label.cget("text") + "\n"
                + self._raw_key + "\n"
                + str(self._value_label.cget("text"))
            ).lower()
            return q in hay
        except Exception:
            return True
