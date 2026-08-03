"""Modal for building 2D / 3D graphs from a parametric-study result.

Users configure one or both graphs via dropdowns and enable-checkboxes,
then hit Show to open each in its own matplotlib window.

Extras beyond raw axis selection:
  - Output-variable dropdowns are grouped into "common" and "other" using
    in-list header entries (non-selectable — if the user clicks one, the
    previous value is silently restored).
  - Each graph row has a "hold picker" underneath the axis dropdowns:
    the user can pin any non-axis swept variable to a specific value
    (drawn from the actual grid the sim ran on).  The value combobox
    supports type-ahead prefix filtering.

Usage from steady_results.py:

    ParametricGraphDialog(
        parent=self,
        swept_vars=[(pretty, wire), ...],
        output_var_groups=[
            ("Common outputs",     [(pretty, wire), ...]),
            ("All other outputs",  [(pretty, wire), ...]),
        ],
        default_output="Isp",
        hold_value_options={wire: [(display_str, si_value), ...], ...},
        hold_unit_labels={wire: "psi", wire: "kg/s", ...},
        on_confirm=self._render_parametric_graphs,
    )

`on_confirm` is called with `spec_2d`, `spec_3d`.  Either may be None
if the user unchecked that row.  Each spec is a dict:

    spec_2d = {"x": wire, "y": wire, "holds": {wire: si_value, ...}}
    spec_3d = {"x": wire, "y": wire, "z": wire,
               "holds": {wire: si_value, ...}}
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from src.ui.app import theme


# In-list group-header markers for the output dropdown.  We can't make
# CTkOptionMenu entries non-clickable, so we detect header selection
# with these delimiters and silently revert.
_HEADER_PREFIX = "── "
_HEADER_SUFFIX = " ──"
_ADD_HOLD_PLACEHOLDER = "+ Hold parametrized variable constant"


def _is_header(value: str) -> bool:
    return value.startswith(_HEADER_PREFIX) and value.endswith(_HEADER_SUFFIX)


# ---------------------------------------------------------------------------
# Hold picker (one per graph row)
# ---------------------------------------------------------------------------

class _HoldPicker(ctk.CTkFrame):
    """A '+' picker plus a list of per-variable hold rows.

    Each hold row shows:  <var pretty name>: Hold constant at [ combobox ]  unit  [×]

    The combobox is populated from `hold_value_options[wire]` — a list
    of (display_string, si_value) pairs — and supports type-ahead: as
    the user types, the dropdown values shrink to items starting with
    the typed prefix.
    """

    def __init__(
        self, parent, *,
        wire_to_pretty: dict[str, str],
        hold_value_options: dict[str, list[tuple[str, float]]],
        hold_unit_labels: dict[str, str],
        axis_vars_provider: Callable[[], set[str]],
        on_layout_changed: Callable[[], None] | None = None,
    ) -> None:
        # height=0 so the picker collapses to just its children when empty.
        # (CTkFrame's default height of 200 would otherwise leave a fat
        # empty rectangle below the picker on first open.)
        super().__init__(parent, fg_color="transparent", height=0)
        self._wire_to_pretty     = wire_to_pretty
        self._hold_value_options = hold_value_options
        self._hold_unit_labels   = hold_unit_labels
        self._axis_vars_provider = axis_vars_provider
        self._on_layout_changed  = on_layout_changed

        # {wire: {"row": frame, "var": StringVar, "combo": CTkComboBox}}
        self._holds: dict[str, dict] = {}

        # ---- picker row (dropdown that ADDS a hold on selection) -----
        self._picker_row = ctk.CTkFrame(self, fg_color="transparent",
                                        height=0)
        self._picker_row.pack(fill="x", pady=(theme.PAD_XS, 0))

        self._picker_var = ctk.StringVar(value=_ADD_HOLD_PLACEHOLDER)
        self._picker_menu = ctk.CTkOptionMenu(
            self._picker_row,
            variable=self._picker_var,
            values=[_ADD_HOLD_PLACEHOLDER],
            command=self._on_picker_choice,
            dynamic_resizing=False,
            width=280,
        )
        self._picker_menu.pack(side="left")

        # Hold rows pack directly into self (below _picker_row) — no
        # separate wrapper frame, since an empty CTkFrame refuses to
        # collapse below its default 200-px height.
        self.refresh_picker_options()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh_picker_options(self) -> None:
        """Call whenever axis vars change so the "+" dropdown re-computes
        which swept vars are still available to hold, and any holds that
        just became axis vars get auto-removed."""
        axis = set(self._axis_vars_provider())
        # Drop holds whose var just became an axis.
        for w in list(self._holds.keys()):
            if w in axis:
                self._remove_hold(w)
        # Recompute the picker's dropdown values.
        available = [
            w for w in self._hold_value_options.keys()
            if w not in axis and w not in self._holds
        ]
        if not available:
            values = ["(nothing more to hold)"]
        else:
            values = [_ADD_HOLD_PLACEHOLDER] + [
                self._wire_to_pretty.get(w, w) for w in available
            ]
        self._picker_menu.configure(values=values)
        self._picker_var.set(values[0])
        self._picker_menu.configure(
            state="disabled" if not available else "normal"
        )

    def get_holds_si(self) -> dict[str, float]:
        """Return {wire: si_value} for every hold whose combobox value
        matches one of the pre-populated grid points.  Values that don't
        match are silently dropped (safer than partial holds)."""
        out: dict[str, float] = {}
        for wire, info in self._holds.items():
            typed = info["var"].get().strip()
            if not typed:
                continue
            for display, si in self._hold_value_options.get(wire, []):
                if display == typed:
                    out[wire] = si
                    break
        return out

    # ------------------------------------------------------------------
    # Internal — add / remove holds
    # ------------------------------------------------------------------

    def _on_picker_choice(self, choice: str) -> None:
        if choice == _ADD_HOLD_PLACEHOLDER or _is_header(choice):
            return
        # Translate pretty label back to wire.
        wire = next(
            (w for w in self._hold_value_options
             if self._wire_to_pretty.get(w, w) == choice),
            None,
        )
        if wire is None or wire in self._holds:
            return
        self._add_hold(wire)
        self.refresh_picker_options()
        self._fire_layout_changed()

    def _add_hold(self, wire: str) -> None:
        pretty = self._wire_to_pretty.get(wire, wire)
        options   = self._hold_value_options.get(wire, [])
        unit_lbl  = self._hold_unit_labels.get(wire, "")
        displays  = [d for d, _ in options]

        # Pack directly into self (no wrapper frame) so removing all
        # holds leaves no residual empty space.
        row = ctk.CTkFrame(self, fg_color="transparent", height=0)
        row.pack(fill="x", pady=1)

        ctk.CTkLabel(
            row, text=f"{pretty}: Hold constant at",
            anchor="w",
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
        ).pack(side="left", padx=(0, theme.PAD_XS))

        # Store the full option list so the type-ahead trace can restore
        # it and filter fresh each keystroke.
        var = ctk.StringVar(value=displays[0] if displays else "")
        combo = ctk.CTkComboBox(
            row, variable=var, values=displays,
            width=120, state="normal",
        )
        combo.pack(side="left")

        if unit_lbl:
            ctk.CTkLabel(
                row, text=unit_lbl,
                anchor="w",
                text_color=theme.TEXT_MUTED,
                font=ctk.CTkFont(size=theme.SIZE_SMALL),
            ).pack(side="left", padx=(theme.PAD_XS, 0))

        ctk.CTkButton(
            row, text="✕", width=22, height=22, corner_radius=11,
            fg_color="transparent",
            text_color=("#b00020", "#ff6b6b"),
            hover_color=("gray80", "gray25"),
            command=lambda w=wire: self._remove_hold_and_refresh(w),
        ).pack(side="left", padx=(theme.PAD_XS, 0))

        # Type-ahead: whenever the entry text changes, shrink the
        # combobox's dropdown to values starting with what's typed.
        # The full list stays in `displays`; we re-derive on each write.
        state = {"guard": False}

        def _on_typed(*_):
            if state["guard"]:
                return
            typed = var.get()
            if not typed:
                filtered = displays
            else:
                filtered = [d for d in displays if d.startswith(typed)]
            if not filtered:
                # Show all if nothing matches — avoids an empty dropdown.
                filtered = displays
            try:
                combo.configure(values=filtered)
            except Exception:
                pass

        var.trace_add("write", _on_typed)

        self._holds[wire] = {"row": row, "var": var, "combo": combo,
                             "displays": displays}

    def _remove_hold(self, wire: str) -> None:
        info = self._holds.pop(wire, None)
        if info is None:
            return
        try:
            info["row"].destroy()
        except Exception:
            pass

    def _remove_hold_and_refresh(self, wire: str) -> None:
        self._remove_hold(wire)
        self.refresh_picker_options()
        self._fire_layout_changed()

    def _fire_layout_changed(self) -> None:
        if self._on_layout_changed is not None:
            try:
                self._on_layout_changed()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class ParametricGraphDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        *,
        swept_vars: list[tuple[str, str]],
        output_var_groups: list[tuple[str, list[tuple[str, str]]]],
        default_output: str,
        hold_value_options: dict[str, list[tuple[str, float]]] | None = None,
        hold_unit_labels:   dict[str, str]                        | None = None,
        on_confirm: Callable[[dict | None, dict | None], None] = lambda a, b: None,
        title: str = "Choose graph to display",
    ) -> None:
        super().__init__(parent)
        self.title(title)
        # No fixed geometry: we shrink-wrap to whatever the packed
        # children need.  _resize_to_content() runs after the initial
        # layout and again whenever hold rows are added / removed.
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.resizable(False, True)
        self.minsize(760, 100)

        self._on_confirm = on_confirm

        # ---- look-up tables + flat dropdown values -------------------
        self._swept_pretty_to_wire  = {p: w for p, w in swept_vars}
        self._swept_wire_to_pretty  = {w: p for p, w in swept_vars}
        self._output_pretty_to_wire: dict[str, str] = {}
        output_dropdown_values: list[str] = []
        for group_header, entries in output_var_groups:
            if entries:
                if len(output_var_groups) > 1:
                    output_dropdown_values.append(
                        f"{_HEADER_PREFIX}{group_header}{_HEADER_SUFFIX}"
                    )
                for pretty, wire in entries:
                    output_dropdown_values.append(pretty)
                    self._output_pretty_to_wire[pretty] = wire

        swept_prettys = [p for p, _ in swept_vars]

        default_output_pretty = next(
            (p for p, w in self._output_pretty_to_wire.items()
             if w == default_output),
            next((v for v in output_dropdown_values if not _is_header(v)), ""),
        )

        self._enable_3d = (len(swept_vars) >= 2)

        # ---- header --------------------------------------------------
        ctk.CTkLabel(
            self,
            text="Construct the graphs you want. Each opens in its own "
                 "matplotlib window.",
            font=ctk.CTkFont(size=theme.SIZE_BODY),
            text_color=theme.TEXT_MUTED,
            anchor="w", justify="left", wraplength=700,
        ).pack(fill="x", padx=theme.PAD_L, pady=(theme.PAD_L, theme.PAD_M))

        # Footer is built here but packed at the very end (after both
        # graph rows) so it always sits right below the 3D row rather
        # than floating at the bottom of a fixed-size window.
        self._footer = ctk.CTkFrame(self, fg_color="transparent", height=0)

        ctk.CTkButton(
            self._footer, text="Cancel", width=100,
            fg_color="transparent", border_width=1,
            text_color=("gray25", "gray75"),
            command=self.destroy,
        ).pack(side="right")

        ctk.CTkButton(
            self._footer, text="Show", width=140,
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            fg_color=theme.SUCCESS,
            hover_color=theme.SUCCESS_HOVER,
            command=self._on_show_click,
        ).pack(side="right", padx=(0, theme.PAD_S))

        # ---- 2D row --------------------------------------------------
        row2d = ctk.CTkFrame(self, fg_color=("gray92", "gray17"),
                             corner_radius=8)
        row2d.pack(fill="x", padx=theme.PAD_L, pady=theme.PAD_XS)

        self._enable_2d_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            row2d, text="2D graph",
            variable=self._enable_2d_var,
            font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold"),
        ).pack(anchor="w", padx=theme.PAD_M, pady=(theme.PAD_M, 2))

        controls_2d = ctk.CTkFrame(row2d, fg_color="transparent")
        controls_2d.pack(fill="x", padx=theme.PAD_L,
                         pady=(0, theme.PAD_XS))

        self._y2d_var = ctk.StringVar(value=default_output_pretty)
        self._x2d_var = ctk.StringVar(
            value=swept_prettys[0] if swept_prettys else ""
        )
        self._labeled_option(
            controls_2d, "Output variable (y-axis)",
            self._y2d_var, output_dropdown_values, width=240,
        )
        self._labeled_option(
            controls_2d, "Parametrized variable (x-axis)",
            self._x2d_var, swept_prettys, width=240,
            padx=(theme.PAD_L, 0),
        )
        self._install_header_filter(self._y2d_var)

        # 2D hold picker
        self._hold_2d = _HoldPicker(
            row2d,
            wire_to_pretty=self._swept_wire_to_pretty,
            hold_value_options=hold_value_options or {},
            hold_unit_labels=hold_unit_labels or {},
            axis_vars_provider=lambda: {
                self._swept_pretty_to_wire.get(self._x2d_var.get(),
                                               self._x2d_var.get()),
            },
            on_layout_changed=lambda: self._resize_to_content(),
        )
        self._hold_2d.pack(fill="x", padx=theme.PAD_L,
                           pady=(0, theme.PAD_M))
        # Refresh the hold picker whenever the x-axis changes.
        self._x2d_var.trace_add(
            "write", lambda *_: self._hold_2d.refresh_picker_options()
        )

        # ---- 3D row --------------------------------------------------
        row3d = ctk.CTkFrame(self, fg_color=("gray92", "gray17"),
                             corner_radius=8)
        row3d.pack(fill="x", padx=theme.PAD_L, pady=theme.PAD_XS)

        self._enable_3d_var = ctk.BooleanVar(value=self._enable_3d)
        self._3d_check = ctk.CTkCheckBox(
            row3d, text="3D graph",
            variable=self._enable_3d_var,
            font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold"),
        )
        self._3d_check.pack(anchor="w", padx=theme.PAD_M,
                            pady=(theme.PAD_M, 2))

        controls_3d = ctk.CTkFrame(row3d, fg_color="transparent")
        controls_3d.pack(fill="x", padx=theme.PAD_L,
                         pady=(0, theme.PAD_XS))

        default_x_3d = swept_prettys[0] if swept_prettys else ""
        default_y_3d = (swept_prettys[1] if len(swept_prettys) > 1
                        else swept_prettys[0] if swept_prettys else "")

        self._z3d_var = ctk.StringVar(value=default_output_pretty)
        self._x3d_var = ctk.StringVar(value=default_x_3d)
        self._y3d_var = ctk.StringVar(value=default_y_3d)

        self._z3d_menu = self._labeled_option(
            controls_3d, "Output variable (z-axis)",
            self._z3d_var, output_dropdown_values, width=210,
        )
        self._x3d_menu = self._labeled_option(
            controls_3d, "Parametrized variable 1 (x-axis)",
            self._x3d_var, swept_prettys, width=210,
            padx=(theme.PAD_L, 0),
        )
        self._y3d_menu = self._labeled_option(
            controls_3d, "Parametrized variable 2 (y-axis)",
            self._y3d_var, swept_prettys, width=210,
            padx=(theme.PAD_L, 0),
        )

        self._install_header_filter(self._z3d_var)

        # 3D hold picker
        self._hold_3d = _HoldPicker(
            row3d,
            wire_to_pretty=self._swept_wire_to_pretty,
            hold_value_options=hold_value_options or {},
            hold_unit_labels=hold_unit_labels or {},
            axis_vars_provider=lambda: {
                self._swept_pretty_to_wire.get(self._x3d_var.get(),
                                               self._x3d_var.get()),
                self._swept_pretty_to_wire.get(self._y3d_var.get(),
                                               self._y3d_var.get()),
            },
            on_layout_changed=lambda: self._resize_to_content(),
        )
        self._hold_3d.pack(fill="x", padx=theme.PAD_L,
                           pady=(0, theme.PAD_M))

        # Auto-swap: whenever x or y changes to match the other, bump
        # the other one to a different swept variable (silent).
        # Also refresh the 3D hold picker on any axis change.
        self._x3d_var.trace_add(
            "write",
            lambda *_: (self._enforce_3d_distinct("x"),
                        self._hold_3d.refresh_picker_options()),
        )
        self._y3d_var.trace_add(
            "write",
            lambda *_: (self._enforce_3d_distinct("y"),
                        self._hold_3d.refresh_picker_options()),
        )

        if not self._enable_3d:
            self._set_3d_row_enabled(False)

        # Pack the footer LAST so it sits directly under row3d instead
        # of at the fixed bottom of the window.
        self._footer.pack(fill="x", padx=theme.PAD_L,
                          pady=theme.PAD_M)

        # Size the window to its natural content on first show.
        self.after_idle(self._resize_to_content)

    def _resize_to_content(self) -> None:
        """Shrink-wrap the window height to whatever the packed content
        currently needs.  Called on first show and again whenever a
        hold row is added or removed."""
        try:
            self.update_idletasks()
            w = max(760, self.winfo_reqwidth())
            h = self.winfo_reqheight()
            self.geometry(f"{w}x{h}")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _labeled_option(self, parent, label_text, variable, values,
                        width=200, padx=(0, 0)):
        col = ctk.CTkFrame(parent, fg_color="transparent")
        col.pack(side="left", padx=padx)
        ctk.CTkLabel(col, text=label_text, anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_SMALL),
                     text_color=theme.TEXT_MUTED,
                     ).pack(anchor="w")
        menu = ctk.CTkOptionMenu(
            col, variable=variable, values=values or [""],
            dynamic_resizing=False, width=width,
        )
        menu.pack()
        return menu

    def _install_header_filter(self, var: ctk.StringVar) -> None:
        """Trace the variable so if the user picks a header row, we
        silently restore the previous non-header value."""
        state = {"last": var.get(), "guard": False}

        def _filter(*_):
            if state["guard"]:
                return
            new_val = var.get()
            if _is_header(new_val):
                state["guard"] = True
                try:
                    var.set(state["last"])
                finally:
                    state["guard"] = False
            else:
                state["last"] = new_val

        var.trace_add("write", _filter)

    def _set_3d_row_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        try:
            self._3d_check.configure(state=state)
            self._z3d_menu.configure(state=state)
            self._x3d_menu.configure(state=state)
            self._y3d_menu.configure(state=state)
        except Exception:
            pass

    def _enforce_3d_distinct(self, just_changed: str) -> None:
        """Silently swap the OTHER axis's variable if x and y collide."""
        if not self._enable_3d:
            return
        x = self._x3d_var.get()
        y = self._y3d_var.get()
        if x != y:
            return
        options = [p for p in self._swept_pretty_to_wire.keys() if p != x]
        if not options:
            return
        replacement = options[0]
        if just_changed == "x":
            self._y3d_var.set(replacement)
        else:
            self._x3d_var.set(replacement)

    # ------------------------------------------------------------------
    # Show
    # ------------------------------------------------------------------

    def _on_show_click(self) -> None:
        spec_2d = None
        if self._enable_2d_var.get():
            spec_2d = {
                "x": self._swept_pretty_to_wire.get(self._x2d_var.get(),
                                                    self._x2d_var.get()),
                "y": self._output_pretty_to_wire.get(self._y2d_var.get(),
                                                     self._y2d_var.get()),
                "holds": self._hold_2d.get_holds_si(),
            }

        spec_3d = None
        if self._enable_3d and self._enable_3d_var.get():
            spec_3d = {
                "x": self._swept_pretty_to_wire.get(self._x3d_var.get(),
                                                    self._x3d_var.get()),
                "y": self._swept_pretty_to_wire.get(self._y3d_var.get(),
                                                    self._y3d_var.get()),
                "z": self._output_pretty_to_wire.get(self._z3d_var.get(),
                                                     self._z3d_var.get()),
                "holds": self._hold_3d.get_holds_si(),
            }

        self.destroy()
        try:
            self._on_confirm(spec_2d, spec_3d)
        except Exception:
            import traceback
            traceback.print_exc()
