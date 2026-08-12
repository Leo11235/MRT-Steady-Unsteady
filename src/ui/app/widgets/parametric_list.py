"""
ParametricList — the swept-variable editor on the steady page.

    [ Chamber pressure ] [ low ] [ high ] [ step ]  [ psi v ]  [ x ]
    [ + Add variable v ]

One row per swept variable, each with three bounds and a single unit that
applies to all three. A sweep in mixed units would be meaningless, so the unit
lives on the row rather than the bound, and changing it converts all three
numbers together.

Rows emit the same [value, unit] pairs everything else does:

    {"chamber_pressure": {"low_end": [400, "psi"],
                          "high_end": [600, "psi"],
                          "step_size": [100, "psi"]}}

Only variables the field registry knows and that are numeric can be swept, and
each one can only be added once — the picker drops what's already in use.
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from src.common import variable_conversions as vc
from src.ui.app import field_registry as registry
from src.ui.app import theme

_ADD_PLACEHOLDER = "+  Add variable"
_NONE_LEFT = "(every variable is already swept)"

_BOUND_KEYS = ("low_end", "high_end", "step_size")


def _format_number(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "" if value is None else str(value)
    if number == int(number) and abs(number) < 1e15:
        return str(int(number))
    return f"{number:.6g}"


class _Row(ctk.CTkFrame):
    """One swept variable: three bounds sharing a unit."""

    def __init__(self, master, key: str, *,
                 on_remove: Callable[["_Row"], None],
                 on_change: Optional[Callable[[], None]] = None) -> None:
        super().__init__(master, fg_color="transparent")
        self.key = key
        self.spec = registry.get(key)
        self._on_change = on_change

        ctk.CTkLabel(self, text=self.spec.label, width=200, anchor="w").pack(
            side="left", padx=(0, theme.PAD_S))

        self.bound_vars: dict[str, ctk.StringVar] = {}
        for bound, placeholder in zip(_BOUND_KEYS, ("low", "high", "step")):
            var = ctk.StringVar()
            if on_change is not None:
                var.trace_add("write", lambda *_: on_change())
            self.bound_vars[bound] = var
            ctk.CTkEntry(self, textvariable=var, width=90,
                         placeholder_text=placeholder).pack(
                side="left", padx=(0, theme.PAD_XS))

        # One unit for the whole row. Same reasoning as LabeledField: convert
        # from the exact SI values rather than the rounded display, so
        # switching units repeatedly doesn't drift.
        self._unit_var = ctk.StringVar(value=self.spec.unit)
        self._previous_unit = self.spec.unit
        options = self.spec.unit_options
        if len(options) >= 2:
            ctk.CTkOptionMenu(self, values=options, variable=self._unit_var,
                              command=self._on_unit_changed,
                              width=78, dynamic_resizing=False).pack(
                side="left", padx=(theme.PAD_XS, 0))
        else:
            ctk.CTkLabel(self, text=options[0] if options else "",
                         width=78, text_color=theme.TEXT_MUTED).pack(
                side="left", padx=(theme.PAD_XS, 0))

        ctk.CTkButton(self, text="✕", width=30, height=28,
                      fg_color="transparent", text_color=theme.TEXT_MUTED,
                      hover_color=theme.CARD_HOVER,
                      command=lambda: on_remove(self)).pack(
            side="left", padx=(theme.PAD_S, 0))

    # ------------------------------------------------------------------

    @property
    def unit(self) -> str:
        return self._unit_var.get()

    def _on_unit_changed(self, new_unit: str) -> None:
        """Convert all three bounds into the new unit at once."""
        old_unit = self._previous_unit
        self._previous_unit = new_unit
        for var in self.bound_vars.values():
            raw = var.get().strip()
            if not raw:
                continue
            try:
                var.set(_format_number(vc.convert(float(raw), old_unit, new_unit)))
            except (ValueError, KeyError):
                pass        # leave half-typed text alone

    def to_dict(self) -> dict:
        """The three bounds as [value, unit] pairs."""
        unit = self.unit
        out = {}
        for bound in _BOUND_KEYS:
            raw = self.bound_vars[bound].get().strip()
            if raw == "":
                out[bound] = [None, unit]
                continue
            try:
                out[bound] = [float(raw), unit]
            except ValueError:
                out[bound] = [raw, unit]        # let the validator complain
        return out

    def from_dict(self, spec: dict) -> None:
        """Load three bounds, adopting whatever unit they were saved in."""
        unit = None
        for bound in _BOUND_KEYS:
            pair = (spec or {}).get(bound)
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                value, pair_unit = pair
                if unit is None and pair_unit and vc.is_known_unit(pair_unit):
                    unit = vc._canonical(pair_unit)
            else:
                value = pair
            self.bound_vars[bound].set("" if value is None else _format_number(value))

        if unit and unit in self.spec.unit_options:
            self._unit_var.set(unit)
            self._previous_unit = unit


class ParametricList(ctk.CTkFrame):
    """The whole editor: rows plus the add-a-variable picker."""

    def __init__(self, master, *,
                 sweepable: Optional[list[str]] = None,
                 on_change: Optional[Callable[[], None]] = None) -> None:
        super().__init__(master, fg_color="transparent")
        self._on_change = on_change
        self._rows: list[_Row] = []

        # Anything numeric on the steady form can be swept. The hotfire
        # alternates are excluded: the solver derives them per point, so
        # sweeping one would fight the convergence loop.
        self._sweepable = sweepable if sweepable is not None else [
            key for key in registry.STEADY_KEYS
            if registry.get(key).is_numeric
            and key not in ("fuel_mass", "initial_internal_fuel_diameter")
        ]

        self._rows_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._rows_frame.pack(fill="x")

        self._picker_var = ctk.StringVar(value=_ADD_PLACEHOLDER)
        self._picker = ctk.CTkOptionMenu(
            self, values=[_ADD_PLACEHOLDER], variable=self._picker_var,
            command=self._on_picked, width=240, dynamic_resizing=False,
        )
        self._picker.pack(anchor="w", pady=(theme.PAD_S, 0))
        self._refresh_picker()

    # ------------------------------------------------------------------

    def _label_to_key(self, label: str) -> Optional[str]:
        for key in self._sweepable:
            if registry.get(key).label == label:
                return key
        return None

    def _refresh_picker(self) -> None:
        """Offer only what isn't already swept."""
        used = self.used_vars()
        available = [registry.get(k).label for k in self._sweepable if k not in used]
        self._picker.configure(values=[_ADD_PLACEHOLDER] + available
                               if available else [_NONE_LEFT])
        self._picker_var.set(_ADD_PLACEHOLDER if available else _NONE_LEFT)

    def _on_picked(self, label: str) -> None:
        key = self._label_to_key(label)
        if key is not None:
            self.add_row(key)
        self._picker_var.set(_ADD_PLACEHOLDER)

    def _remove_row(self, row: _Row) -> None:
        self._rows.remove(row)
        row.destroy()
        self._refresh_picker()
        self._fire_change()

    def _fire_change(self) -> None:
        if self._on_change is not None:
            self._on_change()

    # ------------------------------------------------------------------

    def add_row(self, key: str, spec: Optional[dict] = None) -> Optional[_Row]:
        """Add a swept variable. Ignores keys already present or unknown."""
        if key in self.used_vars() or not registry.has(key):
            return None
        row = _Row(self._rows_frame, key, on_remove=self._remove_row,
                   on_change=self._fire_change)
        row.pack(fill="x", pady=theme.PAD_XS)
        self._rows.append(row)
        if spec:
            row.from_dict(spec)
        self._refresh_picker()
        self._fire_change()
        return row

    def clear(self) -> None:
        for row in list(self._rows):
            row.destroy()
        self._rows.clear()
        self._refresh_picker()

    def used_vars(self) -> list[str]:
        return [row.key for row in self._rows]

    def to_dict(self) -> dict:
        return {row.key: row.to_dict() for row in self._rows}

    def from_dict(self, data: dict) -> None:
        self.clear()
        for key, spec in (data or {}).items():
            self.add_row(key, spec)
        self._fire_change()
