"""
Unsteady simulation page.

Seven tabs:
    Sim Settings | Tank | Valve | Injector | Chamber | Nozzle | Rocket Body

Compared to the Steady page:
  - The config is NESTED (rocket_inputs.CV_inputs.CV1_tank.* etc.) rather than
    flat, so to_config / from_config thread keys through that hierarchy.
  - We pre-fill every field with the template's defaults.  Unsteady has 30+
    inputs and most of them are CV-specific hardware values a user would never
    remember off the top of their head; giving them a working Joel-validation
    starting point is much friendlier than a blank form.
  - Two "either/or" pairs (ullage_fraction OR tank_internal_length_m;
    chamber_fuel_mass_kg OR chamber_fuel_internal_radius_m) are shown as
    side-by-side fields with a small note — the validator catches the case
    where neither is filled.
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


# ============================================================================
# Defaults — mirror unsteady_input_template.jsonc.
# ============================================================================

_DEFAULT_METADATA = {
    "simulation_type": "unsteady",
    "simulation_name": "",
    "warnings":        True,
    "save_to_pdf":     True,
    "save_to_png":     False,
}

# By design, most fields start EMPTY — the user fills in their rocket.
# The only pre-filled values are the chamber's Advanced section (propellant
# chemistry & regression law) which are literature-derived and rarely
# change between rockets.
_DEFAULT_CV_INPUTS = {
    "CV1_tank": {
        "model": "saturated_equilibrium",
        "tank_internal_radius_m":           "",
        "tank_internal_shell_length_m":     "",
        "tank_internal_volume_m3":          "",
        "tank_temperature_K":               "",
        "tank_oxidizer_mass_kg":            "",
        "dip_tube_external_radius_m":       "",
        "dip_tube_internal_radius_m":       "",
        "dip_tube_length_m":                "",
        "tank_ullage_fraction":             "",
        "tank_internal_length_m":           "",
    },
    "CV2_valve": {
        "model": "sigmoid",
        "valve_time_constant_s": "",
        "sigmoid_half_time_s":   "",
        "sigmoid_steepness":     "",
    },
    "CV3_injector": {
        "model": "SPI",
        "injector_discharge_coefficient": "",
        "injector_number_of_holes":       "",
        "injector_hole_area_m2":          "",
        "feed_pressure_loss_Pa":          "",
    },
    "CV4_chamber": {
        "model": "0D_quasi_steady",
        "chamber_fuel_length_m":                       "",
        "chamber_fuel_external_radius_m":              "",
        "pre_chamber_volume_m3":                       "",
        "post_chamber_volume_m3":                      "",
        "chamber_fuel_mass_kg":                        "",
        "chamber_fuel_internal_radius_m":              "",
        # ---- Advanced (locked by default) — see _CHAMBER_ADVANCED --------
        "chamber_fuel_density_kgm3":                   900.0,
        "chamber_regression_rate_scaling_constant":    0.000132,
        "chamber_regression_rate_exponent":            0.555,
    },
    "CV5_nozzle": {
        "model": "1D_frozen",
        "nozzle_throat_radius_m": "",
        "nozzle_exit_radius_m":   "",
    },
    "CV6_trajectory": {
        "model": "2dof",
        "rocket_dry_mass_kg":                       "",
        "rocket_drag_coefficient":                  "",
        "rocket_frontal_area_m2":                   "",
        "rocket_launch_angle_deg":                  "",
        "drogue_parachute_drag_coefficient":        "",
        "drogue_parachute_frontal_area_m2":         "",
        "main_parachute_deployment_altitude_agl_m": "",
        "main_parachute_drag_coefficient":          "",
        "main_parachute_frontal_area_m2":           "",
        "launch_site_altitude_asl_m":               "",
    },
}


# Keys that live inside the Advanced (locked) section of their tab.
# For now only the chamber has one.  The lock icon toggles editability
# of every field in this set on its respective tab.
_CHAMBER_ADVANCED_KEYS = (
    "chamber_fuel_density_kgm3",
    "chamber_regression_rate_scaling_constant",
    "chamber_regression_rate_exponent",
)


OUTPUT_UNITS = ("SI", "MRT", "IMP")


# ============================================================================
# Friendly labels
# ============================================================================

_LABELS = {
    # CV1
    "tank_internal_radius_m":           "Internal radius",
    "tank_internal_shell_length_m":     "Internal shell length",
    "tank_internal_volume_m3":          "Internal volume",
    "tank_temperature_K":               "Initial temperature",
    "tank_oxidizer_mass_kg":            "Oxidizer mass",
    "dip_tube_external_radius_m":       "Dip tube external radius",
    "dip_tube_internal_radius_m":       "Dip tube internal radius",
    "dip_tube_length_m":                "Dip tube length",
    "tank_ullage_fraction":             "Ullage fraction",
    "tank_internal_length_m":           "Internal length",
    # CV2
    "valve_time_constant_s":            "Time constant (linear ramp)",
    "sigmoid_half_time_s":              "Sigmoid t½",
    "sigmoid_steepness":                "Sigmoid steepness",
    # CV3
    "injector_discharge_coefficient":   "Discharge coefficient (Cd)",
    "injector_number_of_holes":         "Number of holes",
    "injector_hole_area_m2":            "Hole area",
    "feed_pressure_loss_Pa":            "Feed pressure loss",
    # CV4
    "chamber_fuel_length_m":                    "Fuel length",
    "chamber_fuel_density_kgm3":                "Fuel density",
    "chamber_fuel_external_radius_m":           "Fuel external radius",
    "chamber_regression_rate_scaling_constant": "Regression coefficient (a)",
    "chamber_regression_rate_exponent":         "Regression exponent (n)",
    "pre_chamber_volume_m3":                    "Pre-chamber volume",
    "post_chamber_volume_m3":                   "Post-chamber volume",
    "chamber_fuel_mass_kg":                     "Fuel mass",
    "chamber_fuel_internal_radius_m":           "Fuel internal radius",
    # CV5
    "nozzle_throat_radius_m":                   "Throat radius",
    "nozzle_exit_radius_m":                     "Exit radius",
    # CV6
    "rocket_dry_mass_kg":                       "Dry mass",
    "rocket_drag_coefficient":                  "Drag coefficient",
    "rocket_frontal_area_m2":                   "Frontal area",
    "rocket_launch_angle_deg":                  "Launch angle (from vertical)",
    "drogue_parachute_drag_coefficient":        "Drogue Cd",
    "drogue_parachute_frontal_area_m2":         "Drogue area",
    "main_parachute_deployment_altitude_agl_m": "Main deploy altitude AGL",
    "main_parachute_drag_coefficient":          "Main Cd",
    "main_parachute_frontal_area_m2":           "Main area",
    "launch_site_altitude_asl_m":               "Launch site altitude ASL",
}


# Whether each field is numeric (controls whether unit-conversion runs)
def _is_numeric(key: str) -> bool:
    """All unsteady fields except text/identifier fields are numeric."""
    return True   # every unsteady-input field happens to be a number


# Per-CV model option lists.  Update these when new physics models land
# in the backend.
_MODEL_OPTIONS = {
    "CV1_tank":       ["saturated_equilibrium"],
    "CV2_valve":      ["linear", "sigmoid"],
    "CV3_injector":   ["SPI"],
    "CV4_chamber":    ["0D_quasi_steady"],
    "CV5_nozzle":     ["1D_frozen"],
    "CV6_trajectory": ["2dof"],
}


# Which fields belong to which (cv, model) pair.  If a (cv, model) isn't
# listed here, every field in that CV's defaults is shown — used for CVs
# whose models all share the same inputs.  When listed, only the named
# fields are visible; the rest are pack_forgotten.
_MODEL_FIELDS: dict[tuple[str, str], set[str]] = {
    ("CV2_valve", "linear"):  {"valve_time_constant_s"},
    ("CV2_valve", "sigmoid"): {"sigmoid_half_time_s", "sigmoid_steepness"},
}


# Pretty display names for physics models.  Keep this in sync with
# _MODEL_OPTIONS; anything missing falls back to a generic title-case.
_MODEL_DISPLAY: dict[str, str] = {
    "saturated_equilibrium": "Saturated equilibrium",
    "linear":                "Linear",
    "sigmoid":               "Sigmoid",
    "SPI":                   "SPI",
    "0D_quasi_steady":       "0D quasi-steady",
    "1D_frozen":             "1D frozen",
    "2dof":                  "2-DOF",
}
_MODEL_WIRE = {v: k for k, v in _MODEL_DISPLAY.items()}


def _model_display(wire: str) -> str:
    """Wire form ('saturated_equilibrium') → pretty form ('Saturated equilibrium')."""
    if wire in _MODEL_DISPLAY:
        return _MODEL_DISPLAY[wire]
    # generic fallback
    return wire.replace("_", " ").capitalize() if wire else wire


def _model_wire(display: str) -> str:
    """Pretty form → wire form."""
    if display in _MODEL_WIRE:
        return _MODEL_WIRE[display]
    return display.replace(" ", "_").lower() if display else display


# Notes that appear immediately ABOVE the named field (rather than at the
# bottom of the tab).  Keyed by (cv_name, field_name) so we can support
# more either/or-style notes later without changing the build loop.
_INLINE_NOTES_BEFORE: dict[tuple[str, str], str] = {
    ("CV1_tank", "tank_ullage_fraction"): (
        "Fill in EITHER 'Ullage fraction' OR 'Internal length' — the "
        "simulator uses whichever is non-empty to size the tank."
    ),
    ("CV4_chamber", "chamber_fuel_mass_kg"): (
        "Fill in EITHER 'Fuel mass' OR 'Fuel internal radius' — "
        "the simulator solves for the other."
    ),
}


# ============================================================================
# Page
# ============================================================================

class UnsteadyPage(ctk.CTkFrame):
    TITLE = "Unsteady simulation"

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate

        # Field registry — keyed by (cv_name, field_name).  cv_name is None
        # for metadata-level fields.
        self.fields: dict[tuple[str | None, str], LabeledField] = {}

        # Per-CV "model" string vars
        self.model_vars: dict[str, ctk.StringVar] = {}

        # Metadata vars
        self.sim_name_var = ctk.StringVar(value=_DEFAULT_METADATA["simulation_name"])
        self.output_units_var = ctk.StringVar(
            value=user_settings.get("default_output_units", "SI"),
        )
        self.warnings_var    = ctk.BooleanVar(value=_DEFAULT_METADATA["warnings"])
        self.save_pdf_var    = ctk.BooleanVar(value=_DEFAULT_METADATA["save_to_pdf"])
        self.save_png_var    = ctk.BooleanVar(value=_DEFAULT_METADATA["save_to_png"])

        # Preset tracking + auto-save (mirrors SteadyPage)
        self._loaded_preset_path: Path | None = None
        self._loaded_cfg_snapshot: dict | None = None
        self.auto_save_var = ctk.BooleanVar(value=True)

        # Chamber's Advanced-section lock (🔒 by default)
        self._advanced_locked = ctk.BooleanVar(value=True)
        self._advanced_fields: list[str] = []      # keys of locked fields
        self._chamber_lock_btn = None

        self._build()
        self._capture_build_order()
        self._apply_advanced_lock()   # lock chamber's Advanced section on startup
        # Wire up model-driven visibility AFTER capturing the original order
        # so _show_in_order has somewhere to look up the right anchor.
        for cv_name, mv in self.model_vars.items():
            mv.trace_add("write",
                         lambda *_, cv=cv_name: self._refresh_model_visibility(cv))
            self._refresh_model_visibility(cv_name)

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
        tank_tab   = self.tabs.add("Tank")
        valve_tab  = self.tabs.add("Valve")
        inj_tab    = self.tabs.add("Injector")
        cham_tab   = self.tabs.add("Chamber")
        noz_tab    = self.tabs.add("Nozzle")
        body_tab   = self.tabs.add("Rocket Body")

        self._build_sim_tab(sim_tab)
        self._build_cv_tab(tank_tab,  "CV1_tank")
        self._build_cv_tab(valve_tab, "CV2_valve")
        self._build_cv_tab(inj_tab,   "CV3_injector")
        self._build_cv_tab(cham_tab,  "CV4_chamber")
        self._build_cv_tab(noz_tab,   "CV5_nozzle")
        self._build_cv_tab(body_tab,  "CV6_trajectory")

        # Sidebar
        sidebar = ctk.CTkFrame(self, fg_color="transparent")
        sidebar.grid(row=0, column=1, sticky="ns",
                     padx=(theme.PAD_S, theme.PAD_M), pady=theme.PAD_M)
        self._build_sidebar(sidebar)

        # Status line
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

        self._section_title(wrap, "Simulation")

        # Simulation name
        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text="Simulation name", width=220, anchor="w") \
            .pack(side="left", padx=(0, theme.PAD_S))
        ctk.CTkEntry(row, textvariable=self.sim_name_var,
                     placeholder_text="(optional; used for the saved file name)") \
            .pack(side="left", fill="x", expand=True)

        # Output units
        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text="Output units", width=220, anchor="w") \
            .pack(side="left", padx=(0, theme.PAD_S))
        ctk.CTkOptionMenu(row, variable=self.output_units_var,
                          values=list(OUTPUT_UNITS),
                          dynamic_resizing=False, width=260) \
            .pack(side="left")

        self._divider(wrap)
        self._section_title(wrap, "Output")
        ctk.CTkCheckBox(wrap, text="Generate warnings report",
                        variable=self.warnings_var).pack(anchor="w", pady=theme.PAD_XS)
        ctk.CTkCheckBox(wrap, text="Save graphs as PDF",
                        variable=self.save_pdf_var).pack(anchor="w", pady=theme.PAD_XS)
        ctk.CTkCheckBox(wrap, text="Save graphs as PNG",
                        variable=self.save_png_var).pack(anchor="w", pady=theme.PAD_XS)

    # -------------------------------------------------------------------
    # Generic CV tab builder
    # -------------------------------------------------------------------

    def _build_cv_tab(self, parent, cv_name: str) -> None:
        """Build a tab for one CV — model dropdown at the top, then every
        field from the defaults dict.  Inline notes (from
        _INLINE_NOTES_BEFORE) appear ABOVE the field they reference."""
        wrap = ctk.CTkScrollableFrame(parent, label_text="")
        wrap.pack(fill="both", expand=True)

        cv_defaults = _DEFAULT_CV_INPUTS[cv_name]

        # ---- model dropdown ------------------------------------------
        self._section_title(wrap, "Model")
        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text="Physics model", width=220, anchor="w") \
            .pack(side="left", padx=(0, theme.PAD_S))

        # Model var stores the PRETTY display string; convert to wire form
        # via _model_wire when serializing to JSONC.
        wire_default = cv_defaults["model"]
        display_default = _model_display(wire_default)
        var = ctk.StringVar(value=display_default)
        self.model_vars[cv_name] = var

        wire_opts = _MODEL_OPTIONS.get(cv_name, [wire_default])
        if wire_default not in wire_opts:
            wire_opts = list(wire_opts) + [wire_default]
        display_opts = [_model_display(w) for w in wire_opts]
        ctk.CTkOptionMenu(row, variable=var, values=display_opts,
                          dynamic_resizing=False, width=260) \
            .pack(side="left")

        self._divider(wrap)
        self._section_title(wrap, "Inputs")

        # For the chamber tab we split the fields into "main" and
        # "advanced" (locked) — the density + regression law only.
        is_chamber = (cv_name == "CV4_chamber")
        advanced_keys = set(_CHAMBER_ADVANCED_KEYS) if is_chamber else set()

        for key, default_value in cv_defaults.items():
            if key == "model" or key in advanced_keys:
                continue
            note = _INLINE_NOTES_BEFORE.get((cv_name, key))
            if note is not None:
                self._note(wrap, note)
            self._add_field(wrap, cv_name, key, default_value)

        # Chamber's Advanced (locked) section
        if is_chamber:
            self._divider(wrap)
            self._build_chamber_advanced_header(wrap)
            for key in _CHAMBER_ADVANCED_KEYS:
                field = self._add_field(wrap, cv_name, key, cv_defaults[key])
                self._advanced_fields.append(key)

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
        ctk.CTkLabel(parent, text=text, anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold")) \
            .pack(fill="x", pady=(theme.PAD_S, theme.PAD_XS))

    def _divider(self, parent) -> None:
        ctk.CTkFrame(parent, height=1, fg_color=("gray75", "gray30")) \
            .pack(fill="x", pady=theme.PAD_S)

    def _build_chamber_advanced_header(self, parent) -> None:
        """The 'Advanced (propellant chemistry & regression law)' header
        with a 🔒/🔓 icon next to it.  Clicking the icon toggles read-only
        state on all fields under this header."""
        ROW_H = 32
        row = ctk.CTkFrame(parent, fg_color="transparent", height=ROW_H)
        row.pack(fill="x", pady=(theme.PAD_S, theme.PAD_XS))
        row.pack_propagate(False)

        ctk.CTkLabel(
            row,
            text="Advanced (propellant chemistry & regression law)",
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            anchor="w", height=ROW_H,
        ).pack(side="left")

        self._chamber_lock_btn = ctk.CTkButton(
            row, text="🔒", width=32, height=ROW_H,
            corner_radius=6, fg_color="transparent",
            hover_color=("gray85", "gray25"),
            command=self._toggle_advanced_lock,
        )
        self._chamber_lock_btn.pack(side="left", padx=(theme.PAD_S, 0))

        ctk.CTkLabel(
            row, text="click to edit",
            font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
            text_color=("gray45", "gray60"),
            height=ROW_H, width=85, anchor="w",
        ).pack(side="left", padx=(theme.PAD_XS, 0))

    def _toggle_advanced_lock(self) -> None:
        self._advanced_locked.set(not self._advanced_locked.get())
        self._apply_advanced_lock()

    def _apply_advanced_lock(self) -> None:
        locked = self._advanced_locked.get()
        if self._chamber_lock_btn is not None:
            self._chamber_lock_btn.configure(text="🔒" if locked else "🔓")
        for key in self._advanced_fields:
            f = self.fields.get(("CV4_chamber", key))
            if f is not None:
                f.set_locked(locked)

    def _note(self, parent, text: str) -> None:
        ctk.CTkLabel(parent, text=text,
                     anchor="w", justify="left",
                     text_color=("gray35", "gray65"),
                     font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
                     wraplength=800) \
            .pack(fill="x", padx=(220 + theme.PAD_S, 0),
                  pady=(theme.PAD_XS, theme.PAD_S))

    def _add_field(self, parent, cv_name: str | None, key: str, default) -> LabeledField:
        label = _LABELS.get(key, key)
        kind  = display_mod.field_kind(key)
        field = LabeledField(
            parent,
            label=label,
            kind=kind,
            default="" if default == "" or default is None else str(default),
            numeric=_is_numeric(key),
            required=False,   # unsteady validation is per-CV, not per-field
        )
        field.pack(fill="x", pady=theme.PAD_XS)
        self.fields[(cv_name, key)] = field
        return field

    # ===================================================================
    # Serialization
    # ===================================================================

    def to_config(self) -> dict:
        """Build the nested config dict the simulator expects."""
        # metadata
        metadata = dict(_DEFAULT_METADATA)
        metadata["simulation_name"] = self.sim_name_var.get().strip()
        metadata["warnings"]    = bool(self.warnings_var.get())
        metadata["save_to_pdf"] = bool(self.save_pdf_var.get())
        metadata["save_to_png"] = bool(self.save_png_var.get())

        # CV inputs
        cv_inputs = {}
        for cv_name in _DEFAULT_CV_INPUTS:
            block: dict = {}
            mv = self.model_vars.get(cv_name)
            current_model = _model_wire(mv.get()) if mv is not None else None
            if current_model is not None:
                block["model"] = current_model
            # Fields hidden by the current model selection are excluded from
            # the saved config — otherwise stale values would leak in.
            visible_filter = _MODEL_FIELDS.get((cv_name, current_model or ""))
            for key in _DEFAULT_CV_INPUTS[cv_name]:
                if key == "model":
                    continue
                if visible_filter is not None and key not in visible_filter:
                    continue
                field = self.fields.get((cv_name, key))
                if field is None:
                    continue
                v = field.get_internal()
                if v is None or v == "":
                    continue
                block[key] = v
            cv_inputs[cv_name] = block

        # output_units lives in simulation_settings_override so the
        # simulator's default-loader merges it.
        sim_settings_override = {"output_units": self.output_units_var.get()}

        return {
            "rocket_inputs": {
                "metadata":  metadata,
                "CV_inputs": cv_inputs,
            },
            "simulation_settings_override": sim_settings_override,
        }

    def from_config(self, cfg: dict) -> None:
        """Populate every widget from a loaded config dict."""
        ri = cfg.get("rocket_inputs", {}) or {}
        meta = ri.get("metadata", {}) or {}
        cvs  = ri.get("CV_inputs", {}) or {}

        # metadata
        self.sim_name_var.set(str(meta.get("simulation_name", "")))
        if "warnings"    in meta: self.warnings_var.set(bool(meta["warnings"]))
        if "save_to_pdf" in meta: self.save_pdf_var.set(bool(meta["save_to_pdf"]))
        if "save_to_png" in meta: self.save_png_var.set(bool(meta["save_to_png"]))

        # output units (looked up from override block, falls back to template)
        ov = cfg.get("simulation_settings_override", {}) or {}
        ou = ov.get("output_units")
        if ou in OUTPUT_UNITS:
            self.output_units_var.set(ou)

        # CVs
        for cv_name, block in cvs.items():
            if not isinstance(block, dict):
                continue
            # model — set it (the trace will re-fire visibility)
            if "model" in block:
                mv = self.model_vars.get(cv_name)
                if mv is not None:
                    mv.set(_model_display(str(block["model"])))
            # fields
            for key, value in block.items():
                if key == "model":
                    continue
                field = self.fields.get((cv_name, key))
                if field is not None:
                    field.set_from_internal(value)

        # Re-apply model visibility now that everything is set.
        for cv_name in self.model_vars:
            self._refresh_model_visibility(cv_name)

    # ===================================================================
    # Model-driven field visibility (currently used by Valve)
    # ===================================================================

    def _capture_build_order(self) -> None:
        """Snapshot the pack order of every parent that holds a field.  Used
        by _show_in_order to re-insert hidden widgets at their original spot."""
        self._build_order: dict = {}
        for field in self.fields.values():
            parent = field.master
            if parent not in self._build_order:
                self._build_order[parent] = list(parent.winfo_children())

    def _show_in_order(self, widget,
                       pack_kwargs: dict | None = None) -> None:
        """Pack `widget` at its original sibling position."""
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

    def _set_packed(self, widget, want_visible: bool,
                    pack_kwargs: dict | None = None) -> None:
        try:
            is_managed = (widget.winfo_manager() == "pack")
        except Exception:
            return
        if want_visible and not is_managed:
            self._show_in_order(widget, pack_kwargs)
        elif not want_visible and is_managed:
            widget.pack_forget()

    def _refresh_model_visibility(self, cv_name: str) -> None:
        """Show/hide fields inside `cv_name`'s tab based on the chosen model."""
        mv = self.model_vars.get(cv_name)
        if mv is None:
            return
        # model_var stores the pretty display string; convert to wire form
        # for the _MODEL_FIELDS lookup.
        model = _model_wire(mv.get())
        visible_set = _MODEL_FIELDS.get((cv_name, model))
        if visible_set is None:
            # No filtering — every field stays visible.
            for key in _DEFAULT_CV_INPUTS[cv_name]:
                if key == "model":
                    continue
                f = self.fields.get((cv_name, key))
                if f is not None:
                    self._set_packed(f, True)
            return
        # Filtered: only show the fields named in visible_set.
        for key in _DEFAULT_CV_INPUTS[cv_name]:
            if key == "model":
                continue
            f = self.fields.get((cv_name, key))
            if f is not None:
                self._set_packed(f, key in visible_set)

    # ===================================================================
    # Actions
    # ===================================================================

    def _on_load_preset(self) -> None:
        d = backend_bridge.unsteady_presets_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = filedialog.askopenfilename(
            initialdir=str(d),
            title="Load unsteady preset",
            filetypes=[("Unsteady configs", "*.jsonc *.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            cfg = backend_bridge.load_jsonc(Path(path))
            self.from_config(cfg)
            self._loaded_preset_path = Path(path)
            self._loaded_cfg_snapshot = self.to_config()
            self._set_status(f"Loaded preset: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("Could not load preset",
                                 f"{type(exc).__name__}: {exc}")

    def _on_save_preset(self) -> None:
        cfg = self.to_config()
        errors = backend_bridge.validate_unsteady_config(cfg)
        if errors:
            messagebox.showwarning(
                "Missing required fields",
                "Please fix the following before saving:\n\n• "
                + "\n• ".join(errors),
            )
            return

        d = backend_bridge.unsteady_presets_dir()
        d.mkdir(parents=True, exist_ok=True)
        default_name = self._default_save_name(cfg)
        path = filedialog.asksaveasfilename(
            initialdir=str(d),
            initialfile=default_name,
            title="Save unsteady preset",
            defaultextension=".jsonc",
            filetypes=[("Unsteady configs", "*.jsonc *.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            backend_bridge.save_jsonc(Path(path), cfg)
            self._loaded_preset_path = Path(path)
            self._loaded_cfg_snapshot = cfg
            self._set_status(f"Saved preset: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("Could not save preset",
                                 f"{type(exc).__name__}: {exc}")

    def _on_run(self) -> None:
        cfg = self.to_config()
        errors = backend_bridge.validate_unsteady_config(cfg)
        if errors:
            messagebox.showwarning(
                "Cannot run simulation",
                "Please fix the following before running:\n\n• "
                + "\n• ".join(errors),
            )
            return

        config_file_path = self._pick_config_path_for_run(cfg)

        shell = self.winfo_toplevel()
        shell.start_loading_run(
            title="Running unsteady simulation",
            run_fn=lambda: backend_bridge.run_unsteady(
                cfg, config_file_path=config_file_path,
            ),
            on_complete=self._on_loading_complete,
            on_error=lambda exc, tb, cfg=cfg: self._on_loading_error(exc, tb, cfg),
        )

    def _pick_config_path_for_run(self, cfg: dict) -> Path | None:
        """Same logic as SteadyPage — reuse the loaded preset if unchanged,
        or auto-save a friendly-named preset when that option is on."""
        if (self._loaded_preset_path is not None
                and self._loaded_cfg_snapshot == cfg
                and self._loaded_preset_path.exists()):
            return self._loaded_preset_path

        if self.auto_save_var.get():
            try:
                presets = backend_bridge.unsteady_presets_dir()
                presets.mkdir(parents=True, exist_ok=True)
                name = self._default_save_name(cfg)
                path = presets / name
                backend_bridge.save_jsonc(path, cfg)
                self._loaded_preset_path = path
                self._loaded_cfg_snapshot = cfg
                self._set_status(f"Auto-saved as {path.name}")
                return path
            except Exception:
                return None

        return None

    def _on_loading_complete(self, result) -> None:
        result_path, result_dict = result
        self._set_status(f"Done. Results saved to {result_path.name}")
        # Navigate to the dedicated results page.
        shell = self.winfo_toplevel()
        try:
            results_page = shell._ensure_page("unsteady_results")
            results_page.load_results(result_path, result_dict)
            shell.go("unsteady_results")
        except Exception as exc:
            messagebox.showerror("Could not display results",
                                 f"{type(exc).__name__}: {exc}")

    def _on_loading_error(self, exc, tb, cfg) -> None:
        self._set_status(f"Simulation failed: {type(exc).__name__}")
        self._show_error_popup(exc, tb, cfg)

    # ===================================================================
    # Error popup (mirrors the one on SteadyPage)
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
            shell.go("unsteady")

        def go_report():
            win.destroy()
            loading = shell.pages.get("loading")
            terminal_text = (loading.get_terminal_text() if loading is not None
                             else "(terminal output unavailable)")
            try:
                cfg_json = json.dumps(cfg, indent=4)
            except Exception:
                cfg_json = repr(cfg)
            title = f"Error while running unsteady: {type(exc).__name__}"
            body = (
                "While running unsteady, the following message stack occurred:\n\n"
                f"{terminal_text}\n\n"
                f"{tb}\n"
                "The following simulation inputs were used:\n\n"
                f"{cfg_json}\n"
            )
            try:
                bug_page = shell._ensure_page("bug")
            except Exception:
                bug_page = None
            if bug_page is not None:
                bug_page.prefill(title, body)
            shell.go("bug")

        ctk.CTkButton(actions, text="Back to Unsteady", width=160, height=36,
                      command=go_back).pack(side="left", padx=theme.PAD_S)
        ctk.CTkButton(actions, text="Report a bug", width=160, height=36,
                      fg_color=theme.MRT_RED_THEMED,
                      hover_color=("#7a131a", "#a01a26"),
                      command=go_report).pack(side="left", padx=theme.PAD_S)

    # ===================================================================
    # Utilities
    # ===================================================================

    def _default_save_name(self, cfg: dict) -> str:
        ri = cfg.get("rocket_inputs", {}) or {}
        meta = ri.get("metadata", {}) or {}
        name = meta.get("simulation_name")
        if name:
            safe = "_".join(str(name).split()).replace("/", "_").replace("\\", "_")
            return f"unsteady_{safe}.jsonc"
        return f"unsteady_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.jsonc"

    def _set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    # ===================================================================
    # Reset — called by the shell when the user hits Home
    # ===================================================================

    def reset_to_defaults(self) -> None:
        """Restore initial state (blank inputs + defaults for Advanced only)."""
        # metadata
        self.sim_name_var.set(_DEFAULT_METADATA["simulation_name"])
        self.output_units_var.set(user_settings.get("default_output_units", "SI"))
        self.warnings_var.set(_DEFAULT_METADATA["warnings"])
        self.save_pdf_var.set(_DEFAULT_METADATA["save_to_pdf"])
        self.save_png_var.set(_DEFAULT_METADATA["save_to_png"])
        # per-CV model back to its template default
        for cv_name, mv in self.model_vars.items():
            mv.set(_model_display(_DEFAULT_CV_INPUTS[cv_name]["model"]))
        # fields
        for (cv_name, key), field in self.fields.items():
            default = _DEFAULT_CV_INPUTS[cv_name].get(key, "")
            field.set("" if default == "" or default is None else str(default))
        # advanced lock re-engaged
        self._advanced_locked.set(True)
        self._apply_advanced_lock()
        # preset tracking + auto-save
        self._loaded_preset_path = None
        self._loaded_cfg_snapshot = None
        self.auto_save_var.set(True)
        # status
        self._set_status("")
        # reapply model-driven visibility (in case model changed)
        for cv_name in self.model_vars:
            self._refresh_model_visibility(cv_name)

    # per-show hook (refreshes the output-units initial when settings changed)
    def on_show(self) -> None:
        wanted = user_settings.get("default_output_units", "SI")
        if wanted in OUTPUT_UNITS and self.output_units_var.get() not in OUTPUT_UNITS:
            self.output_units_var.set(wanted)
