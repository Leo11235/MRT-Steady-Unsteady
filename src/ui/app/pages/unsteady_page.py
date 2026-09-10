"""
Unsteady input form.

Seven tabs: simulation settings, then one per control volume.

    Sim settings   name, description, warnings and graph output
    Tank           CV1      Injector   CV3      Nozzle       CV5
    Valve          CV2      Chamber    CV4      Rocket body  CV6

Each control-volume tab opens with its physics-model dropdown and a paragraph
explaining what that model assumes, then the inputs that model needs. Changing
the model swaps the fields underneath without discarding what's typed in the
ones it hides.

The whole form is generated from the backend schema: every CV, every model and
every field. The field registry supplies labels, units and help text. Adding a
model to the schema makes it appear here with its own fields, and nothing in
this file changes.

The old version kept a hand-maintained `_MODEL_FIELDS` map and a
`_DEFAULT_CV_INPUTS` dict that both had to track the schema by hand.
"""

from __future__ import annotations

import customtkinter as ctk

from src.ui.app import backend_bridge, theme
from src.ui.app import field_registry as registry
from src.ui.app.pages.input_page import InputPage, VALUE_INDENT
from src.ui.app.widgets.tooltip import Tooltip


# Tab label per control volume, in tab order.
CV_TABS: dict[str, str] = {
    "CV1_tank":       "Tank",
    "CV2_valve":      "Valve",
    "CV3_injector":   "Injector",
    "CV4_chamber":    "Chamber",
    "CV5_nozzle":     "Nozzle",
    "CV6_trajectory": "Rocket body",
}

# Chamber inputs with defensible defaults, locked behind the padlock.
_CHAMBER_ADVANCED = (
    "chamber_fuel_density",
    "chamber_regression_rate_scaling_constant",
    "chamber_regression_rate_exponent",
    "chamber_cstar_efficiency",
)

ALTERNATES = backend_bridge.UNSTEADY_ALTERNATES


