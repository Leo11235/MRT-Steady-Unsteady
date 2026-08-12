"""
Unsteady input form.

Six collapsible control-volume sections, each with a physics-model dropdown
that decides which fields below it apply. Picking a different valve model swaps
the valve's inputs; picking a different injector model adds or removes the
two-phase multiplier.

The whole form is generated from the backend schema. Every CV, every model and
every field comes from input_schema.jsonc, with the field registry supplying
labels, units and help text. Adding a model to the schema makes it appear in
the dropdown with its own fields, and nothing here needs editing.

The old version of this page carried a hand-maintained `_MODEL_FIELDS` map that
had to be kept in step with the schema by hand, and a `_DEFAULT_CV_INPUTS` dict
listing every field again.
"""

from __future__ import annotations

import customtkinter as ctk

from src.ui.app import backend_bridge, theme
from src.ui.app import field_registry as registry
from src.ui.app.pages.input_page import InputPage
from src.ui.app.widgets.section import CollapsibleSection, note, section_title


CV_TITLES: dict[str, str] = {
    "CV1_tank":       "CV1 — Oxidizer tank",
    "CV2_valve":      "CV2 — Main valve",
    "CV3_injector":   "CV3 — Injector",
    "CV4_chamber":    "CV4 — Combustion chamber",
    "CV5_nozzle":     "CV5 — Nozzle",
    "CV6_trajectory": "CV6 — Trajectory",
}

# Which fields are 'fill exactly one of'. Mirrors the nested lists in the
# schema, which the bridge also reads for validation.
ALTERNATES = backend_bridge.UNSTEADY_ALTERNATES


