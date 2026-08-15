"""
The parametric graph builder.

A sweep produces a grid of results, and there's no single obvious plot of it,
so this dialog lets you build one or two:

    [x] 2D    x: <swept>   y: <output>            + hold a variable
    [ ] 3D    x: <swept>   y: <swept>  z: <output> + hold a variable

    [Cancel]  [Show]

WHY THE HOLD PICKER EXISTS
--------------------------
Sweeping three variables gives a 4D result. A 2D plot can show two dimensions,
a 3D surface three, so the rest have to be pinned somewhere. The hold picker
pins them to values drawn from the grid the solver actually ran — not arbitrary
numbers — because anything off-grid has no data behind it.

Holds only offer swept variables that aren't already on an axis, and the list
updates as the axis dropdowns change.

OUTPUT GROUPING
---------------
A run has dozens of output variables and about six anyone plots. The output
dropdowns put those first under a header, everything else under a second one.
CTkOptionMenu has no notion of a non-selectable entry, so headers are marked
with box-drawing characters and selecting one silently reverts — the same
approach the old dialog used.

Returns (spec_2d, spec_3d), either of which may be None:

    {"x": wire, "y": wire, "z": wire, "holds": {wire: si_value}}
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app.widgets.filter_combo import FilterCombo

# Axis captions. "x-axis" alone doesn't say which of the two kinds of variable
# belongs there, and picking an output for the x of a 2D plot produces a
# meaningless graph rather than an error.
_AXIS_LABELS = {
    ("2d", "x"): "Parametrized variable (x-axis)",
    ("2d", "y"): "Output variable (y-axis)",
    ("3d", "x"): "Parametrized variable 1 (x-axis)",
    ("3d", "y"): "Parametrized variable 2 (y-axis)",
    ("3d", "z"): "Output variable (z-axis)",
}
_AXIS_LABEL_W = 200

_HEADER_PREFIX = "── "
_HEADER_SUFFIX = " ──"
_ADD_HOLD = "+ Hold a swept variable constant"
_NO_HOLDS_LEFT = "(no other swept variables)"


def _header(text: str) -> str:
    return f"{_HEADER_PREFIX}{text}{_HEADER_SUFFIX}"


def _is_header(value: str) -> bool:
    return value.startswith(_HEADER_PREFIX) and value.endswith(_HEADER_SUFFIX)


class _HoldPicker(ctk.CTkFrame):
    """Pin swept variables not on an axis to a value from the grid."""

    def __init__(self, master, *, hold_options: dict,
                 axis_vars_getter: Callable[[], set],
                 label_of: Callable[[str], str]) -> None:
        super().__init__(master, fg_color="transparent")
        self._hold_options = hold_options       # {wire: [(display, si_value)]}
        self._axis_vars = axis_vars_getter
        self._label_of = label_of
        self._held: dict[str, ctk.StringVar] = {}
        self._rows: dict[str, ctk.CTkFrame] = {}
        self._widgets: dict[str, tuple] = {}     # wire -> (combo, remove button)
        self._enabled = True

        self._picker_var = ctk.StringVar(value=_ADD_HOLD)
        self._picker = ctk.CTkOptionMenu(
            self, variable=self._picker_var, values=[_ADD_HOLD],
            command=self._on_pick, width=300, dynamic_resizing=False,
            font=ctk.CTkFont(size=theme.SIZE_SMALL))
        self._repack_picker()
        self.refresh()

    def _repack_picker(self) -> None:
        try:
            self._picker.pack_forget()
        except Exception:                       # noqa: BLE001
            pass
        self._picker.pack(anchor="w", pady=(theme.PAD_XS, 0))

    def refresh(self) -> None:
        """Re-offer whatever isn't on an axis and isn't already held.

        Also drops holds that have since been promoted onto an axis — pinning
        a variable you're now plotting against would silently reduce the plot
        to a single point.
        """
        on_axis = self._axis_vars()
        for wire in list(self._held):
            if wire in on_axis:
                self._remove(wire)

        available = [w for w in self._hold_options
                     if w not in on_axis and w not in self._held]
        self._picker.configure(
            values=[_ADD_HOLD] + [self._label_of(w) for w in available]
            if available else [_NO_HOLDS_LEFT])
        self._picker_var.set(_ADD_HOLD if available else _NO_HOLDS_LEFT)

    def _on_pick(self, label: str) -> None:
        for wire in self._hold_options:
            if self._label_of(wire) == label:
                self._add(wire)
                break
        self._picker_var.set(_ADD_HOLD)

    def _add(self, wire: str) -> None:
        options = self._hold_options.get(wire) or []
        if not options:
            return
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=1)
        # No fixed label width: the name and the box should sit together.
        # A 200 px column left a gulf between "Chamber pressure =" and its
        # value that read as a layout bug.
        ctk.CTkLabel(row, text=f"{self._label_of(wire)} =", anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_SMALL)).pack(
            side="left", padx=(0, theme.PAD_S))

        var = ctk.StringVar(value=options[0][0])
        self._held[wire] = var
        combo = FilterCombo(
            row, values=[display for display, _value in options],
            variable=var, width=190,
            font=ctk.CTkFont(size=theme.SIZE_SMALL))
        combo.pack(side="left")
        close = ctk.CTkButton(row, text="✕", width=28, height=24,
                              fg_color="transparent", text_color=theme.TEXT_MUTED,
                              hover_color=theme.CARD_HOVER,
                              command=lambda w=wire: self._remove_and_refresh(w))
        close.pack(side="left", padx=(theme.PAD_XS, 0))
        self._widgets[wire] = (combo, close)

        self._rows[wire] = row
        self._repack_picker()
        self.refresh()
        # A row added while the card is off must arrive greyed out too.
        if not self._enabled:
            self.set_enabled(False)

    def set_enabled(self, enabled: bool) -> None:
        """Grey out the picker and every hold row.

        The axis dropdowns already grey out with the row's checkbox; leaving
        the hold controls live made the card look half-disabled and let you
        edit a graph you'd just switched off.
        """
        self._enabled = enabled
        state = "normal" if enabled else "disabled"
        self._picker.configure(state=state)
        for combo, close in self._widgets.values():
            combo.configure(state=state)
            close.configure(state=state)

    def _remove(self, wire: str) -> None:
        row = self._rows.pop(wire, None)
        if row is not None:
            row.destroy()
        self._held.pop(wire, None)
        self._widgets.pop(wire, None)

    def _remove_and_refresh(self, wire: str) -> None:
        self._remove(wire)
        self._repack_picker()
        self.refresh()

    def holds(self) -> dict:
        """{wire: si_value} for everything currently pinned."""
        result = {}
        for wire, var in self._held.items():
            for display, value in self._hold_options.get(wire, []):
                if display == var.get():
                    result[wire] = value
                    break
        return result


class _GraphRow(ctk.CTkFrame):
    """One configurable graph: an enable box, axis dropdowns, and holds."""

    def __init__(self, master, *, kind: str, title: str, blurb: str, axes: list,
                 swept_pairs: list, output_groups: list,
                 hold_options: dict, label_of: Callable[[str], str],
                 enabled: bool, on_axis_change: Callable[[], None]) -> None:
        super().__init__(master, fg_color=theme.CARD_BG, corner_radius=8)
        self._kind = kind                       # "2d" or "3d", for the captions
        self._axes = axes                       # [("x","swept"), ("y","output")]
        self._on_axis_change = on_axis_change
        self._swept_labels = [label for label, _w in swept_pairs]
        # Guards the auto-move below against re-entering itself: moving y
        # fires y's own command, which would try to move x straight back.
        self._resolving = False

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=theme.PAD_M, pady=(theme.PAD_M, 0))
        self.enabled_var = ctk.BooleanVar(value=enabled)
        ctk.CTkCheckBox(header, text=title, variable=self.enabled_var,
                        command=self._sync_enabled,
                        font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold")).pack(
            side="left")
        ctk.CTkLabel(header, text=blurb, text_color=theme.TEXT_MUTED,
                     font=ctk.CTkFont(size=theme.SIZE_SMALL)).pack(
            side="left", padx=(theme.PAD_S, 0))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="x", padx=theme.PAD_M, pady=(theme.PAD_XS, theme.PAD_M))
        self._body = body

        self.axis_vars: dict[str, ctk.StringVar] = {}
        self._menus: list = []
        for axis_name, source in axes:
            pairs = swept_pairs if source == "swept" else None
            values = ([label for label, _w in swept_pairs] if pairs
                      else self._grouped_output_values(output_groups))
            default = values[0]
            if _is_header(default):
                default = values[1] if len(values) > 1 else default
            # Swept axes start on DIFFERENT variables. Both defaulting to the
            # first one gave a 3D card with the same variable on x and y,
            # which is a degenerate surface.
            if source == "swept":
                taken = {v.get() for a, v in self.axis_vars.items()
                         if dict(axes).get(a) == "swept"}
                free = [label for label in values if label not in taken]
                default = free[0] if free else default

            var = ctk.StringVar(value=default)
            self.axis_vars[axis_name] = var
            caption = _AXIS_LABELS.get((kind, axis_name), f"{axis_name}-axis")
            self._menus.append(self._labelled_menu(
                body, caption, var, values, source == "output"))

        # Built BEFORE the hold picker: the picker refreshes on construction
        # and calls straight back into axis_wires(), which needs this map.
        self._label_to_wire = {label: wire for label, wire in swept_pairs}
        for _group, pairs in output_groups:
            self._label_to_wire.update({label: wire for label, wire in pairs})

        self._holds = _HoldPicker(
            body, hold_options=hold_options,
            axis_vars_getter=self.axis_wires, label_of=label_of)
        self._holds.pack(fill="x", pady=(theme.PAD_S, 0))

        self._sync_enabled()

    @staticmethod
    def _grouped_output_values(output_groups: list) -> list[str]:
        values: list[str] = []
        for group_name, pairs in output_groups:
            if not pairs:
                continue
            values.append(_header(group_name))
            values.extend(label for label, _wire in pairs)
        return values or ["(none)"]

    def _labelled_menu(self, parent, label: str, var, values, guard_headers: bool):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(row, text=label, width=_AXIS_LABEL_W, anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_SMALL)).pack(side="left")
        menu = ctk.CTkOptionMenu(row, variable=var, values=values, width=300,
                                 dynamic_resizing=False,
                                 command=lambda _v: self._on_menu_changed(var),
                                 font=ctk.CTkFont(size=theme.SIZE_SMALL))
        menu.pack(side="left")
        if guard_headers:
            self._guard_headers(var, values)
        return menu

    @staticmethod
    def _guard_headers(var: ctk.StringVar, values: list[str]) -> None:
        """Revert if a group header gets selected.

        CTkOptionMenu can't mark an entry non-selectable, so the header is a
        normal item and we undo the selection. Silently: an error message for
        clicking a label would be worse than the click just not taking.
        """
        last = {"value": var.get()}

        def on_write(*_args) -> None:
            current = var.get()
            if _is_header(current):
                var.set(last["value"])
            else:
                last["value"] = current

        var.trace_add("write", on_write)

    def _on_menu_changed(self, changed_var) -> None:
        self._resolve_duplicates(changed_var)
        self._holds.refresh()
        self._on_axis_change()

    def _resolve_duplicates(self, changed_var) -> None:
        """Keep every swept axis on a different variable.

        Picking x = the variable already on y doesn't refuse the click; it
        moves y to the next free swept variable. Refusing would leave you
        unable to swap two axes without a pointless intermediate step.

        Only swept axes take part. Output axes draw from a different list, so
        they can never collide with a swept one.
        """
        if self._resolving:
            return
        swept_axes = [name for name, source in self._axes if source == "swept"]
        if len(swept_axes) < 2:
            return

        self._resolving = True
        try:
            taken = {changed_var.get()}
            for axis in swept_axes:
                var = self.axis_vars[axis]
                if var is changed_var:
                    continue
                if var.get() in taken:
                    free = [label for label in self._swept_labels
                            if label not in taken]
                    if free:
                        var.set(free[0])
                taken.add(var.get())
        finally:
            self._resolving = False

    def _sync_enabled(self) -> None:
        """Grey the body out when the row is unchecked."""
        enabled = bool(self.enabled_var.get())
        state = "normal" if enabled else "disabled"
        for menu in self._menus:
            menu.configure(state=state)
        self._holds.set_enabled(enabled)

    def axis_wires(self) -> set:
        return {self._label_to_wire.get(var.get())
                for var in self.axis_vars.values()} - {None}

    def spec(self) -> Optional[dict]:
        if not self.enabled_var.get():
            return None
        spec = {axis: self._label_to_wire.get(var.get())
                for axis, var in self.axis_vars.items()}
        if any(value is None for value in spec.values()):
            return None
        spec["holds"] = self._holds.holds()
        return spec


def show_parametric_graph_dialog(
    parent, *, swept_pairs: list, output_groups: list,
    hold_options: dict, label_of: Callable[[str], str],
) -> tuple[Optional[dict], Optional[dict]]:
    """Build a 2D and/or 3D parametric graph. Returns (spec_2d, spec_3d)."""
    window = ctk.CTkToplevel(parent)
    window.title("Parametric graphs")
    window.transient(parent.winfo_toplevel())
    window.resizable(False, False)

    width, height = 700, 560
    window.update_idletasks()
    try:
        root = parent.winfo_toplevel()
        x = root.winfo_rootx() + (root.winfo_width() - width) // 2
        y = root.winfo_rooty() + (root.winfo_height() - height) // 4
        window.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
    except Exception:                           # noqa: BLE001
        window.geometry(f"{width}x{height}")
    window.after(10, window.grab_set)

    result: dict = {"specs": (None, None)}

    actions = ctk.CTkFrame(window, fg_color="transparent")
    actions.pack(side="bottom", pady=(0, theme.PAD_M))

    # No heading: the window title already says "Parametric graphs".
    ctk.CTkLabel(
        window,
        text="A sweep is a grid of results. Choose which slice of it to plot; "
             "any swept variable not on an axis can be pinned to one of the "
             "values the solver actually ran.",
        text_color=theme.TEXT_MUTED, wraplength=560, justify="center",
        font=ctk.CTkFont(size=theme.SIZE_SMALL)).pack(
        pady=(theme.PAD_L, theme.PAD_M), padx=theme.PAD_M)

    body = ctk.CTkScrollableFrame(window, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=theme.PAD_M, pady=(0, theme.PAD_M))

    rows: list[_GraphRow] = []

    def on_axis_change() -> None:
        for row in rows:
            row._holds.refresh()                # noqa: SLF001

    row_2d = _GraphRow(
        body, kind="2d", title="2D plot",
        blurb="one output against one swept variable",
        axes=[("x", "swept"), ("y", "output")],
        swept_pairs=swept_pairs, output_groups=output_groups,
        hold_options=hold_options, label_of=label_of,
        enabled=True, on_axis_change=on_axis_change)
    row_2d.pack(fill="x", pady=(0, theme.PAD_S))
    rows.append(row_2d)

    # 3D needs two swept variables to have a surface to draw.
    if len(swept_pairs) >= 2:
        row_3d = _GraphRow(
            body, kind="3d", title="3D surface",
            blurb="one output over two swept variables",
            axes=[("x", "swept"), ("y", "swept"), ("z", "output")],
            swept_pairs=swept_pairs, output_groups=output_groups,
            hold_options=hold_options, label_of=label_of,
            enabled=False, on_axis_change=on_axis_change)
        row_3d.pack(fill="x", pady=(0, theme.PAD_S))
        rows.append(row_3d)
    else:
        row_3d = None
        ctk.CTkLabel(
            body,
            text="A 3D surface needs two swept variables. This run swept one.",
            text_color=theme.TEXT_FAINT, wraplength=560,
            font=ctk.CTkFont(size=theme.SIZE_SMALL)).pack(
            fill="x", pady=theme.PAD_S)

    def cancel() -> None:
        result["specs"] = (None, None)
        window.destroy()

    def show() -> None:
        spec_2d = row_2d.spec()
        spec_3d = row_3d.spec() if row_3d is not None else None
        # A 3D surface with the same variable on both axes is degenerate.
        if spec_3d and spec_3d.get("x") == spec_3d.get("y"):
            spec_3d = None
        result["specs"] = (spec_2d, spec_3d)
        window.destroy()

    ctk.CTkButton(actions, text="Cancel", width=140, height=36,
                  fg_color="transparent", border_width=1,
                  text_color=theme.TEXT_MUTED, hover_color=theme.CARD_HOVER,
                  command=cancel).pack(side="left", padx=theme.PAD_S)
    ctk.CTkButton(actions, text="Show", width=140, height=36,
                  fg_color=theme.ACCENT_SLATE,
                  hover_color=theme.ACCENT_SLATE_HOVER,
                  command=show).pack(side="left", padx=theme.PAD_S)
    window.protocol("WM_DELETE_WINDOW", cancel)

    window.wait_window()
    return result["specs"]
