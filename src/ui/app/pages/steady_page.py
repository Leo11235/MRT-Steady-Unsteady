"""
Steady simulation page.

Changes vs. the previous iteration:

  - Pretty display names in the simulation-type dropdown and parametric picker
    (round-tripped via src.ui.app.display).
  - Unit dropdowns on every numeric field that has a unit (length / pressure /
    mass / mass-flow / density / angle).  Internal storage stays SI.
  - Oxidizer & Fuel and Rocket Body sections have NO pre-filled values; only
    the Advanced subsection (chemistry & regression law) is pre-filled.
  - Reset-to-defaults button removed.
  - Sim-type-driven visibility:
      * hotfire           → hide every Rocket Body field, show a placeholder.
      * parametric_study  → show the parametric list; remove any variable
                            from its tab while it is parametrized.
  - Lock icon (🔒 / 🔓) next to the Advanced section title.  Click toggles.
  - default_output_units initial value comes from user_settings.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.ui.app import theme, backend_bridge, settings as user_settings
from src.ui.app import display as display_mod
from src.ui.app.widgets.form_field import LabeledField
from src.ui.app.widgets.parametric_list import ParametricList


# --------------------------------------------------------------------------
# Defaults
#
# By design ONLY the Advanced (propellant chemistry & regression law) fields
# are pre-filled.  Everything else starts blank.
# --------------------------------------------------------------------------

_ADVANCED_DEFAULTS = {
    "fuel_grain_density":                   900,
    "regression_rate_scaling_coefficient":  0.000132,
    "regression_rate_exponent":             0.555,
    "liquid_oxidizer_type":                 "NITROUS OXIDE",
    "solid_fuel_type":                      "EICOSANE (PARAFFIN)",
}

SIM_TYPES_WIRE = ("hotfire", "fuel_mass_convergence", "parametric_study")
OUTPUT_UNITS   = ("SI", "MRT", "IMP")


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------

class SteadyPage(ctk.CTkFrame):
    TITLE = "Steady simulation"

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate

        # Field registry: key = rocket_inputs JSON key, value = LabeledField.
        # Also: which tab the field's row is currently packed into, so we can
        # pack_forget / pack it back without losing its position.
        self.fields: dict[str, LabeledField] = {}

        # Top-level form state
        # — sim_type stored in WIRE form internally
        self.sim_type_var = ctk.StringVar(value="fuel_mass_convergence")
        self.output_units_var = ctk.StringVar(
            value=user_settings.get("default_output_units", "SI"),
        )
        self.save_data_var = ctk.BooleanVar(value=True)
        self.sim_name_var = ctk.StringVar(value="")

        # Preset tracking: when the user has loaded (or just saved) a preset,
        # we remember which file it was and what the config dict looked like
        # right after.  If the form is then run without any further edits,
        # we reuse that file instead of writing a fresh _ui_run_*.jsonc.
        self._loaded_preset_path: Path | None = None
        self._loaded_cfg_snapshot: dict | None = None

        # "Auto-save inputs as new preset" — when on, every Run also stamps
        # out a properly-named preset file rather than a temp one.  Default
        # ON so runs are traceable out of the box; user can uncheck it if
        # they're iterating rapidly and don't want the files.
        self.auto_save_var = ctk.BooleanVar(value=True)

        # Visibility-control state
        self._rocket_body_fields: list[str] = []  # keys whose widgets sit on Rocket Body tab
        self._rocket_body_placeholder = None

        # Advanced-section lock state
        self._advanced_locked = ctk.BooleanVar(value=True)
        self._advanced_fields: list[str] = []
        self._lock_btn = None

        self._build()
        self._capture_build_order()       # snapshot pack order for restoration

        # Initial visibility pass
        self.sim_type_var.trace_add("write", lambda *_: self._refresh_visibility())
        self._apply_advanced_lock()
        self._refresh_visibility()

    # ===================================================================
    # Layout
    # ===================================================================

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=200)
        self.grid_rowconfigure(0, weight=1)

        self.tabs = ctk.CTkTabview(self, anchor="w")
        self.tabs.grid(row=0, column=0, sticky="nsew",
                       padx=(theme.PAD_M, theme.PAD_S), pady=theme.PAD_M)

        sim_tab    = self.tabs.add("Sim Settings")
        oxfuel_tab = self.tabs.add("Oxidizer & Fuel")
        body_tab   = self.tabs.add("Rocket Body")

        self._build_sim_tab(sim_tab)
        self._build_oxfuel_tab(oxfuel_tab)
        self._build_body_tab(body_tab)

        # Sidebar
        sidebar = ctk.CTkFrame(self, fg_color="transparent")
        sidebar.grid(row=0, column=1, sticky="ns",
                     padx=(theme.PAD_S, theme.PAD_M), pady=theme.PAD_M)
        self._build_sidebar(sidebar)

        # Bottom status line
        self.status_label = ctk.CTkLabel(
            self, text="", anchor="w",
            text_color=("gray35", "gray65"),
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
        )
        self.status_label.grid(row=1, column=0, columnspan=2, sticky="ew",
                               padx=theme.PAD_M, pady=(0, theme.PAD_S))

    # -------------------------------------------------------------------
    # Sim Settings tab
    # -------------------------------------------------------------------

    def _build_sim_tab(self, parent) -> None:
        wrap = ctk.CTkScrollableFrame(parent, label_text="")
        wrap.pack(fill="both", expand=True)

        # --- header --------------------------------------------------------
        self._section_title(wrap, "Simulation")

        # Simulation name
        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text="Simulation name", width=220, anchor="w") \
            .pack(side="left", padx=(0, theme.PAD_S))
        ctk.CTkEntry(row, textvariable=self.sim_name_var,
                     placeholder_text="(optional; used for the saved file name)") \
            .pack(side="left", fill="x", expand=True)

        # Simulation type — pretty display, wire-form storage
        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text="Simulation type", width=220, anchor="w") \
            .pack(side="left", padx=(0, theme.PAD_S))

        self._sim_type_display_var = ctk.StringVar(
            value=display_mod.SIM_TYPE_DISPLAY[self.sim_type_var.get()],
        )
        ctk.CTkOptionMenu(
            row, variable=self._sim_type_display_var,
            values=[display_mod.SIM_TYPE_DISPLAY[k] for k in SIM_TYPES_WIRE],
            command=self._on_sim_type_display_changed,
            dynamic_resizing=False, width=260,
        ).pack(side="left")

        # Output units
        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text="Output units", width=220, anchor="w") \
            .pack(side="left", padx=(0, theme.PAD_S))
        ctk.CTkOptionMenu(row, variable=self.output_units_var,
                          values=list(OUTPUT_UNITS),
                          dynamic_resizing=False, width=260) \
            .pack(side="left")

        # Save data
        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkCheckBox(row, text="Save simulation data to JSON",
                        variable=self.save_data_var) \
            .pack(side="left")

        # --- parametric study section ---------------------------------------
        self._divider(wrap)
        self._parametric_section = ctk.CTkFrame(wrap, fg_color="transparent")
        self._parametric_section.pack(fill="x", pady=(theme.PAD_S, 0))

        self._section_title(self._parametric_section, "Parametric Study Settings")
        ctk.CTkLabel(
            self._parametric_section,
            text="Add one or more variables to sweep; each is given a low/high/step. "
                 "Parametrized variables are hidden from the other tabs so you can't "
                 "set them to a single value at the same time.",
            anchor="w", justify="left",
            text_color=("gray35", "gray65"),
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
            wraplength=820,
        ).pack(fill="x", pady=(0, theme.PAD_S))

        self.parametric_list = ParametricList(
            self._parametric_section,
            on_change=self._refresh_visibility,
        )
        self.parametric_list.pack(fill="x", pady=(0, theme.PAD_S))

    # -------------------------------------------------------------------
    # Oxidizer & Fuel tab
    # -------------------------------------------------------------------

    def _build_oxfuel_tab(self, parent) -> None:
        wrap = ctk.CTkScrollableFrame(parent, label_text="")
        wrap.pack(fill="both", expand=True)

        self._section_title(wrap, "Combustion")
        self._add_field(wrap, "oxidizer_mass_flow_rate",
                        label="Oxidizer mass flow rate",
                        kind="mass_flow",
                        required=True, numeric=True)
        self._add_field(wrap, "chamber_pressure",
                        label="Chamber pressure",
                        kind="pressure",
                        required=True, numeric=True)

        self._divider(wrap)
        self._section_title(wrap, "Fuel grain geometry")
        self._add_field(wrap, "fuel_external_radius",
                        label="Fuel external radius",
                        kind="length",
                        required=True, numeric=True)
        self._add_field(wrap, "fuel_length",
                        label="Fuel length",
                        kind="length",
                        required=True, numeric=True)

        # Hotfire-only sub-frame (one container so we can show/hide it as a
        # unit, preserving the internal order on every toggle).
        self._hotfire_only_section = ctk.CTkFrame(wrap, fg_color="transparent")
        # NOT packed initially — _refresh_visibility will pack it when hotfire.
        self._add_field(self._hotfire_only_section, "initial_internal_fuel_radius",
                        label="Initial internal fuel radius",
                        kind="length",
                        numeric=True)
        ctk.CTkLabel(
            self._hotfire_only_section,
            text="(only used for hotfire — the other modes solve for it.)",
            anchor="w",
            text_color=("gray35", "gray65"),
            font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
            wraplength=820,
        ).pack(fill="x", padx=(220 + theme.PAD_S, 0), pady=(0, theme.PAD_S))

        # ---- Advanced section (with lock icon) ---------------------------
        self._divider(wrap)
        self._build_advanced_header(wrap)

        for key, default in _ADVANCED_DEFAULTS.items():
            field = self._add_field(
                wrap, key,
                label=_PRETTY_FIELD_LABELS.get(key, key),
                kind=display_mod.field_kind(key),
                default=str(default) if default is not None else "",
                numeric=isinstance(default, (int, float)),
            )
            self._advanced_fields.append(key)

    def _build_advanced_header(self, parent) -> None:
        # Give the row a fixed height so all three children get a consistent
        # vertical-center.  We pad the labels' heights to match the lock
        # button so nothing gets cropped.
        ROW_H = 32
        row = ctk.CTkFrame(parent, fg_color="transparent", height=ROW_H)
        row.pack(fill="x", pady=(theme.PAD_S, theme.PAD_XS))
        row.pack_propagate(False)  # honour our explicit height

        ctk.CTkLabel(
            row,
            text="Advanced (propellant chemistry & regression law)",
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            anchor="w",
            height=ROW_H,
        ).pack(side="left")

        # 🔒/🔓 clickable label — sized to match the row height so it
        # sits on the same baseline as the surrounding text.
        self._lock_btn = ctk.CTkButton(
            row,
            text="🔒",
            width=32, height=ROW_H,
            corner_radius=6,
            fg_color="transparent",
            hover_color=("gray85", "gray25"),
            command=self._toggle_advanced_lock,
        )
        self._lock_btn.pack(side="left", padx=(theme.PAD_S, 0))

        # "click to edit" — explicit height + width avoids the
        # font-padding-cropping-the-t bug.
        ctk.CTkLabel(
            row,
            text="click to edit",
            font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
            text_color=("gray45", "gray60"),
            height=ROW_H,
            width=85,
            anchor="w",
        ).pack(side="left", padx=(theme.PAD_XS, 0))

    # -------------------------------------------------------------------
    # Rocket Body tab
    # -------------------------------------------------------------------

    def _build_body_tab(self, parent) -> None:
        wrap = ctk.CTkScrollableFrame(parent, label_text="")
        wrap.pack(fill="both", expand=True)
        self._rocket_body_wrap = wrap

        # Wrapper-frame pattern: keep all the actual content inside one inner
        # frame so we can pack_forget the whole subtree (preserving the
        # internal order) when sim_type is hotfire.
        self._rocket_body_content = ctk.CTkFrame(wrap, fg_color="transparent")
        self._rocket_body_content.pack(fill="x")
        content = self._rocket_body_content

        # Placeholder shown when sim_type is hotfire (in the SAME wrap).
        self._rocket_body_placeholder = ctk.CTkLabel(
            wrap,
            text="Rocket Body inputs aren't used for a Hotfire simulation.",
            font=ctk.CTkFont(size=theme.SIZE_H2),
            text_color=("gray45", "gray60"),
            wraplength=600,
            justify="center",
        )
        # built but not packed yet — _refresh_visibility manages it

        self._section_title(content, "Rocket")
        self._add_field(content, "rocket_name",
                        label="Rocket name", placeholder="(optional)")
        self._add_field(content, "dry_mass",
                        label="Dry mass", kind="mass",
                        required=True, numeric=True)
        self._add_field(content, "rocket_external_radius",
                        label="Rocket external radius", kind="length",
                        required=True, numeric=True)
        self._add_field(content, "drag_coefficient",
                        label="Drag coefficient",
                        required=True, numeric=True)

        self._divider(content)
        self._section_title(content, "Mission")
        self._add_field(content, "target_apogee",
                        label="Target apogee", kind="length",
                        required=True, numeric=True)
        self._add_field(content, "launch_site_altitude",
                        label="Launch site altitude", kind="length",
                        required=True, numeric=True)
        self._add_field(content, "launch_angle",
                        label="Launch angle (from vertical)", kind="angle",
                        required=True, numeric=True)

        # Track which fields live on the Rocket Body tab so the parametric
        # mode knows which ones to hide when they're being swept.
        self._rocket_body_fields = [
            "rocket_name", "dry_mass", "rocket_external_radius", "drag_coefficient",
            "target_apogee", "launch_site_altitude", "launch_angle",
        ]

    # -------------------------------------------------------------------
    # Sidebar
    # -------------------------------------------------------------------

    def _build_sidebar(self, parent) -> None:
        ctk.CTkLabel(parent, text="Actions",
                     font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
                     anchor="w").pack(fill="x", pady=(0, theme.PAD_S))

        ctk.CTkButton(parent, text="Load preset…", width=180, height=36,
                      command=self._on_load_preset).pack(pady=theme.PAD_XS)

        ctk.CTkButton(parent, text="Save preset…", width=180, height=36,
                      command=self._on_save_preset).pack(pady=theme.PAD_XS)

        ctk.CTkButton(parent, text="Run simulation", width=180, height=44,
                      font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
                      fg_color=("#2a9d8f", "#2a9d8f"),
                      hover_color=("#21867a", "#21867a"),
                      command=self._on_run).pack(pady=(theme.PAD_M, theme.PAD_XS))

        ctk.CTkCheckBox(parent,
                        text="Auto-save inputs\nas new preset",
                        variable=self.auto_save_var) \
            .pack(pady=(theme.PAD_S, 0))

    # -------------------------------------------------------------------
    # Builder helpers
    # -------------------------------------------------------------------

    def _section_title(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent, text=text, anchor="w",
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
        ).pack(fill="x", pady=(theme.PAD_S, theme.PAD_XS))

    def _divider(self, parent) -> None:
        ctk.CTkFrame(parent, height=1, fg_color=("gray75", "gray30")) \
            .pack(fill="x", pady=theme.PAD_S)

    def _add_field(self, parent, key: str, **kwargs) -> LabeledField:
        # Snake-case keys get a friendly default label if not overridden
        kwargs.setdefault("label", _PRETTY_FIELD_LABELS.get(key, key))
        # kind defaults to the registered FIELD_KIND
        kwargs.setdefault("kind", display_mod.field_kind(key))
        field = LabeledField(parent, **kwargs)
        field.pack(fill="x", pady=theme.PAD_XS)
        self.fields[key] = field
        return field

    # ===================================================================
    # Conditional visibility
    # ===================================================================

    def _on_sim_type_display_changed(self, display_value: str) -> None:
        wire = display_mod.SIM_TYPE_VALUE.get(display_value, display_value)
        self.sim_type_var.set(wire)
        # the trace on sim_type_var fires _refresh_visibility

    def _refresh_visibility(self) -> None:
        sim_type = self.sim_type_var.get()
        hotfire  = (sim_type == "hotfire")
        param    = (sim_type == "parametric_study")

        # 1) Parametric Settings section appears only in parametric mode
        if self._parametric_section is not None:
            self._set_packed(self._parametric_section, param,
                             pack_kwargs={"fill": "x",
                                          "pady": (theme.PAD_S, 0)})

        # 2) Hotfire-only sub-frame (initial_internal_fuel_radius + note)
        self._set_packed(self._hotfire_only_section, hotfire,
                         pack_kwargs={"fill": "x"})

        # 3) Rocket Body tab — swap between the real content frame and the
        #    "not used for hotfire" placeholder.  Wrapping in a single inner
        #    frame preserves the internal order across toggles (no reordering
        #    of fields when you go hotfire → fuel_mass_convergence and back).
        self._set_packed(self._rocket_body_content, not hotfire,
                         pack_kwargs={"fill": "x"})
        self._set_packed(self._rocket_body_placeholder, hotfire,
                         pack_kwargs={"pady": theme.PAD_XL,
                                      "padx": theme.PAD_L,
                                      "fill": "x"})

        # 4) Parametrized variables disappear from their static tab.
        #    Restoration uses _show_field_in_order so they re-appear in
        #    their original position rather than at the bottom of the tab.
        parametrized = set(self.parametric_list.used_vars()) if param else set()
        for key, field in self.fields.items():
            if key in parametrized:
                self._set_packed(field, False)
            else:
                # Skip fields whose tab-level container is currently hidden
                # (parent frame manages those; don't second-guess it).
                parent = field.master
                if parent is self._rocket_body_content and hotfire:
                    continue
                if parent is self._hotfire_only_section and not hotfire:
                    continue
                # Restore in original position (in case it was previously
                # parametric-hidden).
                if field.winfo_manager() != "pack":
                    self._show_in_order(field)

    def _show_in_order(self, widget,
                       pack_kwargs: dict | None = None) -> None:
        """
        Pack `widget` at its original position relative to its siblings.

        We snapshot the pack order of every parent at build time
        (_capture_build_order); when restoring, we look up the next sibling
        that's still packed and use `pack(before=...)`.  Falls back to
        plain pack() if no anchor is found.
        """
        pack_kwargs = pack_kwargs or {"fill": "x", "pady": theme.PAD_XS}
        siblings = self._build_order.get(widget.master, [])
        if widget in siblings:
            idx = siblings.index(widget)
            for sib in siblings[idx + 1:]:
                try:
                    if sib.winfo_manager() == "pack":
                        widget.pack(before=sib, **pack_kwargs)
                        return
                except Exception:
                    continue
        widget.pack(**pack_kwargs)

    def _capture_build_order(self) -> None:
        """Snapshot child order of every parent that hosts toggle-able widgets."""
        self._build_order = {}

        # Parents we must track: each toggleable widget's master + every
        # field's master.  Sets deduplicate.
        parents = set()
        for w in (self._parametric_section,
                  self._hotfire_only_section,
                  self._rocket_body_content,
                  self._rocket_body_placeholder):
            if w is not None:
                parents.add(w.master)
        for field in self.fields.values():
            parents.add(field.master)
        # The inner content frames of the wrappers also matter — they hold
        # the actual fields whose order we want to preserve.
        for parent in (self._rocket_body_content, self._hotfire_only_section):
            if parent is not None:
                parents.add(parent)

        for parent in parents:
            if parent is not None:
                self._build_order[parent] = list(parent.winfo_children())

    def _set_packed(self, widget, want_visible: bool,
                    pack_kwargs: dict | None = None) -> None:
        # NOTE: we deliberately check `winfo_manager()` instead of
        # `winfo_ismapped()`.  Widgets on an inactive CTkTabview tab are
        # technically NOT mapped (the tabview hides them), so
        # winfo_ismapped() returns False and we'd skip the pack_forget,
        # leaving the widgets visible when the tab is later activated.
        try:
            is_managed = (widget.winfo_manager() == "pack")
        except Exception:
            return
        if want_visible and not is_managed:
            # Use the build-order helper so widgets re-appear in their
            # original position (otherwise pack() appends to the end of the
            # parent — and the hotfire-only section would end up below
            # Advanced instead of inside Fuel grain geometry).
            self._show_in_order(widget, pack_kwargs)
        elif not want_visible and is_managed:
            widget.pack_forget()

    # ===================================================================
    # Advanced section lock
    # ===================================================================

    def _toggle_advanced_lock(self) -> None:
        self._advanced_locked.set(not self._advanced_locked.get())
        self._apply_advanced_lock()

    def _apply_advanced_lock(self) -> None:
        locked = self._advanced_locked.get()
        if self._lock_btn is not None:
            self._lock_btn.configure(text="🔒" if locked else "🔓")
        for key in self._advanced_fields:
            f = self.fields.get(key)
            if f is not None:
                f.set_locked(locked)

    # ===================================================================
    # Serialization
    # ===================================================================

    def to_config(self) -> dict:
        sim_settings: dict = {
            "simulation_type":  self.sim_type_var.get(),
            "output_units":     self.output_units_var.get(),
            "save_output_data": bool(self.save_data_var.get()),
        }
        if self.sim_type_var.get() == "parametric_study":
            sim_settings["parametric_study_settings"] = self.parametric_list.to_dict()
        if self.sim_name_var.get().strip():
            sim_settings["simulation_name"] = self.sim_name_var.get().strip()

        rocket_inputs: dict = {}
        parametrized = (
            set(self.parametric_list.used_vars())
            if self.sim_type_var.get() == "parametric_study" else set()
        )
        for key, field in self.fields.items():
            # Skip values that are parametrized (those live in sim_settings)
            if key in parametrized:
                continue
            # Skip hotfire-only field if not hotfire
            if (key == "initial_internal_fuel_radius"
                    and self.sim_type_var.get() != "hotfire"):
                continue
            # Skip Rocket Body fields entirely when hotfire
            if (self.sim_type_var.get() == "hotfire"
                    and key in self._rocket_body_fields):
                continue
            value = field.get_internal()
            if value is None or value == "":
                continue
            rocket_inputs[key] = value

        return {
            "simulation_settings": sim_settings,
            "rocket_inputs": rocket_inputs,
        }

    def from_config(self, cfg: dict) -> None:
        sim = cfg.get("simulation_settings", {}) or {}
        ri  = cfg.get("rocket_inputs", {}) or {}

        st = sim.get("simulation_type")
        if st in SIM_TYPES_WIRE:
            self.sim_type_var.set(st)
            self._sim_type_display_var.set(display_mod.SIM_TYPE_DISPLAY[st])
        ou = sim.get("output_units")
        if ou in OUTPUT_UNITS:
            self.output_units_var.set(ou)
        if "save_output_data" in sim:
            self.save_data_var.set(bool(sim["save_output_data"]))
        if "simulation_name" in sim:
            self.sim_name_var.set(str(sim["simulation_name"]))

        ps = sim.get("parametric_study_settings", {}) or {}
        self.parametric_list.from_dict(ps)

        # populate every known field; clear ones that aren't in the config so
        # we don't keep stale values from a previous preset.
        for key, field in self.fields.items():
            if key in ri:
                field.set_from_internal(ri[key])
            else:
                # Advanced fields fall back to their default; everything else clears
                if key in _ADVANCED_DEFAULTS:
                    field.set(str(_ADVANCED_DEFAULTS[key]))
                else:
                    field.set("")

        self._refresh_visibility()

    # ===================================================================
    # Actions
    # ===================================================================

    def _on_load_preset(self) -> None:
        d = backend_bridge.steady_presets_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = filedialog.askopenfilename(
            initialdir=str(d),
            title="Load steady preset",
            filetypes=[("Steady configs", "*.jsonc *.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            cfg = backend_bridge.load_jsonc(Path(path))
            self.from_config(cfg)
            # Track the loaded preset so Run can reuse this file unchanged.
            # We snapshot via to_config() (post-form-round-trip) so a later
            # comparison isn't tripped up by JSON-vs-Python type quirks.
            self._loaded_preset_path = Path(path)
            self._loaded_cfg_snapshot = self.to_config()
            self._set_status(f"Loaded preset: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("Could not load preset",
                                 f"{type(exc).__name__}: {exc}")

    def _on_save_preset(self) -> None:
        cfg = self.to_config()
        errors = backend_bridge.validate_steady_config(cfg)
        if errors:
            self._highlight_invalid_fields(cfg)
            messagebox.showwarning(
                "Missing required fields",
                "Please fix the following before saving:\n\n• "
                + "\n• ".join(errors),
            )
            return

        d = backend_bridge.steady_presets_dir()
        d.mkdir(parents=True, exist_ok=True)
        default_name = self._default_save_name(cfg)
        path = filedialog.asksaveasfilename(
            initialdir=str(d),
            initialfile=default_name,
            title="Save steady preset",
            defaultextension=".jsonc",
            filetypes=[("Steady configs", "*.jsonc *.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            backend_bridge.save_jsonc(Path(path), cfg)
            # Treat the saved file as the "loaded" preset so subsequent
            # runs reuse it.
            self._loaded_preset_path = Path(path)
            self._loaded_cfg_snapshot = cfg
            self._set_status(f"Saved preset: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("Could not save preset",
                                 f"{type(exc).__name__}: {exc}")

    def _on_run(self) -> None:
        cfg = self.to_config()
        errors = backend_bridge.validate_steady_config(cfg)
        if errors:
            self._highlight_invalid_fields(cfg)
            messagebox.showwarning(
                "Cannot run simulation",
                "Please fix the following before running:\n\n• "
                + "\n• ".join(errors),
            )
            return

        # Decide whether to reuse an existing preset file or write a new one.
        config_file_path = self._pick_config_path_for_run(cfg)

        # Route through the loading screen: it owns the worker thread,
        # captures stdout for the terminal display, and animates the
        # rocket bar.
        shell = self.winfo_toplevel()
        shell.start_loading_run(
            title="Running steady simulation",
            run_fn=lambda: backend_bridge.run_steady(
                cfg, config_file_path=config_file_path,
            ),
            on_complete=self._on_loading_complete,
            # `cfg` baked in via default-arg so the closure doesn't depend
            # on the local scope by the time the worker reports back.
            on_error=lambda exc, tb, cfg=cfg: self._on_loading_error(exc, tb, cfg),
        )

    def _pick_config_path_for_run(self, cfg: dict) -> Path | None:
        """
        Decide what file the simulator should be given:

          - If the form matches the last loaded/saved preset exactly, reuse
            that preset file (no new file is created).
          - Else if "Auto-save inputs as new preset" is on, drop a friendly-
            named preset file and use that.
          - Else return None and let backend_bridge.run_steady write its
            usual temp `_ui_run_*.jsonc`.
        """
        if (self._loaded_preset_path is not None
                and self._loaded_cfg_snapshot == cfg
                and self._loaded_preset_path.exists()):
            return self._loaded_preset_path

        if self.auto_save_var.get():
            try:
                presets = backend_bridge.steady_presets_dir()
                presets.mkdir(parents=True, exist_ok=True)
                # Strip the underscore prefix so it shows up alongside
                # normal user presets, not the hidden `_ui_run_*` ones.
                name = self._default_save_name(cfg)
                path = presets / name
                backend_bridge.save_jsonc(path, cfg)
                # Update tracking so a subsequent identical Run reuses it.
                self._loaded_preset_path = path
                self._loaded_cfg_snapshot = cfg
                self._set_status(f"Auto-saved as {path.name}")
                return path
            except Exception:
                # If auto-save fails for any reason, fall through to temp.
                return None

        return None

    def _on_loading_complete(self, result) -> None:
        """Called by LoadingScreen when the simulation finishes successfully."""
        result_path, result_dict = result
        self._set_status(f"Done. Results saved to {result_path.name}")
        # Navigate to the dedicated results page.
        shell = self.winfo_toplevel()
        try:
            results_page = shell._ensure_page("steady_results")
            results_page.load_results(result_path, result_dict)
            shell.go("steady_results")
        except Exception:
            # Fallback: the old inline modal, in case something went wrong.
            self._show_results_dialog(result_path, result_dict)

    def _on_loading_error(self, exc, tb, cfg) -> None:
        """Called by LoadingScreen on uncaught exceptions in the worker."""
        self._set_status(f"Simulation failed: {type(exc).__name__}")
        self._show_error_popup(exc, tb, cfg)

    # ===================================================================
    # Error popup (shown on simulation failure)
    # ===================================================================

    def _show_error_popup(self, exc: BaseException, tb: str, cfg: dict) -> None:
        shell = self.winfo_toplevel()

        win = ctk.CTkToplevel(self)
        win.title("Simulation error")
        win.geometry("480x230")
        win.transient(shell)
        win.grab_set()
        win.resizable(False, False)

        ctk.CTkLabel(
            win, text="Error during simulation",
            font=ctk.CTkFont(size=theme.SIZE_H1, weight="bold"),
            text_color=theme.MRT_RED_THEMED,
        ).pack(pady=(theme.PAD_L, theme.PAD_S))

        ctk.CTkLabel(
            win,
            text="Please verify all your inputs are correct, and run again.",
            font=ctk.CTkFont(size=theme.SIZE_BODY),
            wraplength=420, justify="center",
        ).pack(pady=(0, theme.PAD_M), padx=theme.PAD_M)

        # Show the exception headline as a small detail line — useful even
        # without opening a bug report.
        ctk.CTkLabel(
            win,
            text=f"{type(exc).__name__}: {exc}",
            text_color=("gray35", "gray65"),
            font=ctk.CTkFont(family="Consolas", size=theme.SIZE_SMALL),
            wraplength=420, justify="center",
        ).pack(pady=(0, theme.PAD_L), padx=theme.PAD_M)

        actions = ctk.CTkFrame(win, fg_color="transparent")
        actions.pack(pady=(0, theme.PAD_M))

        def go_back():
            win.destroy()
            shell.go("steady")

        def go_report():
            win.destroy()
            # Build the prefilled bug-report message
            loading = shell.pages.get("loading")
            terminal_text = (loading.get_terminal_text() if loading is not None
                             else "(terminal output unavailable)")
            try:
                cfg_json = json.dumps(cfg, indent=4)
            except Exception:
                cfg_json = repr(cfg)

            title = f"Error while running steady: {type(exc).__name__}"
            body = (
                "While running steady, the following message stack occurred:\n\n"
                f"{terminal_text}\n\n"
                f"{tb}\n"
                "The following simulation inputs were used:\n\n"
                f"{cfg_json}\n"
            )
            # Lazy-build the bug page if it isn't on screen yet, then prefill.
            try:
                bug_page = shell._ensure_page("bug")
            except Exception:
                bug_page = None
            if bug_page is not None:
                bug_page.prefill(title, body)
            shell.go("bug")

        ctk.CTkButton(
            actions, text="Back to Steady", width=160, height=36,
            command=go_back,
        ).pack(side="left", padx=theme.PAD_S)

        ctk.CTkButton(
            actions, text="Report a bug", width=160, height=36,
            fg_color=theme.MRT_RED_THEMED,
            hover_color=("#7a131a", "#a01a26"),
            command=go_report,
        ).pack(side="left", padx=theme.PAD_S)

    # ===================================================================
    # Results dialog (interim — to be replaced by the dedicated results page)
    # ===================================================================

    def _show_results_dialog(self, result_path: Path, result_dict: dict) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Simulation results")
        win.geometry("640x520")
        win.transient(self.winfo_toplevel())
        win.grab_set()

        ctk.CTkLabel(
            win, text="Simulation finished",
            font=ctk.CTkFont(size=theme.SIZE_H1, weight="bold"),
        ).pack(pady=(theme.PAD_M, theme.PAD_XS))

        ctk.CTkLabel(
            win, text=f"Saved to:  {result_path}",
            text_color=("gray35", "gray65"),
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
            wraplength=600, justify="left", anchor="w",
        ).pack(fill="x", padx=theme.PAD_M, pady=(0, theme.PAD_M))

        body = ctk.CTkTextbox(win, wrap="word",
                              font=ctk.CTkFont(family="Consolas", size=12))
        body.pack(fill="both", expand=True, padx=theme.PAD_M, pady=theme.PAD_S)
        body.insert("0.0", self._format_results(result_dict))
        body.configure(state="disabled")

        footer = ctk.CTkFrame(win, fg_color="transparent")
        footer.pack(fill="x", padx=theme.PAD_M, pady=theme.PAD_M)
        ctk.CTkButton(footer, text="Close", command=win.destroy).pack(side="right")

    def _format_results(self, results: dict) -> str:
        lines: list[str] = []
        sim = results.get("simulation_settings", {}) or {}
        ri  = results.get("rocket_inputs", {}) or {}
        sim_type = (sim.get("simulation_type") or "").lower()

        lines.append(f"Simulation type: "
                     f"{display_mod.SIM_TYPE_DISPLAY.get(sim_type, sim_type)}")
        if "rocket_name" in ri:
            lines.append(f"Rocket: {ri.get('rocket_name')}")
        lines.append("")

        if sim_type == "hotfire":
            _append_performance(lines, results.get("rocket_parameters", {}) or {})

        elif sim_type == "fuel_mass_convergence":
            _append_performance(lines, results.get("rocket_parameters", {}) or {})
            fd = results.get("flight_dict") or {}
            if isinstance(fd, dict) and fd.get("altitude"):
                lines.append("")
                lines.append("Ascent profile:")
                alts = fd["altitude"]
                times = fd.get("time", [])
                lines.append(f"  apogee:          {max(alts):,.1f} m")
                if times:
                    lines.append(f"  time to apogee:  {times[-1]:,.2f} s")

        elif sim_type == "parametric_study":
            pr = results.get("parametric_results") or {}
            combos = pr.get("combinations") if isinstance(pr, dict) else None
            if combos:
                lines.append(f"Parametric study completed: "
                             f"{len(combos)} configurations simulated.")
            rp_list = pr.get("rocket_parameters", []) if isinstance(pr, dict) else []
            if rp_list:
                lines.append("")
                lines.append("First cell:")
                _append_performance(lines, rp_list[0])

        return "\n".join(lines) if lines else "(no result data)"

    # ===================================================================
    # Utilities
    # ===================================================================

    def _default_save_name(self, cfg: dict) -> str:
        sim = cfg.get("simulation_settings", {}) or {}
        ri  = cfg.get("rocket_inputs", {}) or {}
        name = sim.get("simulation_name") or ri.get("rocket_name")
        if name:
            safe = "_".join(str(name).split()).replace("/", "_").replace("\\", "_")
            return f"steady_{safe}.jsonc"
        return f"steady_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.jsonc"

    def _highlight_invalid_fields(self, cfg: dict) -> None:
        ri = cfg.get("rocket_inputs", {}) or {}
        sim_type = (cfg.get("simulation_settings", {}) or {}).get(
            "simulation_type", "").lower()

        required = list(backend_bridge.STEADY_BASE_REQUIRED)
        if sim_type in ("fuel_mass_convergence", "parametric_study"):
            required += list(backend_bridge.STEADY_KINEMATICS_REQUIRED)
        if sim_type == "hotfire":
            if not ri.get("initial_internal_fuel_radius") and not ri.get("fuel_mass"):
                required.append("initial_internal_fuel_radius")

        parametrized = (
            set(self.parametric_list.used_vars())
            if sim_type == "parametric_study" else set()
        )

        for key in required:
            if key in parametrized:
                continue   # parametrized vars don't need a static value
            f = self.fields.get(key)
            if f is not None:
                f.mark_invalid(ri.get(key) in (None, ""))
        for key, field in self.fields.items():
            if key not in required or key in parametrized:
                field.mark_invalid(False)

    def _set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    # ===================================================================
    # Reset — called by the shell when the user hits Home
    # ===================================================================

    def reset_to_defaults(self) -> None:
        """Blow away current inputs and status, restore initial state."""
        # form vars
        self.sim_type_var.set("fuel_mass_convergence")
        self._sim_type_display_var.set(display_mod.SIM_TYPE_DISPLAY["fuel_mass_convergence"])
        self.output_units_var.set(user_settings.get("default_output_units", "SI"))
        self.save_data_var.set(True)
        self.sim_name_var.set("")
        # fields — clear ones that used to be blank; restore Advanced defaults
        for key, field in self.fields.items():
            if key in _ADVANCED_DEFAULTS:
                field.set(str(_ADVANCED_DEFAULTS[key]))
            else:
                field.set("")
            field.mark_invalid(False)
        # parametric list starts empty
        self.parametric_list.clear()
        # advanced section locked
        self._advanced_locked.set(True)
        self._apply_advanced_lock()
        # preset tracking + auto-save
        self._loaded_preset_path = None
        self._loaded_cfg_snapshot = None
        self.auto_save_var.set(True)
        # status
        self._set_status("")
        # visibility refresh (in case sim_type changed)
        self._refresh_visibility()

    # ----- per-show hook (refreshes the output-units initial when settings changed)
    def on_show(self) -> None:
        # If the user opened Settings, changed default_output_units, and came
        # back, only update the dropdown if they haven't already manually
        # overridden it during this session. Simplest rule: only override
        # if it's still set to a stale default.
        wanted = user_settings.get("default_output_units", "SI")
        if wanted in OUTPUT_UNITS and self.output_units_var.get() not in OUTPUT_UNITS:
            self.output_units_var.set(wanted)


# =============================================================================
# Module-level helpers
# =============================================================================

# Friendly labels used by _add_field when the caller doesn't pass `label=`.
_PRETTY_FIELD_LABELS = {
    "rocket_name":                          "Rocket name",
    "oxidizer_mass_flow_rate":              "Oxidizer mass flow rate",
    "chamber_pressure":                     "Chamber pressure",
    "fuel_external_radius":                 "Fuel external radius",
    "fuel_length":                          "Fuel length",
    "initial_internal_fuel_radius":         "Initial internal fuel radius",
    "fuel_grain_density":                   "Fuel grain density",
    "regression_rate_scaling_coefficient":  "Regression coefficient (a)",
    "regression_rate_exponent":             "Regression exponent (n)",
    "liquid_oxidizer_type":                 "Liquid oxidizer type",
    "solid_fuel_type":                      "Solid fuel type",
    "target_apogee":                        "Target apogee",
    "launch_site_altitude":                 "Launch site altitude",
    "dry_mass":                             "Dry mass",
    "rocket_external_radius":               "Rocket external radius",
    "drag_coefficient":                     "Drag coefficient",
    "launch_angle":                         "Launch angle (from vertical)",
}


def _append_performance(lines: list[str], rp: dict) -> None:
    PRETTY = [
        ("thrust",                          "Thrust",              "N",     2),
        ("Isp",                             "Isp",                 "s",     2),
        ("burntime",                        "Burn time",           "s",     3),
        ("total_impulse",                   "Total impulse",       "N·s",   1),
        ("average_oxidizer_to_fuel_ratio",  "Average O/F",         "",      3),
        ("fuel_mass",                       "Fuel mass",           "kg",    3),
        ("nozzle_throat_radius",            "Nozzle throat radius","m",     5),
        ("nozzle_exit_radius",              "Nozzle exit radius",  "m",     5),
        ("wet_mass",                        "Wet mass",            "kg",    2),
        ("thrust_to_weight_ratio",          "Thrust / weight",     "",      2),
        ("reached_apogee",                  "Apogee reached",      "m",     1),
    ]
    lines.append("Performance:")
    for key, label, unit, prec in PRETTY:
        if key in rp and rp[key] is not None:
            try:
                v = float(rp[key])
                u = f" {unit}" if unit else ""
                lines.append(f"  {label:24s} {v:>14,.{prec}f}{u}")
            except (TypeError, ValueError):
                lines.append(f"  {label:24s} {rp[key]}")
