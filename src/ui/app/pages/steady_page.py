"""
Steady input form.

Three tabs:

    Sim settings      name, type, save toggle, and the parametric sweep editor
    Oxidizer & fuel   the operating point and grain geometry
    Rocket body       mass, drag and mission, only used when there's a trajectory

Two sections appear conditionally. The hotfire alternates live inside the
Oxidizer & fuel tab and only show for a hotfire, because the other two types
solve for them. The Rocket body tab swaps its whole contents for a short
explanation during a hotfire rather than emptying out, so the tab never looks
broken.

There's no output-units control here. Inputs carry their own unit per field,
and the SI/MRT/IMP choice belongs to the results page where it's actually read.
"""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from src.ui.app import backend_bridge, theme
from src.ui.app import field_registry as registry
from src.ui.app import settings as user_settings
from src.ui.app.pages.input_page import InputPage, VALUE_INDENT
from src.ui.app.widgets.parametric_list import ParametricList


SIM_TYPES: dict[str, str] = {
    "hotfire":               "Hotfire",
    "fuel_mass_convergence": "Fuel mass convergence",
    "parametric_study":      "Parametric study",
}
SIM_TYPE_WIRE = {label: wire for wire, label in SIM_TYPES.items()}

_HOTFIRE_ALTERNATES = ("initial_internal_fuel_diameter", "fuel_mass")

# Inputs with defensible defaults that most runs never touch. Locked behind
# the padlock so changing one is deliberate.
_ADVANCED_KEYS = (
    "fuel_grain_density",
    "regression_rate_scaling_coefficient",
    "regression_rate_exponent",
    "liquid_oxidizer_type",
    "solid_fuel_type",
)


