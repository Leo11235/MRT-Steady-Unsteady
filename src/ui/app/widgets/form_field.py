"""
LabeledField — one row of an input form.

    [ Label            ] [ entry .................... ] [ unit v ]

Built from a FieldSpec, so the label, tooltip, unit list, starting unit and
value type all come from the field registry rather than the call site:

    LabeledField(parent, registry.get("chamber_pressure"))

VALUE MODEL
-----------
Config files store every physical input as a [value, unit] pair, and so does
this widget.  What the user typed and the unit they typed it in are BOTH
preserved end to end — nothing is silently normalised behind their back.

    to_pair()     -> [3.5, "MPa"]  exactly what's on screen
    from_pair()   <- [3.5, "MPa"]  shows 3.5 and selects MPa
    get_si()      -> 3500000.0     for preflight and validation

That means loading a preset shows the numbers as they were written in the file,
not converted into some canonical unit.  A grain length saved as 609.6 mm comes
back as 609.6 mm rather than 0.6096 m.

Changing the unit dropdown converts the displayed number, so picking "in" after
typing 100 mm leaves 3.937 rather than a bare 100.  That's a conversion, not a
reinterpretation: the physical quantity is unchanged.

BLANK VS ZERO
-------------
An empty entry means "not filled" and yields [None, unit], which is exactly how
an unused 'one or the other' field is written to disk.  A typed 0 is a real
value and yields [0.0, unit].  The distinction matters: 0 is a legitimate
ullage fraction and a legitimate valve time constant.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

from src.common import variable_conversions as vc
from src.ui.app import theme
from src.ui.app.field_registry import FieldSpec
from src.ui.app.widgets.tooltip import Tooltip


_LABEL_WIDTH = 220
_UNIT_WIDTH = 78
_BORDER_NORMAL = ("gray60", "gray40")


class LabeledField(ctk.CTkFrame):
    """One labelled input, wired to a FieldSpec."""

    def __init__(
        self,
        master,
        spec: FieldSpec,
        *,
        system: str = "SI",
        label_width: int = _LABEL_WIDTH,
        on_change: Optional[Callable[[str], None]] = None,
        show_help: bool = True,
    ) -> None:
        super().__init__(master, fg_color="transparent")

        self.spec = spec
        self.key = spec.key
        # The user's unit system, from settings. Decides what unit a blank
        # field starts in; a loaded preset overrides it per field.
        self.system = system
        self._locked = False
        self._on_change = on_change

        # ---- label ---------------------------------------------------
        self._label = ctk.CTkLabel(self, text=spec.label, anchor="w",
                                   width=label_width)
        self._label.pack(side="left", padx=(0, theme.PAD_S))

        # ---- value ---------------------------------------------------
        self.var = ctk.StringVar()

        # The exact SI value behind whatever is displayed, kept so that
        # switching units repeatedly doesn't accumulate rounding — see
        # _on_unit_changed.  None whenever the entry is blank or unparseable.
        self._si_cache: Optional[float] = None
        self._updating_display = False
        self.var.trace_add("write", lambda *_: self._refresh_si_cache())

        if on_change is not None:
            self.var.trace_add("write", lambda *_: on_change(self.var.get()))

        if spec.choices:
            # Fixed set of valid answers: a dropdown can't be typo'd.
            self._entry = ctk.CTkOptionMenu(self, values=list(spec.choices),
                                            variable=self.var)
        else:
            self._entry = ctk.CTkEntry(self, textvariable=self.var)
        self._entry.pack(side="left", fill="x", expand=True)

        # ---- unit ----------------------------------------------------
        # Dimensionless and text fields get nothing here; single-option
        # categories get a static label, since a one-item dropdown is a lie.
        self._unit_var = ctk.StringVar(value=spec.unit_for(system))
        self._unit_menu: ctk.CTkOptionMenu | None = None
        options = spec.unit_options

        if len(options) >= 2:
            self._unit_menu = ctk.CTkOptionMenu(
                self, values=options, variable=self._unit_var,
                command=self._on_unit_changed,
                width=_UNIT_WIDTH, dynamic_resizing=False,
            )
            self._unit_menu.pack(side="left", padx=(theme.PAD_S, 0))
        elif len(options) == 1:
            ctk.CTkLabel(self, text=options[0], anchor="w",
                         width=_UNIT_WIDTH,
                         text_color=theme.TEXT_MUTED).pack(
                side="left", padx=(theme.PAD_S, 0))
        else:
            # Keeps the entry column aligned with fields that do have units.
            ctk.CTkLabel(self, text="", width=_UNIT_WIDTH).pack(
                side="left", padx=(theme.PAD_S, 0))

        # What the dropdown was before the last change, so we know what to
        # convert FROM.
        self._previous_unit = self._unit_var.get()

        # Pre-fill from the registry default, which arrives as a [value, unit]
        # pair and therefore brings its own unit with it.
        if spec.default is not None:
            self.from_pair(spec.default)

        # ---- help ----------------------------------------------------
        # Attached to both halves, so hovering anywhere on the row works.
        if show_help and spec.help:
            Tooltip(self._label, spec.help)
            Tooltip(self._entry, spec.help)

    # ==================================================================
    # Reading and writing
    # ==================================================================

    @property
    def unit(self) -> str:
        """The unit currently selected."""
        return self._unit_var.get()

    def get_text(self) -> str:
        """Exactly what's in the entry, untouched."""
        return self.var.get().strip()

    def is_blank(self) -> bool:
        return self.get_text() == ""

    def to_pair(self) -> list:
        """This field as a [value, unit] config pair.

        Blank gives [None, unit], which is how an unused alternate is written.
        Text fields give their string.  A number that won't parse comes back as
        the raw string, so the validator can report it rather than this widget
        swallowing it.
        """
        raw = self.get_text()
        unit = self.unit

        if self.spec.value_type == "text":
            return raw

        if raw == "":
            return [None, unit]

        try:
            value = int(raw) if self.spec.value_type == "int" else float(raw)
        except ValueError:
            return [raw, unit]      # invalid; let validation catch it
        return [value, unit]

    def from_pair(self, pair: Any) -> None:
        """Populate from a config pair, adopting the unit it was saved in.

        Deliberately does NOT convert into whatever unit is currently selected:
        showing the file's own numbers makes a loaded preset recognisable.
        Accepts a bare number too, for configs written before the pair format.
        """
        if self.spec.value_type == "text":
            self.var.set("" if pair is None else str(pair))
            return

        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            value, unit = pair
            if unit and vc.is_known_unit(unit):
                canonical = vc._canonical(unit)
                if canonical in self.spec.unit_options:
                    self._set_unit_silently(canonical)
        else:
            value = pair

        if value is None or value == "":
            self.var.set("")
        else:
            self.var.set(_format_number(value))

    def get_si(self) -> Optional[float]:
        """This field's value in SI, or None when blank or unparseable.

        For validation and preflight, which think in SI.  Never used to write
        a config — that's to_pair()'s job.
        """
        pair = self.to_pair()
        if not isinstance(pair, (list, tuple)):
            return None
        value, unit = pair
        if not isinstance(value, (int, float)):
            return None
        try:
            return vc.to_SI(value, unit)
        except (ValueError, KeyError):
            return None

    def clear(self) -> None:
        """Blank the value and go back to the unit system's starting unit."""
        self.var.set("")
        self._set_unit_silently(self.spec.unit_for(self.system))

    def reset_to_default(self) -> None:
        """Back to the registry default, or blank if there isn't one."""
        self.clear()
        if self.spec.default is not None:
            self.from_pair(self.spec.default)

    # ==================================================================
    # Unit changes
    # ==================================================================

    def _refresh_si_cache(self) -> None:
        """Recompute the exact SI value from what's typed.

        Runs on every keystroke.  Skipped while we're rewriting the display
        ourselves, because at that moment the entry holds a rounded number and
        recomputing from it is exactly the drift we're avoiding.
        """
        if self._updating_display:
            return
        raw = self.get_text()
        if raw == "" or self.spec.value_type == "text":
            self._si_cache = None
            return
        try:
            self._si_cache = vc.to_SI(float(raw), self.unit)
        except (ValueError, KeyError):
            self._si_cache = None

    def _set_unit_silently(self, unit: str) -> None:
        """Select a unit WITHOUT converting the displayed number.

        Used when loading a preset, where the number already belongs to that
        unit and converting it would corrupt the value.
        """
        self._unit_var.set(unit)
        self._previous_unit = unit
        self._refresh_si_cache()

    def set_system(self, system: str) -> None:
        """Switch this field to the given unit system's unit for its category.

        Converts whatever is typed, so the physical quantity is preserved and
        only its presentation changes. A no-op if the field is dimensionless,
        is a text field, or is already showing the right unit.

        Called when the program-wide unit preference changes. Without this, a
        page built before the change keeps whatever units it was born with,
        because pages are cached and never rebuilt.
        """
        self.system = system
        if self.spec.value_type == "text":
            return
        target = self.spec.unit_for(system)
        if not target or target == self.unit:
            return
        # Route through the dropdown so the conversion path is the same one a
        # manual change takes, cached SI value and all.
        self._unit_var.set(target)
        self._on_unit_changed(target)

    def _on_unit_changed(self, new_unit: str) -> None:
        """Convert what's typed into the newly selected unit.

        Converts from the cached SI value rather than from the number on
        screen.  That matters because the display is rounded to 6 significant
        figures: going 32 mm -> in -> mm via the display gives 31.9999, while
        going via SI gives 32 back exactly.  Chain a few unit switches and the
        difference stops being cosmetic.

        Blanks and half-typed text are left alone. There's nothing meaningful
        to convert, and rewriting under the user's cursor would be hostile.
        """
        old_unit = self._previous_unit
        self._previous_unit = new_unit

        raw = self.get_text()
        if raw == "" or self.spec.value_type == "text":
            return

        try:
            if self._si_cache is not None:
                converted = vc.from_SI(self._si_cache, new_unit)
            else:
                converted = vc.convert(float(raw), old_unit, new_unit)
        except (ValueError, KeyError, TypeError):
            return

        # Rewrite the display without letting the trace clobber the cache.
        exact = self._si_cache
        self._updating_display = True
        try:
            self.var.set(_format_number(converted))
        finally:
            self._updating_display = False
        self._si_cache = exact

    # ==================================================================
    # Visual state
    # ==================================================================

    def mark_invalid(self, invalid: bool = True) -> None:
        """Red ring on the entry.  Cleared by calling with False."""
        if isinstance(self._entry, ctk.CTkEntry):
            self._entry.configure(
                border_color=theme.ERROR if invalid else _BORDER_NORMAL,
                border_width=2)

    def set_locked(self, locked: bool) -> None:
        """Read-only and faded, for fields the current mode computes itself."""
        self._locked = locked
        state = "disabled" if locked else "normal"
        self._entry.configure(state=state)
        if isinstance(self._entry, ctk.CTkEntry):
            self._entry.configure(
                text_color=theme.TEXT_LOCKED if locked else ("gray10", "gray90"))
        if self._unit_menu is not None:
            self._unit_menu.configure(state=state)

    @property
    def is_locked(self) -> bool:
        return self._locked


# =============================================================================
# Number formatting
# =============================================================================

def _format_number(value: Any) -> str:
    """Render a number for an entry box: readable, and round-trip safe.

    Whole numbers lose their ".0", everything else gets 6 significant figures.
    That's enough to survive a unit round-trip (mm to in and back) without
    filling the box with floating-point noise like 0.60960000000000003.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number) and abs(number) < 1e15:
        return str(int(number))
    return f"{number:.6g}"
