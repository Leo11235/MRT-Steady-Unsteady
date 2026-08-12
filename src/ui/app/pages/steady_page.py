"""
Steady input form.

Three simulation types share one form, with sections appearing and disappearing
as the type changes:

    hotfire               performance at one operating point, no trajectory
    fuel_mass_convergence solves fuel mass until the apogee target is met
    parametric_study      runs a convergence at every point of a sweep

Kinematics only matters once there's a trajectory, so that section hides for
hotfire. The fuel-mass / port-diameter pair is the opposite: only hotfire needs
it, because the other two solve for it.

Which fields exist in each group comes from the backend schema, so adding an
input there makes it appear here without touching this file.
"""

from __future__ import annotations

import customtkinter as ctk

from src.ui.app import backend_bridge, theme
from src.ui.app import field_registry as registry
from src.ui.app.pages.input_page import InputPage
from src.ui.app.widgets.parametric_list import ParametricList
from src.ui.app.widgets.section import CollapsibleSection, note, section_title


SIM_TYPES: dict[str, str] = {
    "hotfire":               "Hotfire",
    "fuel_mass_convergence": "Fuel mass convergence",
    "parametric_study":      "Parametric study",
}
SIM_TYPE_WIRE = {label: wire for wire, label in SIM_TYPES.items()}

OUTPUT_UNIT_SYSTEMS = ("SI", "MRT", "IMP")

_HOTFIRE_ALTERNATES = ("fuel_mass", "initial_internal_fuel_diameter")