class SteadyPage(InputPage):
    TITLE = "Steady simulation"
    KIND = "steady"

    # ==================================================================
    # Tabs
    # ==================================================================

    def _build_tabs(self) -> None:
        self.sim_name_var = ctk.StringVar()
        self.sim_type_var = ctk.StringVar(value=SIM_TYPES["fuel_mass_convergence"])
        self.output_units_var = ctk.StringVar(
            value=user_settings.get("default_program_units", "SI"))

        self._build_sim_tab(self.add_tab("Sim Settings"))
        self._build_oxfuel_tab(self.add_tab("Oxidizer & Fuel"))
        self._build_body_tab(self.add_tab("Rocket Body"))

    def _after_build(self) -> None:
        self._refresh_visibility()

    # ==================================================================
    # After a run
    # ==================================================================

    def _review_result(self, result) -> bool:
        """Warn when a convergence run never reached the target apogee.

        The run succeeded — it produced a complete result — so nothing else in
        the pipeline flags it, and the results page looks exactly like a
        converged one until you read the apogee. Only convergence runs can
        fail this way: a hotfire has no target, and a parametric study flags
        its failing points individually in the sweep tab.
        """
        if self.sim_type_var.get() != SIM_TYPES["fuel_mass_convergence"]:
            return True

        try:
            results = backend_bridge.load_run(Path(result))
        except Exception:                       # noqa: BLE001
            return True                         # can't tell; don't block

        params = results.get("rocket_parameters") or {}
        if params.get("target_apogee_reached") is not False:
            return True

        from src.ui.app.widgets.apogee_dialog import show_apogee_shortfall
        from src.ui.app.widgets.kv_row import native_system_of

        inputs = results.get("rocket_inputs") or {}
        return show_apogee_shortfall(
            self,
            reached=params.get("reached_apogee"),
            target=inputs.get("target_apogee"),
            system=self.system,
            # The file is in MRT units when the run's output_units said so, so
            # a 45000 ft target is stored as the number 45000. Reading that as
            # metres is exactly the bug this argument exists to prevent.
            native=native_system_of(results),
        )

    def _on_system_changed(self, system: str) -> None:
        """The base class re-presents the plain fields; these two widgets carry
        units of their own and have to be told separately."""
        self.output_units_var.set(system)
        if getattr(self, "parametric_list", None) is not None:
            self.parametric_list.set_system(system)

    # ---- tab 1 --------------------------------------------------------

    def _build_sim_tab(self, wrap) -> None:
        self.add_section_title(wrap, "Simulation")

        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text="Simulation name", width=220, anchor="w").pack(
            side="left", padx=(0, theme.PAD_S))
        ctk.CTkEntry(row, textvariable=self.sim_name_var,
                     placeholder_text="optional; blank uses a timestamp").pack(
            side="left", fill="x", expand=True)

        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text="Simulation type", width=220, anchor="w").pack(
            side="left", padx=(0, theme.PAD_S))
        ctk.CTkOptionMenu(row, variable=self.sim_type_var,
                          values=list(SIM_TYPES.values()),
                          command=lambda _v: self._refresh_visibility(),
                          dynamic_resizing=False, width=260).pack(side="left")

        ctk.CTkLabel(wrap, text="Description", anchor="w").pack(
            fill="x", pady=(theme.PAD_S, theme.PAD_XS))
        self.description = ctk.CTkTextbox(wrap, height=60, wrap="word")
        self.description.pack(fill="x")

        # ---- parametric sweep ----------------------------------------
        self.add_divider(wrap)
        self._parametric_section = ctk.CTkFrame(wrap, fg_color="transparent")
        self._parametric_section.pack(fill="x", pady=(theme.PAD_S, 0))

        self.add_section_title(self._parametric_section, "Parametric Study Settings")
        ctk.CTkLabel(
            self._parametric_section,
            text=("Add one or more variables to sweep; each is given a low/high/step."),
            anchor="w", justify="left", wraplength=820,
            text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
        ).pack(fill="x", pady=(0, theme.PAD_S))

        self.parametric_list = ParametricList(
            self._parametric_section, system=self.system,
            on_change=self._refresh_visibility)
        self.parametric_list.pack(fill="x", pady=(0, theme.PAD_S))

    # ---- tab 2 --------------------------------------------------------

    def _build_oxfuel_tab(self, wrap) -> None:
        self.add_section_title(wrap, "Combustion")
        self.add_field(wrap, "oxidizer_mass_flow_rate")
        self.add_field(wrap, "chamber_pressure")

        self.add_divider(wrap)
        self.add_section_title(wrap, "Fuel geometry")
        self.add_field(wrap, "fuel_external_diameter")
        self.add_field(wrap, "fuel_length")

        # One container for the hotfire-only pair, so it hides and shows as a
        # unit and keeps its internal order across toggles.
        self._hotfire_section = ctk.CTkFrame(wrap, fg_color="transparent")
        # Deliberately not packed; _refresh_visibility owns it.
        ctk.CTkLabel(
            self._hotfire_section,
            text=("Fill in EITHER 'Initial internal fuel diameter' OR 'Fuel mass.' The "
                  "solver derives the other. Only used for hotfires."),
            anchor="w", justify="left", wraplength=820,
            text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
        ).pack(fill="x", padx=(VALUE_INDENT, 0), pady=(theme.PAD_S, theme.PAD_XS))
        for key in _HOTFIRE_ALTERNATES:
            self.add_field(self._hotfire_section, key)

        self.add_divider(wrap)
        self.add_advanced_header(
            wrap, "Advanced (propellant chemistry & regression law)")
        for key in _ADVANCED_KEYS:
            self.add_advanced_field(wrap, key)

    # ---- tab 3 --------------------------------------------------------

    def _build_body_tab(self, wrap) -> None:
        # Content and placeholder are siblings in the same wrap; exactly one is
        # packed at a time. Keeping the content in its own frame means the
        # field order survives every toggle.
        self._body_content = ctk.CTkFrame(wrap, fg_color="transparent")
        self._body_content.pack(fill="x")

        self._body_placeholder = ctk.CTkLabel(
            wrap,
            text=("A hotfire has no trajectory, so none of these inputs are "
                  "used.\n\nSwitch to fuel mass convergence or a parametric "
                  "study to set them."),
            font=ctk.CTkFont(size=theme.SIZE_H2),
            text_color=theme.TEXT_FAINT,
            wraplength=600, justify="center",
        )

        content = self._body_content
        self.add_section_title(content, "Rocket")
        self.add_field(content, "dry_mass")
        self.add_field(content, "rocket_external_diameter")
        self.add_field(content, "drag_coefficient")

        self.add_divider(content)
        self.add_section_title(content, "Mission")
        self.add_field(content, "target_apogee")
        self.add_field(content, "launch_site_altitude")
        self.add_field(content, "launch_angle")

    # ==================================================================
    # Visibility
    # ==================================================================

    @property
    def sim_type(self) -> str:
        return SIM_TYPE_WIRE.get(self.sim_type_var.get(), "fuel_mass_convergence")

    def _refresh_visibility(self) -> None:
        """Show what this simulation type uses, hide what it doesn't."""
        sim_type = self.sim_type
        is_hotfire = sim_type == "hotfire"
        is_parametric = sim_type == "parametric_study"
        swept = set(self.parametric_list.used_vars()) if is_parametric else set()

        self.set_packed(self._parametric_section, is_parametric,
                        {"fill": "x", "pady": (theme.PAD_S, 0)})
        self.set_packed(self._hotfire_section, is_hotfire, {"fill": "x"})

        # Rocket body swaps content for an explanation rather than emptying.
        self.set_packed(self._body_content, not is_hotfire, {"fill": "x"})
        self.set_packed(self._body_placeholder, is_hotfire,
                        {"pady": theme.PAD_XL, "padx": theme.PAD_L, "fill": "x"})

        # A swept variable is supplied per point, so its static field would be
        # misleading. Hide it rather than leaving a value that does nothing.
        for path, field in self.fields.items():
            if path in swept:
                self.set_packed(field, False)
            elif path not in _HOTFIRE_ALTERNATES:
                self.set_packed(field, True)

    # ==================================================================
    # Serialisation
    # ==================================================================

    def to_config(self) -> dict:
        sim_type = self.sim_type
        swept = (set(self.parametric_list.used_vars())
                 if sim_type == "parametric_study" else set())

        settings: dict = {
            "simulation_type": sim_type,
            "output_units": self.output_units_var.get(),
        }
        if sim_type == "parametric_study":
            settings["parametric_study_settings"] = self.parametric_list.to_dict()

        inputs: dict = {}
        for path, field in self.fields.items():
            key = path.rsplit(".", 1)[-1]
            if key in swept or not self._is_key_active(key, sim_type):
                continue
            inputs[key] = field.to_pair()

        return {
            "metadata": {
                "simulation_type": "steady",
                "simulation_name": self.sim_name_var.get().strip(),
                "simulation_description": self.description.get("0.0", "end").strip(),
                "expected_output": "",
            },
            "simulation_settings": settings,
            "rocket_inputs": inputs,
        }

    def _is_key_active(self, key: str, sim_type: str) -> bool:
        """Whether a field belongs in the config for this simulation type.

        Keeps a stale hotfire value from leaking into a convergence run, and
        vice versa.
        """
        if key in _HOTFIRE_ALTERNATES:
            return sim_type == "hotfire"
        kinematics = registry.steady_schema_keys().get("kinematics_requirements", [])
        if key in kinematics:
            return sim_type != "hotfire"
        return True

    def from_config(self, config: dict) -> None:
        settings = config.get("simulation_settings") or {}
        metadata = config.get("metadata") or {}
        inputs = config.get("rocket_inputs") or {}

        wire = settings.get("simulation_type", "fuel_mass_convergence")
        self.sim_type_var.set(SIM_TYPES.get(wire, SIM_TYPES["fuel_mass_convergence"]))
        self.output_units_var.set(settings.get("output_units", "SI"))

        self.sim_name_var.set(str(metadata.get("simulation_name", "") or ""))
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
        return self.sim_name_var.get().strip() or super()._default_run_name()

    def reset_to_defaults(self) -> None:
        super().reset_to_defaults()
        self.sim_name_var.set("")
        self.description.delete("0.0", "end")
        self.sim_type_var.set(SIM_TYPES["fuel_mass_convergence"])
        self.parametric_list.clear()
        self._refresh_visibility()
        self._clean_snapshot = self.to_config()