class UnsteadyPage(InputPage):
    TITLE = "Unsteady simulation"
    KIND = "unsteady"

    # ==================================================================
    # Layout
    # ==================================================================

    def _build_form(self, parent) -> None:
        self._schema = registry.unsteady_schema_keys()
        # {cv: [model names]}, in schema order
        self._models: dict[str, list[str]] = {}
        for cv, model in self._schema:
            self._models.setdefault(cv, []).append(model)

        self.model_vars: dict[str, ctk.StringVar] = {}
        self._sections: dict[str, CollapsibleSection] = {}
        # (cv, field key) -> the widget, so visibility can be toggled per model
        self._field_rows: dict[tuple[str, str], object] = {}

        self._build_metadata(parent)
        for cv in CV_TITLES:
            if cv in self._models:
                self._build_cv(parent, cv)

    def _build_metadata(self, parent) -> None:
        section_title(parent, "Simulation")

        self.name_var = ctk.StringVar()
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text="Run name", width=220, anchor="w").pack(
            side="left", padx=(0, theme.PAD_S))
        ctk.CTkEntry(row, textvariable=self.name_var,
                     placeholder_text="optional; blank uses a timestamp").pack(
            side="left", fill="x", expand=True)

        toggles = ctk.CTkFrame(parent, fg_color="transparent")
        toggles.pack(fill="x", pady=theme.PAD_S)

        self.warnings_var = ctk.BooleanVar(value=True)
        self.save_pdf_var = ctk.BooleanVar(value=True)
        self.save_png_var = ctk.BooleanVar(value=False)
        for text, var in (("Collect warnings", self.warnings_var),
                          ("Save graphs to PDF", self.save_pdf_var),
                          ("Save graphs as PNGs", self.save_png_var)):
            ctk.CTkCheckBox(toggles, text=text, variable=var).pack(
                side="left", padx=(0, theme.PAD_L))

        ctk.CTkLabel(parent, text="Description", anchor="w").pack(
            fill="x", pady=(theme.PAD_S, theme.PAD_XS))
        self.description = ctk.CTkTextbox(parent, height=60, wrap="word")
        self.description.pack(fill="x")

    def _build_cv(self, parent, cv: str) -> None:
        models = self._models[cv]
        section = CollapsibleSection(
            parent, CV_TITLES.get(cv, cv),
            subtitle=registry.model_label(models[0]),
            start_open=(cv == "CV1_tank"),      # one open is enough of a hint
        )
        section.pack(fill="x", pady=(theme.PAD_M, 0))
        self._sections[cv] = section

        # ---- model picker ---------------------------------------------
        var = ctk.StringVar(value=registry.model_label(models[0]))
        self.model_vars[cv] = var

        row = ctk.CTkFrame(section.body, fg_color="transparent")
        row.pack(fill="x", pady=(0, theme.PAD_XS))
        ctk.CTkLabel(row, text="Physics model", width=220, anchor="w").pack(
            side="left", padx=(0, theme.PAD_S))
        picker = ctk.CTkOptionMenu(
            row, values=[registry.model_label(m) for m in models],
            variable=var, width=240,
            command=lambda _v, c=cv: self._on_model_changed(c),
        )
        picker.pack(side="left")
        # A single-model CV has nothing to choose, so say so rather than
        # offering a dropdown that does nothing.
        if len(models) == 1:
            picker.configure(state="disabled")

        self._model_blurbs = getattr(self, "_model_blurbs", {})
        blurb = ctk.CTkLabel(
            section.body, text="", anchor="w", justify="left",
            text_color=theme.TEXT_MUTED, wraplength=760,
            font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
        )
        blurb.pack(fill="x", pady=(0, theme.PAD_S))
        self._model_blurbs[cv] = blurb

        # ---- fields ----------------------------------------------------
        # Every field any of this CV's models can use, built once. Switching
        # models hides and shows them rather than rebuilding, so a value typed
        # under one model survives a look at another.
        alternates = ALTERNATES.get(cv, [])
        if alternates:
            pairs = ", ".join(f"{registry.label(a)} or {registry.label(b)}"
                              for a, b in alternates)
            note(section.body, f"Fill exactly one of: {pairs}.", left_pad=0)

        seen: list[str] = []
        for model in models:
            for key in self._schema[(cv, model)]:
                if key not in seen:
                    seen.append(key)
        for key in seen:
            field = self.add_field(section.body, f"{cv}.{key}")
            self._field_rows[(cv, key)] = field

        self._on_model_changed(cv)

    # ==================================================================
    # Model selection
    # ==================================================================

    def _model_of(self, cv: str) -> str:
        return registry.model_wire(self.model_vars[cv].get())

    def _on_model_changed(self, cv: str) -> None:
        """Show the fields the selected model uses, hide the rest."""
        model = self._model_of(cv)
        wanted = set(self._schema.get((cv, model), []))

        for (row_cv, key), field in self._field_rows.items():
            if row_cv != cv:
                continue
            visible = key in wanted
            if visible and not field.winfo_ismapped():
                field.pack(fill="x", pady=theme.PAD_XS)
            elif not visible and field.winfo_ismapped():
                field.pack_forget()

        self._sections[cv].set_subtitle(registry.model_label(model))
        self._model_blurbs[cv].configure(text=registry.model_description(model))

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
                    "simulation_name": self.name_var.get().strip(),
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

        self.name_var.set(str(metadata.get("simulation_name", "") or ""))
        self.description.delete("0.0", "end")
        self.description.insert("0.0", str(metadata.get("simulation_description", "") or ""))
        self.warnings_var.set(bool(metadata.get("warnings", True)))
        self.save_pdf_var.set(bool(metadata.get("save_to_pdf", True)))
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

        for cv in self._models:
            self._on_model_changed(cv)

    # ==================================================================
    # Backend
    # ==================================================================

    def _validate(self, config: dict) -> list[str]:
        return backend_bridge.validate_unsteady_config(config)

    def _preflight(self, config: dict) -> dict:
        rocket_inputs = (config.get("config") or {}).get("rocket_inputs") or {}
        return backend_bridge.preflight_unsteady(rocket_inputs)

    def _default_run_name(self) -> str:
        return self.name_var.get().strip() or "unsteady_run"

    def reset_to_defaults(self) -> None:
        super().reset_to_defaults()
        self.name_var.set("")
        self.description.delete("0.0", "end")
        self.warnings_var.set(True)
        self.save_pdf_var.set(True)
        self.save_png_var.set(False)
        for cv, models in self._models.items():
            self.model_vars[cv].set(registry.model_label(models[0]))
            self._on_model_changed(cv)
        self._clean_snapshot = self.to_config()
