"""
ParametricList — dynamic add/remove list of variables to sweep.

Each row owns three text fields (low_end, high_end, step_size).  Variable
names are shown using PARAM_VAR_DISPLAY from display.py; the wire form
stays in PARAM_VAR_VALUE for round-tripping.

A `on_change` callback is fired whenever rows are added or removed, so
the parent page can refresh anything that depends on which variables are
parametrized (e.g. hiding the corresponding field on another tab).
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

import customtkinter as ctk

from src.ui.app import theme, display as display_mod


# Variables the user is allowed to parametrize, per the PDF sketch.
PARAMETRIZABLE_VARS: tuple[str, ...] = tuple(display_mod.PARAM_VAR_DISPLAY.keys())


# --------------------------------------------------------------------------
# Row
# --------------------------------------------------------------------------

class _ParamRow(ctk.CTkFrame):
    """One {low, high, step} row inside a ParametricList."""

    def __init__(self, master, *, var_name: str,
                 on_remove: Callable[["_ParamRow"], None]) -> None:
        super().__init__(master, fg_color=("gray90", "gray18"), corner_radius=6)
        self.var_name = var_name             # wire form (snake_case)
        self._on_remove = on_remove

        self.low_var  = ctk.StringVar()
        self.high_var = ctk.StringVar()
        self.step_var = ctk.StringVar()

        # ---- header: pretty variable name + remove button --------------
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=theme.PAD_S, pady=(theme.PAD_S, 2))

        ctk.CTkLabel(
            header,
            text=display_mod.PARAM_VAR_DISPLAY.get(var_name, var_name),
            anchor="w",
            font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold"),
        ).pack(side="left")

        ctk.CTkButton(
            header, text="✕", width=24, height=24, corner_radius=12,
            fg_color="transparent",
            text_color=("#b00020", "#ff6b6b"),
            hover_color=("gray80", "gray25"),
            command=lambda: self._on_remove(self),
        ).pack(side="right")

        # ---- low / high / step grid -----------------------------------
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=theme.PAD_S, pady=(0, theme.PAD_S))

        def _input(label_text: str, var) -> None:
            row = ctk.CTkFrame(grid, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=label_text, width=90, anchor="w") \
                .pack(side="left")
            ctk.CTkEntry(row, textvariable=var) \
                .pack(side="left", fill="x", expand=True)

        _input("Low end",   self.low_var)
        _input("High end",  self.high_var)
        _input("Step size", self.step_var)

    def to_dict(self) -> dict:
        def num(s: str):
            s = s.strip()
            if s == "":
                return None
            try:
                v = float(s)
                return int(v) if v.is_integer() else v
            except ValueError:
                return s
        return {
            "low_end":   num(self.low_var.get()),
            "high_end":  num(self.high_var.get()),
            "step_size": num(self.step_var.get()),
        }

    def from_dict(self, spec: dict) -> None:
        self.low_var.set("" if spec.get("low_end")   is None else str(spec["low_end"]))
        self.high_var.set("" if spec.get("high_end")  is None else str(spec["high_end"]))
        self.step_var.set("" if spec.get("step_size") is None else str(spec["step_size"]))


# --------------------------------------------------------------------------
# List
# --------------------------------------------------------------------------

_ADD_PLACEHOLDER = "➕  Add parameter"
_NONE_LEFT_LABEL = "(all variables already added)"


class ParametricList(ctk.CTkFrame):
    """Container for zero or more _ParamRow widgets plus an add-picker."""

    def __init__(self, master, *,
                 allowed_vars: Iterable[str] = PARAMETRIZABLE_VARS,
                 on_change: Optional[Callable[[], None]] = None) -> None:
        super().__init__(master, fg_color="transparent")
        self._allowed_vars = tuple(allowed_vars)
        self._on_change = on_change
        self._rows: list[_ParamRow] = []

        # Layout: rows pack directly into `self`, each one inserted with
        # `before=self._footer` so the picker always stays at the bottom.
        # Earlier versions had a separate `_rows_box` CTkFrame to hold the
        # rows, but CTkFrame's default height of 200px doesn't collapse to
        # zero even with no children — that produced a phantom ~one-row gap
        # whenever there were no parameters added.  Removing the container
        # fixes the ghost space.
        self._footer = ctk.CTkFrame(self, fg_color="transparent")
        self._footer.pack(fill="x", pady=(theme.PAD_S, 0))

        self._add_var = ctk.StringVar(value="")
        self._add_menu = ctk.CTkOptionMenu(
            self._footer,
            variable=self._add_var,
            values=self._available_display_options(),
            command=self._on_add_selected,
            dynamic_resizing=False,
            width=260,
        )
        self._add_menu.set(_ADD_PLACEHOLDER)
        self._add_menu.pack(side="left")

    # ----------------------------------------------------------------
    # Internal
    # ----------------------------------------------------------------

    def _used_vars(self) -> set[str]:
        return {r.var_name for r in self._rows}

    def _available_display_options(self) -> list[str]:
        used = self._used_vars()
        avail = [v for v in self._allowed_vars if v not in used]
        if not avail:
            return [_NONE_LEFT_LABEL]
        return [display_mod.PARAM_VAR_DISPLAY[v] for v in avail]

    def _refresh_picker(self) -> None:
        self._add_menu.configure(values=self._available_display_options())
        self._add_menu.set(_ADD_PLACEHOLDER)

    def _on_add_selected(self, choice_display: str) -> None:
        # Translate display name back to wire form
        choice_wire = display_mod.PARAM_VAR_VALUE.get(choice_display, choice_display)
        if choice_wire not in self._allowed_vars or choice_wire in self._used_vars():
            self._add_menu.set(_ADD_PLACEHOLDER)
            return
        self.add_row(choice_wire)
        self._refresh_picker()
        self._fire_change()

    def _remove_row(self, row: _ParamRow) -> None:
        self._rows.remove(row)
        row.destroy()
        self._refresh_picker()
        self._fire_change()

    def _fire_change(self) -> None:
        if self._on_change is not None:
            try:
                self._on_change()
            except Exception:
                pass    # don't let consumer errors break the list

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    def add_row(self, var_name: str, spec: Optional[dict] = None) -> _ParamRow:
        row = _ParamRow(self, var_name=var_name, on_remove=self._remove_row)
        row.pack(fill="x", pady=theme.PAD_XS, before=self._footer)
        self._rows.append(row)
        if spec is not None:
            row.from_dict(spec)
        return row

    def clear(self, fire_change: bool = True) -> None:
        for row in list(self._rows):
            row.destroy()
        self._rows.clear()
        self._refresh_picker()
        if fire_change:
            self._fire_change()

    def used_vars(self) -> list[str]:
        """Wire-form names of currently-parametrized variables."""
        return [r.var_name for r in self._rows]

    def to_dict(self) -> dict:
        return {row.var_name: row.to_dict() for row in self._rows}

    def from_dict(self, d: dict) -> None:
        self.clear(fire_change=False)
        if isinstance(d, dict):
            for var_name, spec in d.items():
                if var_name in self._allowed_vars and isinstance(spec, dict):
                    self.add_row(var_name, spec)
        self._refresh_picker()
        self._fire_change()
