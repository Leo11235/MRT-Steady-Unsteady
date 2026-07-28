"""
LabeledField — one row of a form.

Layout (units omitted if none configured):
    [ label *           ] [ entry .................. ] [ unit-dropdown v ]

Features:
  - Optional list of selectable units; the value the user types is in the
    currently-selected unit.  to_internal() converts to the field's internal
    unit (e.g. user types 76.2 cm, internal stores 0.762 m).  Switching the
    unit dropdown auto-converts the typed value (or leaves it alone if the
    field is empty / non-numeric).
  - Required-field asterisk + red border on invalid.
  - set_locked(bool) toggles read-only mode with a faded look.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

import customtkinter as ctk

from src.ui.app import theme, display as display_mod


_BORDER_INVALID = "#e63946"
_LOCKED_TEXT_COLOR  = ("gray55", "gray55")
_NORMAL_TEXT_COLOR  = ("gray10", "gray90")


class LabeledField(ctk.CTkFrame):
    def __init__(
        self,
        master,
        *,
        label: str,
        # Units — pick ONE of the next two:
        kind: Optional[str] = None,        # e.g. "length", "pressure" (lookup in display.UNIT_KINDS)
        units: Optional[Sequence[str]] = None,  # explicit list (rare; overrides kind)
        unit_default: Optional[str] = None,     # which unit to start with; defaults to the first
        # Static behavior:
        placeholder: str = "",
        default: str = "",
        required: bool = False,
        numeric: bool = False,
        label_width: int = 220,
        on_change: Optional[Callable[[str], None]] = None,
        help_text: Optional[str] = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._numeric  = numeric
        self._required = required
        self._on_change = on_change
        self._locked = False
        self._help_text = help_text

        # ---- resolve unit list + internal unit -------------------------
        if units is not None:
            self._unit_options = list(units)
            self._internal_unit = self._unit_options[0]
        elif kind is not None:
            spec = display_mod.UNIT_KINDS.get(kind)
            if spec is None:
                self._unit_options, self._internal_unit = [], ""
            else:
                self._unit_options = list(spec["options"])
                self._internal_unit = spec["internal"]
        else:
            self._unit_options = []
            self._internal_unit = ""

        self._unit_var = ctk.StringVar(value=unit_default or
                                       (self._unit_options[0] if self._unit_options else ""))

        # ---- label -----------------------------------------------------
        # (Required fields used to append " *" but the marker was noisy;
        # required-ness is still tracked internally for validation.)
        label_text = label
        self._label = ctk.CTkLabel(self, text=label_text, anchor="w",
                                   width=label_width)
        self._label.pack(side="left", padx=(0, theme.PAD_S))

        # ---- entry -----------------------------------------------------
        self.var = ctk.StringVar(value=default)
        if on_change is not None:
            self.var.trace_add("write", lambda *_: on_change(self.var.get()))

        self._entry = ctk.CTkEntry(self, textvariable=self.var,
                                   placeholder_text=placeholder)
        self._entry.pack(side="left", fill="x", expand=True)

        # ---- tooltip (optional) ---------------------------------------
        # Attached to BOTH the label and the entry so the user gets the
        # help text no matter which half of the row they hover over.
        if help_text:
            try:
                from src.ui.app.widgets.tooltip import Tooltip
                Tooltip(self._label, help_text)
                Tooltip(self._entry, help_text)
            except Exception:
                # Tooltips are optional polish; never crash the form.
                pass

        # ---- units dropdown (only if there is more than one option) ----
        self._unit_menu = None
        if len(self._unit_options) >= 2:
            self._unit_menu = ctk.CTkOptionMenu(
                self,
                values=self._unit_options,
                variable=self._unit_var,
                command=self._on_unit_changed,
                width=80,
                dynamic_resizing=False,
            )
            self._unit_menu.pack(side="left", padx=(theme.PAD_S, 0))
            # remember last selected so on_change can compute the delta
            self._prev_unit = self._unit_var.get()
        elif len(self._unit_options) == 1:
            # Just show as a static label so the user knows the unit
            ctk.CTkLabel(self, text=self._unit_options[0], anchor="w",
                         text_color=("gray35", "gray65"),
                         width=80).pack(side="left", padx=(theme.PAD_S, 0))

    # ------------------------------------------------------------------
    # Value access (user-facing string + internal SI value)
    # ------------------------------------------------------------------

    def get(self) -> str:
        """The raw string the user has typed, untouched."""
        return self.var.get().strip()

    def set(self, value) -> None:
        """Set the entry's visible value (interpreted in the CURRENT unit)."""
        self.var.set("" if value is None else str(value))

    def get_internal(self):
        """
        Read the field as a number in the field's INTERNAL unit.
        Returns None for blank fields, or the raw string for invalid numeric
        input (validation logic handles the latter).
        """
        raw = self.get()
        if raw == "":
            return None
        if not self._numeric:
            return raw
        try:
            v = float(raw)
        except ValueError:
            return raw
        if self._internal_unit and self._unit_var.get() != self._internal_unit:
            v = display_mod.to_internal(v, self._unit_var.get(), self._internal_unit)
        return int(v) if (self._numeric and float(v).is_integer()) else v

    def set_from_internal(self, value) -> None:
        """
        Write a number that's already in the INTERNAL unit, converting into
        whatever unit the user currently has selected.
        """
        if value is None or value == "":
            self.var.set("")
            return
        try:
            v = float(value)
        except (TypeError, ValueError):
            self.var.set(str(value))
            return
        if self._internal_unit and self._unit_var.get() != self._internal_unit:
            v = display_mod.from_internal(v, self._internal_unit, self._unit_var.get())
        # Format reasonably: integers as integers, floats with up to 6 digits
        if v == int(v):
            self.var.set(str(int(v)))
        else:
            self.var.set(f"{v:.6g}")

    # ------------------------------------------------------------------
    # Unit-change handler
    # ------------------------------------------------------------------

    def _on_unit_changed(self, new_unit: str) -> None:
        """Auto-convert the typed value to the new unit, if possible."""
        old_unit = getattr(self, "_prev_unit", new_unit)
        self._prev_unit = new_unit
        raw = self.get()
        if raw == "" or not self._numeric:
            return
        try:
            v = float(raw)
        except ValueError:
            return  # leave invalid input alone
        try:
            converted = display_mod.convert(v, old_unit, new_unit,
                                            kind_for_internal(self._internal_unit))
        except Exception:
            return
        if converted == int(converted):
            self.var.set(str(int(converted)))
        else:
            self.var.set(f"{converted:.6g}")

    # ------------------------------------------------------------------
    # Validation / lock / visibility helpers
    # ------------------------------------------------------------------

    def is_blank(self) -> bool:
        return self.get() == ""

    def mark_invalid(self, invalid: bool = True) -> None:
        if invalid:
            self._entry.configure(border_color=_BORDER_INVALID, border_width=2)
        else:
            self._entry.configure(border_color=("gray60", "gray40"), border_width=2)

    def set_locked(self, locked: bool) -> None:
        """When locked, the entry becomes read-only and slightly faded."""
        self._locked = locked
        state = "disabled" if locked else "normal"
        self._entry.configure(state=state)
        self._entry.configure(text_color=_LOCKED_TEXT_COLOR if locked else _NORMAL_TEXT_COLOR)
        if self._unit_menu is not None:
            self._unit_menu.configure(state=state)


# ---------------------------------------------------------------------------
# Helper to recover the kind from an internal-unit string
# (Needed inside _on_unit_changed where we only kept the internal unit name.)
# ---------------------------------------------------------------------------

def kind_for_internal(internal: str) -> str:
    for kind, spec in display_mod.UNIT_KINDS.items():
        if spec["internal"] == internal:
            return kind
    raise KeyError(f"no kind has internal unit {internal!r}")