class UnsteadyPage(InputPage):
    TITLE = "Unsteady simulation"
    KIND = "unsteady"

    # ==================================================================
    # Tabs
    # ==================================================================

    def _build_tabs(self) -> None:
        self._schema = registry.unsteady_schema_keys()
        self._models: dict[str, list[str]] = {}
        for cv, model in self._schema:
            self._models.setdefault(cv, []).append(model)

        self.sim_name_var = ctk.StringVar()
        self.warnings_var = ctk.BooleanVar(value=True)
        # Off by default: rendering every graph adds ~30 s to a run, so it
        # is opt-in rather than something you have to remember to switch off.
        self.save_pdf_var = ctk.BooleanVar(value=False)
        self.save_png_var = ctk.BooleanVar(value=False)

        self.model_vars: dict[str, ctk.StringVar] = {}
        self._model_desc: dict[str, ctk.CTkLabel] = {}

        self._build_sim_tab(self.add_tab("Sim settings"))
        for cv, tab_name in CV_TABS.items():
            if cv in self._models:
                self._build_cv_tab(self.add_tab(tab_name), cv)

    def _after_build(self) -> None:
        # Hide the fields the default model doesn't use. Has to wait until the
        # build order is recorded, or a field hidden now could never be
        # restored to its right place.
        self._refresh_all_models()

    # ---- tab 1 --------------------------------------------------------

    def _build_sim_tab(self, wrap) -> None:
        self.add_section_title(wrap, "Simulation")

        # Tooltip on both halves of the row, so hovering anywhere works and
        # no separate help icon is needed.
        help_text = ("Optional label for this run. Used for the output folder "
                     "name and stored in the results file's metadata.")
        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        label = ctk.CTkLabel(row, text="Simulation name", width=220, anchor="w")
        label.pack(side="left", padx=(0, theme.PAD_S))
        entry = ctk.CTkEntry(row, textvariable=self.sim_name_var,
                             placeholder_text="optional; blank uses a timestamp")
        entry.pack(side="left", fill="x", expand=True)
        Tooltip(label, help_text)
        Tooltip(entry, help_text)

        ctk.CTkLabel(wrap, text="Description", anchor="w").pack(
            fill="x", pady=(theme.PAD_S, theme.PAD_XS))
        self.description = ctk.CTkTextbox(wrap, height=60, wrap="word")
        self.description.pack(fill="x")

        self.add_divider(wrap)
        self.add_section_title(wrap, "Output")
        self._checkbox(wrap, self.warnings_var, "Collect warnings",
                       "Runs range checks during the simulation and flags "
                       "results that look physically suspicious: tank "
                       "temperature near critical, O/F outside the trusted CEA "
                       "range, Mach outside the drag model's range.")
        self._checkbox(wrap, self.save_pdf_var, "Generate PDF report",
                       "Write a full run report beside the results JSON: inputs, "
                       "performance, phase breakdown, events, warnings, then every "
                       "plot. Off by default: rendering the graphs adds roughly "
                       "half a minute to the run. You can also generate it later "
                       "from the results page.")
        self._checkbox(wrap, self.save_png_var, "Save graphs as PNGs",
                       "Write each output plot as its own PNG in a graphs/ "
                       "folder beside the results JSON.")

    def _checkbox(self, parent, variable, text: str, help_text: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        box = ctk.CTkCheckBox(row, text=text, variable=variable)
        box.pack(side="left")
        Tooltip(box, help_text)

    # ---- CV tabs -------------------------------------------------------

    def _build_cv_tab(self, wrap, cv: str) -> None:
        models = self._models[cv]
        default_model = models[0]

        # ---- model picker ---------------------------------------------
        self.add_section_title(wrap, "Physics model")
        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text="Model", width=220, anchor="w").pack(
            side="left", padx=(0, theme.PAD_S))

        # The var holds the pretty label; model_wire() converts on the way out.
        var = ctk.StringVar(value=registry.model_label(default_model))
        self.model_vars[cv] = var
        picker = ctk.CTkOptionMenu(
            row, variable=var,
            values=[registry.model_label(m) for m in models],
            command=lambda _v, c=cv: self._on_model_changed(c),
            dynamic_resizing=False, width=260,
        )
        picker.pack(side="left")
        if len(models) == 1:
            # Nothing to choose. Leave it visible so the model is documented,
            # but don't pretend it's a decision.
            picker.configure(state="disabled")

        desc = ctk.CTkLabel(
            wrap, text=registry.model_description(default_model),
            anchor="w", justify="left", wraplength=560,
            text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
        )
        desc.pack(fill="x", padx=(VALUE_INDENT, 0),
                  pady=(theme.PAD_XS, theme.PAD_S), anchor="w")
        self._model_desc[cv] = desc

        self.add_divider(wrap)
        self.add_section_title(wrap, "Inputs")

        # ---- fields ----------------------------------------------------
        # Build the union of every model's fields once. Switching models hides
        # and shows them, so a value typed under one model survives a look at
        # another.
        is_chamber = cv == "CV4_chamber"
        advanced = set(_CHAMBER_ADVANCED) if is_chamber else set()

        ordered: list[str] = []
        for model in models:
            for key in self._schema[(cv, model)]:
                if key not in ordered:
                    ordered.append(key)

        # The note for an alternate pair goes immediately above the first of
        # the two, so the rule is read before the fields it governs.
        alternate_first = {pair[0]: pair for pair in ALTERNATES.get(cv, [])}

        for key in ordered:
            if key in advanced:
                continue
            if key in alternate_first:
                a, b = alternate_first[key]
                self.add_note(
                    wrap, f"Fill in EITHER '{registry.label(a)}' OR "
                          f"'{registry.label(b)}'.")
            self.add_field(wrap, f"{cv}.{key}")

        if is_chamber:
            self.add_divider(wrap)
            self.add_advanced_header(
                wrap, "Advanced (propellant & combustion parameters)")
            for key in _CHAMBER_ADVANCED:
                self.add_advanced_field(wrap, f"{cv}.{key}")

    # ==================================================================
    # Model selection
    # ==================================================================

    def _model_of(self, cv: str) -> str:
        return registry.model_wire(self.model_vars[cv].get())

    def _on_model_changed(self, cv: str) -> None:
        """Show the fields the selected model uses, hide the rest."""
        model = self._model_of(cv)
        wanted = set(self._schema.get((cv, model), []))

        for path, field in self.fields.items():
            if not path.startswith(f"{cv}."):
                continue
            self.set_packed(field, path.split(".", 1)[1] in wanted)

        self._model_desc[cv].configure(text=registry.model_description(model))

    def _refresh_all_models(self) -> None:
        for cv in self._models:
            self._on_model_changed(cv)

    # ==================================================================
    # Serialisation
    # ==================================================================

    def to_config(self) -> dict:
        cv_inputs: dict = {}
        for cv in self._models:
            model = self._model_of(cv)
            block: dict = {"model": model}
            # Only the selected model's fields. A value typed under a different
            # model stays on screen but never reaches the config.
            for key in self._schema.get((cv, model), []):
                field = self.fields.get(f"{cv}.{key}")
                if field is not None:
                    block[key] = field.to_pair()
            cv_inputs[cv] = block

        return {
            "config": {
                "metadata": {
                    "simulation_type": "unsteady",
                    "simulation_name": self.sim_name_var.get().strip(),
                    "simulation_description": self.description.get("0.0", "end").strip(),
                    "expected_output": "",
                    "warnings": bool(self.warnings_var.get()),
                    "save_to_pdf": bool(self.save_pdf_var.get()),
                    "save_to_png": bool(self.save_png_var.get()),
                },
                "rocket_inputs": cv_inputs,
            },
            "simulation_settings_override": {},
        }

    def from_config(self, config: dict) -> None:
        block = config.get("config") or {}
        metadata = block.get("metadata") or {}
        cv_inputs = block.get("rocket_inputs") or {}
        if not cv_inputs:
            raise ValueError("no rocket_inputs block")

        self.sim_name_var.set(str(metadata.get("simulation_name", "") or ""))
        self.description.delete("0.0", "end")
        self.description.insert("0.0", str(metadata.get("simulation_description", "") or ""))
        self.warnings_var.set(bool(metadata.get("warnings", True)))
        self.save_pdf_var.set(bool(metadata.get("save_to_pdf", False)))
        self.save_png_var.set(bool(metadata.get("save_to_png", False)))

        # Models first, so the right fields are visible before they're filled.
        for cv, cv_block in cv_inputs.items():
            if cv not in self.model_vars or not isinstance(cv_block, dict):
                continue
            model = cv_block.get("model")
            if model in self._models.get(cv, []):
                self.model_vars[cv].set(registry.model_label(model))

        for path, field in self.fields.items():
            cv, key = path.split(".", 1)
            cv_block = cv_inputs.get(cv) or {}
            if key in cv_block:
                field.from_pair(cv_block[key])
            else:
                field.reset_to_default()

        self._refresh_all_models()

    # ==================================================================
    # Backend
    # ==================================================================

    def _validate(self, config: dict) -> list[str]:
        return backend_bridge.validate_unsteady_config(config)

    def _preflight(self, config: dict) -> dict:
        rocket_inputs = (config.get("config") or {}).get("rocket_inputs") or {}
        return backend_bridge.preflight_unsteady(rocket_inputs)

    def _default_run_name(self) -> str:
        return self.sim_name_var.get().strip() or super()._default_run_name()

    def reset_to_defaults(self) -> None:
        super().reset_to_defaults()
        self.sim_name_var.set("")
        self.description.delete("0.0", "end")
        self.warnings_var.set(True)
        self.save_pdf_var.set(False)
        self.save_png_var.set(False)
        for cv, models in self._models.items():
            self.model_vars[cv].set(registry.model_label(models[0]))
        self._refresh_all_models()
        self._clean_snapshot = self.to_config()