class SteadyPage(InputPage):
    TITLE = "Steady simulation"
    KIND = "steady"

    # ==================================================================
    # Layout
    # ==================================================================

    def _build_form(self, parent) -> None:
        schema = registry.steady_schema_keys()

        self._build_settings(parent)
        self._build_base(parent, schema.get("base_requirements", []))
        self._build_kinematics(parent, schema.get("kinematics_requirements", []))
        self._build_hotfire(parent)
        self._build_parametric(parent)

        self._refresh_visibility()

    def _build_settings(self, parent) -> None:
        section_title(parent, "Simulation")

        self.sim_type_var = ctk.StringVar(value=SIM_TYPES["fuel_mass_convergence"])
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text="Simulation type", width=220, anchor="w").pack(
            side="left", padx=(0, theme.PAD_S))
        ctk.CTkOptionMenu(row, values=list(SIM_TYPES.values()),
                          variable=self.sim_type_var,
                          command=lambda _v: self._refresh_visibility(),
                          width=240).pack(side="left")

        self.output_units_var = ctk.StringVar(value="SI")
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text="Output units", width=220, anchor="w").pack(
            side="left", padx=(0, theme.PAD_S))
        ctk.CTkOptionMenu(row, values=list(OUTPUT_UNIT_SYSTEMS),
                          variable=self.output_units_var, width=240).pack(side="left")

        self.name_var = ctk.StringVar()
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text="Run name", width=220, anchor="w").pack(
            side="left", padx=(0, theme.PAD_S))
        ctk.CTkEntry(row, textvariable=self.name_var,
                     placeholder_text="optional; blank uses a timestamp").pack(
            side="left", fill="x", expand=True)

        ctk.CTkLabel(parent, text="Description", anchor="w").pack(
            fill="x", pady=(theme.PAD_S, theme.PAD_XS))
        self.description = ctk.CTkTextbox(parent, height=60, wrap="word")
        self.description.pack(fill="x")

    def _build_base(self, parent, keys) -> None:
        self._base_section = CollapsibleSection(parent, "Motor")
        self._base_section.pack(fill="x", pady=(theme.PAD_M, 0))
        for key in keys:
            self.add_field(self._base_section.body, key)

    def _build_kinematics(self, parent, keys) -> None:
        self._kinematics_section = CollapsibleSection(parent, "Rocket and trajectory")
        self._kinematics_section.pack(fill="x", pady=(theme.PAD_M, 0))
        note(self._kinematics_section.body,
             "Not used by a hotfire, which has no trajectory.", left_pad=0)
        for key in keys:
            self.add_field(self._kinematics_section.body, key)

    def _build_hotfire(self, parent) -> None:
        self._hotfire_section = CollapsibleSection(parent, "Fuel grain (hotfire)")
        self._hotfire_section.pack(fill="x", pady=(theme.PAD_M, 0))
        note(self._hotfire_section.body,
             "Fill exactly one of these. The other is derived from it. "
             "The other simulation types solve for both.", left_pad=0)
        for key in _HOTFIRE_ALTERNATES:
            self.add_field(self._hotfire_section.body, key)

    def _build_parametric(self, parent) -> None:
        self._parametric_section = CollapsibleSection(parent, "Swept variables")
        self._parametric_section.pack(fill="x", pady=(theme.PAD_M, 0))
        note(self._parametric_section.body,
             "Each swept variable runs a full convergence at every point, so "
             "the run time is the product of all the step counts.", left_pad=0)
        self.parametric_list = ParametricList(self._parametric_section.body)
        self.parametric_list.pack(fill="x")

    # ==================================================================
    # Visibility
    # ==================================================================

    @property
    def sim_type(self) -> str:
        return SIM_TYPE_WIRE.get(self.sim_type_var.get(), "fuel_mass_convergence")

    def _refresh_visibility(self) -> None:
        """Show only the sections this simulation type uses."""
        sim_type = self.sim_type
        is_hotfire = sim_type == "hotfire"
        is_parametric = sim_type == "parametric_study"

        def show(section, visible: bool) -> None:
            if visible and not section.winfo_ismapped():
                section.pack(fill="x", pady=(theme.PAD_M, 0))
            elif not visible and section.winfo_ismapped():
                section.pack_forget()

        show(self._kinematics_section, not is_hotfire)
        show(self._hotfire_section, is_hotfire)
        show(self._parametric_section, is_parametric)

    # ==================================================================
    # Serialisation
    # ==================================================================

    def to_config(self) -> dict:
        sim_type = self.sim_type
        swept = set(self.parametric_list.used_vars()) if sim_type == "parametric_study" else set()

        settings: dict = {
            "simulation_type": sim_type,
            "output_units": self.output_units_var.get(),
        }
        if sim_type == "parametric_study":
            settings["parametric_study_settings"] = self.parametric_list.to_dict()

        inputs: dict = {}
        for path, field in self.fields.items():
            key = path.rsplit(".", 1)[-1]
            # A swept variable is supplied per point by the solver, so writing a
            # static value for it would be misleading.
            if key in swept:
                continue
            # Sections the current type hides contribute nothing, otherwise a
            # stale hotfire value would leak into a convergence run.
            if not self._is_key_active(key, sim_type):
                continue
            inputs[key] = field.to_pair()

        return {
            "metadata": {
                "simulation_type": "steady",
                "simulation_name": self.name_var.get().strip(),
                "simulation_description": self.description.get("0.0", "end").strip(),
                "expected_output": "",
            },
            "simulation_settings": settings,
            "rocket_inputs": inputs,
        }

    def _is_key_active(self, key: str, sim_type: str) -> bool:
        """Whether a field belongs in the config for this simulation type."""
        schema = registry.steady_schema_keys()
        if key in _HOTFIRE_ALTERNATES:
            return sim_type == "hotfire"
        if key in schema.get("kinematics_requirements", []):
            return sim_type != "hotfire"
        return True

    def from_config(self, config: dict) -> None:
        settings = config.get("simulation_settings") or {}
        metadata = config.get("metadata") or {}
        inputs = config.get("rocket_inputs") or {}

        wire = settings.get("simulation_type", "fuel_mass_convergence")
        self.sim_type_var.set(SIM_TYPES.get(wire, SIM_TYPES["fuel_mass_convergence"]))

        units = settings.get("output_units", "SI")
        self.output_units_var.set(units if units in OUTPUT_UNIT_SYSTEMS else "SI")

        self.name_var.set(str(metadata.get("simulation_name", "") or ""))
        self.description.delete("0.0", "end")
        self.description.insert("0.0", str(metadata.get("simulation_description", "") or ""))

        # Clear first, so fields absent from this preset don't keep values from
        # whatever was loaded before.
        for path, field in self.fields.items():
            key = path.rsplit(".", 1)[-1]
            if key in inputs:
                field.from_pair(inputs[key])
            else:
                field.reset_to_default()

        self.parametric_list.from_dict(settings.get("parametric_study_settings") or {})
        self._refresh_visibility()

    # ==================================================================
    # Backend
    # ==================================================================

    def _validate(self, config: dict) -> list[str]:
        return backend_bridge.validate_steady_config(config)

    def _preflight(self, config: dict) -> dict:
        return backend_bridge.preflight_steady(config.get("rocket_inputs") or {})

    def _default_run_name(self) -> str:
        return self.name_var.get().strip() or "steady_run"

    def reset_to_defaults(self) -> None:
        super().reset_to_defaults()
        self.name_var.set("")
        self.description.delete("0.0", "end")
        self.sim_type_var.set(SIM_TYPES["fuel_mass_convergence"])
        self.output_units_var.set("SI")
        self.parametric_list.clear()
        self._refresh_visibility()
        self._clean_snapshot = self.to_config()
