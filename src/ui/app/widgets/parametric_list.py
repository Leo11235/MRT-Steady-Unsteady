"""
ParametricList — the swept-variable editor on the steady page.

    Fuel external diameter   [ m v ]                              x
        Low end    [                                            ]
        High end   [                                            ]
        Step size  [                                            ]

    Rocket external diameter [ m v ]                              x
        Low end    [                                            ]
        ...

    [ +  Add parameter  v ]

One card per swept variable: a bold name, one unit for the whole card, a remove
button on the right, and the three bounds stacked beneath. A sweep in mixed
units would be meaningless, so the unit belongs to the card rather than each
bound, and changing it converts all three together.

The Add-parameter picker sits immediately below the last card and moves with
them, so it's always the next thing after the list rather than stranded at the
bottom of the scroll region.

Rows emit the same [value, unit] pairs everything else does:

    {"chamber_pressure": {"low_end": [400, "psi"],
                          "high_end": [600, "psi"],
                          "step_size": [100, "psi"]}}
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from src.common import variable_conversions as vc
from src.ui.app import field_registry as registry
from src.ui.app import theme

_ADD_PLACEHOLDER = "+  Add parameter"
_NONE_LEFT = "(every variable is already swept)"

_BOUND_LABELS = (("low_end", "Low end"),
                 ("high_end", "High end"),
                 ("step_size", "Step size"))

# The variables a sweep can drive. Everything else on the steady form is either
# derived by the solver, a propellant species, or a locked constant, none of
# which make sense to sweep.
SWEEPABLE: tuple[str, ...] = (
    "oxidizer_mass_flow_rate",
    "chamber_pressure",
    "fuel_length",
    "fuel_external_diameter",
    "rocket_external_diameter",
    "drag_coefficient",
    "dry_mass",
)


def _format_number(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "" if value is None else str(value)
    if number == int(number) and abs(number) < 1e15:
        return str(int(number))
    return f"{number:.6g}"


class _Row(ctk.CTkFrame):
    """One swept variable: a header with its unit, then three bounds."""

    _BOUND_LABEL_W = 110

    def __init__(self, master, key: str, *, system: str = "SI",
                 on_remove: Callable[["_Row"], None],
                 on_change: Optional[Callable[[], None]] = None) -> None:
        super().__init__(master, fg_color="transparent")
        self.key = key
        self.spec = registry.get(key)
        self._on_change = on_change

        # ---- header: name, unit, remove -------------------------------
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(theme.PAD_S, theme.PAD_XS))

        ctk.CTkLabel(header, text=self.spec.label, anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold")).pack(
            side="left", padx=(0, theme.PAD_S))

        # One unit for the whole card. Converting from the cached SI values
        # rather than the rounded display keeps repeated switches lossless,
        # same as LabeledField.
        self._unit_var = ctk.StringVar(value=self.spec.unit_for(system))
        self._previous_unit = self._unit_var.get()
        options = self.spec.unit_options
        if len(options) >= 2:
            ctk.CTkOptionMenu(header, values=options, variable=self._unit_var,
                              command=self._on_unit_changed,
                              width=80, dynamic_resizing=False).pack(side="left")
        elif options:
            ctk.CTkLabel(header, text=options[0], width=80,
                         text_color=theme.TEXT_MUTED).pack(side="left")

        ctk.CTkButton(header, text="✕", width=30, height=28,
                      fg_color="transparent", text_color=theme.ERROR,
                      hover_color=theme.CARD_HOVER,
                      command=lambda: on_remove(self)).pack(side="right")

        # ---- the three bounds -----------------------------------------
        self.bound_vars: dict[str, ctk.StringVar] = {}
        for bound, label in _BOUND_LABELS:
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", pady=theme.PAD_XS)
            ctk.CTkLabel(row, text=label, width=self._BOUND_LABEL_W,
                         anchor="w").pack(side="left", padx=(theme.PAD_M, theme.PAD_S))
            var = ctk.StringVar()
            if on_change is not None:
                var.trace_add("write", lambda *_: on_change())
            self.bound_vars[bound] = var
            ctk.CTkEntry(row, textvariable=var).pack(
                side="left", fill="x", expand=True)

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
        unit = self.unit
        out = {}
        for bound, _label in _BOUND_LABELS:
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
        for bound, _label in _BOUND_LABELS:
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
    """The whole editor: cards plus the add-a-parameter picker."""

    def __init__(self, master, *, system: str = "SI",
                 sweepable: Optional[list[str]] = None,
                 on_change: Optional[Callable[[], None]] = None) -> None:
        super().__init__(master, fg_color="transparent")
        self._on_change = on_change
        self._system = system
        self._rows: list[_Row] = []
        self._sweepable = list(sweepable if sweepable is not None else SWEEPABLE)

        # Rows are packed directly into this frame rather than a container.
        # An empty CTkFrame keeps its default 200px height, which is what used
        # to strand the picker at the bottom of the scroll region.
        self._picker_var = ctk.StringVar(value=_ADD_PLACEHOLDER)
        self._picker = ctk.CTkOptionMenu(
            self, values=[_ADD_PLACEHOLDER], variable=self._picker_var,
            command=self._on_picked, width=260, dynamic_resizing=False,
            anchor="w",
        )
        self._repack_picker()
        self._refresh_picker()

    # ------------------------------------------------------------------

    def _repack_picker(self) -> None:
        """Keep the picker as the last child, directly under the cards."""
        try:
            self._picker.pack_forget()
        except Exception:                       # noqa: BLE001
            pass
        self._picker.pack(anchor="w", pady=(theme.PAD_S, 0))

    def _label_to_key(self, label: str) -> Optional[str]:
        for key in self._sweepable:
            if registry.get(key).label == label:
                return key
        return None

    def _refresh_picker(self) -> None:
        """Offer only what isn't already swept."""
        used = self.used_vars()
        available = [registry.get(k).label for k in self._sweepable if k not in used]
        self._picker.configure(
            values=[_ADD_PLACEHOLDER] + available if available else [_NONE_LEFT])
        self._picker_var.set(_ADD_PLACEHOLDER if available else _NONE_LEFT)

    def _on_picked(self, label: str) -> None:
        key = self._label_to_key(label)
        if key is not None:
            self.add_row(key)
        self._picker_var.set(_ADD_PLACEHOLDER)

    def _remove_row(self, row: _Row) -> None:
        self._rows.remove(row)
        row.destroy()
        self._repack_picker()
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
        row = _Row(self, key, system=self._system,
                   on_remove=self._remove_row, on_change=self._fire_change)
        row.pack(fill="x")
        self._rows.append(row)
        if spec:
            row.from_dict(spec)
        # Cards are packed after the picker was, so put it back at the end.
        self._repack_picker()
        self._refresh_picker()
        self._fire_change()
        return row

    def clear(self) -> None:
        for row in list(self._rows):
            row.destroy()
        self._rows.clear()
        self._repack_picker()
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
