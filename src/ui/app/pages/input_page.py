"""
InputPage — everything the steady and unsteady forms have in common.

The two pages used to be 2,400 lines with near-identical copies of the preset
loading, saving, dirty-checking, validation and run pipeline. All of that lives
here now; the subclasses only describe their own fields and how those map to a
config dict.

WHAT A SUBCLASS PROVIDES
------------------------
    KIND            "steady" or "unsteady"
    TITLE           top-bar title
    _build_form()   lay out the fields inside self.form
    to_config()     the form as a config dict
    from_config()   populate the form from one
    _validate()     list of problems, via backend_bridge
    _preflight()    warnings dict, via backend_bridge

WHAT IT GETS BACK
-----------------
A scrollable body with a footer, Load/Save/Run wired up, dirty tracking,
keyboard shortcuts, the validation and preflight modals, and the handoff to the
loading screen.

FIELD PATHS
-----------
Fields are stored in self.fields under a dotted path. Steady is flat, so the
path is just the key; unsteady nests per control volume:

    "fuel_length"
    "CV1_tank.tank_internal_diameter"

The last segment is always the registry key. That one convention lets the base
class walk every field on a page without knowing how the page is organised.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from src.ui.app import backend_bridge, theme
from src.ui.app import field_registry as registry
from src.ui.app.widgets.error_popup import show_error_list
from src.ui.app.widgets.form_field import LabeledField
from src.ui.app.widgets.preflight_dialog import show_preflight_warnings


class InputPage(ctk.CTkFrame):
    """Base class for the two simulator input forms."""

    TITLE = ""
    KIND = ""

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate

        # path -> widget, for every field on the page
        self.fields: dict[str, LabeledField] = {}
        # Where this form was loaded from, so Save can overwrite in place.
        self._loaded_path: Optional[Path] = None

        self._build_shell()
        self._build_form(self.form)

        # The baseline for is_dirty(). Re-taken on every load and save, so
        # "dirty" means "different from the last time it was on disk".
        self._clean_snapshot = self.to_config()

    # ==================================================================
    # Layout
    # ==================================================================

    def _build_shell(self) -> None:
        """The scrollable body and the footer, which every input page shares."""
        # Footer first, so a long form can never push the Run button off-screen.
        footer = ctk.CTkFrame(self, height=64, corner_radius=0)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)

        self._status = ctk.CTkLabel(
            footer, text="", anchor="w", text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
        )
        self._status.pack(side="left", padx=theme.PAD_L)

        ctk.CTkButton(footer, text="Run", width=140, height=40,
                      font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
                      fg_color=theme.SUCCESS, hover_color=theme.SUCCESS_HOVER,
                      command=self._on_run).pack(
            side="right", padx=(theme.PAD_S, theme.PAD_L), pady=theme.PAD_S)

        ctk.CTkButton(footer, text="Save preset", width=130, height=40,
                      fg_color=theme.ACCENT_SLATE, hover_color=theme.ACCENT_SLATE_HOVER,
                      command=self._on_save_preset).pack(
            side="right", padx=theme.PAD_XS, pady=theme.PAD_S)

        ctk.CTkButton(footer, text="Load preset", width=130, height=40,
                      fg_color=theme.ACCENT_SLATE, hover_color=theme.ACCENT_SLATE_HOVER,
                      command=self._on_load_preset).pack(
            side="right", padx=theme.PAD_XS, pady=theme.PAD_S)

        self.form = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.form.pack(side="top", fill="both", expand=True,
                       padx=theme.PAD_XL, pady=theme.PAD_M)

    def add_field(self, parent, path: str, **kwargs) -> LabeledField:
        """Build a field from its registry spec and remember it under `path`."""
        key = path.rsplit(".", 1)[-1]
        field = LabeledField(parent, registry.get(key), **kwargs)
        field.pack(fill="x", pady=theme.PAD_XS)
        self.fields[path] = field
        return field

    # ==================================================================
    # Subclass hooks
    # ==================================================================

    def _build_form(self, parent) -> None:
        raise NotImplementedError

    def to_config(self) -> dict:
        raise NotImplementedError

    def from_config(self, config: dict) -> None:
        raise NotImplementedError

    def _validate(self, config: dict) -> list[str]:
        raise NotImplementedError

    def _preflight(self, config: dict) -> dict:
        raise NotImplementedError

    def _default_run_name(self) -> str:
        """What to call a run when the user hasn't named it."""
        return f"{self.KIND}_run"

    # ==================================================================
    # Presets
    # ==================================================================

    def _presets_dir(self) -> Path:
        return (backend_bridge.steady_presets_dir() if self.KIND == "steady"
                else backend_bridge.unsteady_presets_dir())

    def _on_load_preset(self) -> None:
        from tkinter import filedialog

        directory = self._presets_dir()
        directory.mkdir(parents=True, exist_ok=True)
        chosen = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title=f"Load a {self.KIND} preset",
            initialdir=str(directory),
            filetypes=[("Config files", "*.jsonc *.json"), ("All files", "*.*")],
        )
        if not chosen:
            return
        self.load_preset(Path(chosen))

    def load_preset(self, path: Path) -> None:
        """Populate the form from a file, reporting failures in the status line."""
        try:
            config = backend_bridge.load_jsonc(path)
        except Exception as exc:                # noqa: BLE001
            self._set_status(f"Could not read {path.name}: {exc}", error=True)
            return
        try:
            self.from_config(config)
        except Exception as exc:                # noqa: BLE001
            self._set_status(f"{path.name} isn't a {self.KIND} config: {exc}",
                             error=True)
            return
        self._loaded_path = path
        self._clean_snapshot = self.to_config()
        self._set_status(f"Loaded {path.name}")

    def _on_save_preset(self) -> None:
        from tkinter import filedialog

        directory = self._presets_dir()
        directory.mkdir(parents=True, exist_ok=True)
        chosen = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            title=f"Save this {self.KIND} preset",
            initialdir=str(directory),
            initialfile=(self._loaded_path.name if self._loaded_path
                         else f"{self._default_run_name()}.jsonc"),
            defaultextension=".jsonc",
            filetypes=[("Config files", "*.jsonc"), ("All files", "*.*")],
        )
        if not chosen:
            return
        path = Path(chosen)
        try:
            backend_bridge.save_jsonc(path, self.to_config())
        except Exception as exc:                # noqa: BLE001
            self._set_status(f"Could not save: {exc}", error=True)
            return
        self._loaded_path = path
        self._clean_snapshot = self.to_config()
        self._set_status(f"Saved {path.name}")

    # ==================================================================
    # Running
    # ==================================================================

    def _on_run(self) -> None:
        """Validate, preflight, then hand off to the loading screen.

        Three gates, cheapest first: structural problems come back instantly,
        range warnings need only the conversion layer, and only once both are
        satisfied does anything slow start.
        """
        self._clear_field_errors()
        config = self.to_config()

        errors = self._validate(config)
        if errors:
            self._highlight_errors(errors)
            self._set_status(f"{len(errors)} problem"
                             f"{'s' if len(errors) != 1 else ''} to fix", error=True)
            show_error_list(self, errors)
            return

        try:
            warnings = self._preflight(config)
        except Exception as exc:                # noqa: BLE001
            # Preflight is advisory. If the checks themselves break, say so and
            # let the run proceed rather than blocking on a broken guard.
            warnings = {}
            self._set_status(f"Preflight could not run: {exc}")

        if warnings and not show_preflight_warnings(self, warnings):
            self._set_status("Run cancelled from preflight")
            return

        self._launch(config)

    def _launch(self, config: dict) -> None:
        """Start the run on the loading screen."""
        shell = self.winfo_toplevel()
        runner = (backend_bridge.run_steady if self.KIND == "steady"
                  else backend_bridge.run_unsteady)
        path = self._loaded_path

        self._set_status("Running…")
        shell.start_loading_run(
            title=f"{self.KIND.capitalize()} simulation",
            run_fn=lambda: runner(config, path),
            on_complete=self._on_run_complete,
            on_error=lambda exc, tb: self._on_run_error(exc, tb, config),
        )

    def _on_run_complete(self, result) -> None:
        """Show the finished run. Wired to the results pages in a later step."""
        shell = self.winfo_toplevel()
        target = "steady_results" if self.KIND == "steady" else "unsteady_results"
        page = shell.pages.get(target)
        if page is not None and hasattr(page, "show_run"):
            try:
                page.show_run(result)
            except Exception:                   # noqa: BLE001
                pass
        shell.go(target)

    def _on_run_error(self, exc: BaseException, traceback_text: str,
                      config: dict) -> None:
        from src.ui.app.widgets.error_popup import show_simulation_error
        show_simulation_error(
            self, exc, traceback_text, config,
            back_button_text=f"Back to {self.KIND}",
            back_target=self.KIND,
            report_title_prefix=f"Error running {self.KIND}",
        )

    # ==================================================================
    # Errors
    # ==================================================================

    def _clear_field_errors(self) -> None:
        for field in self.fields.values():
            field.mark_invalid(False)

    def _highlight_errors(self, errors: list[str]) -> None:
        """Ring the fields an error message names.

        Validator messages are written for humans and carry field labels
        ("CV4_chamber: missing Fuel mass"), so matching happens on the label.
        Two refinements stop that being sloppy:

        - Word boundaries, so "Drag coefficient" doesn't also ring itself for
          an error about the "Drogue drag coefficient".
        - Section scoping, so an error prefixed with a control volume only
          rings fields in that control volume. Several CVs share labels —
          three of them have a "Drag coefficient" — and without this every
          one of them would light up.
        """
        for path, field in self.fields.items():
            section = path.rsplit(".", 1)[0] if "." in path else ""
            pattern = re.compile(rf"(?<![A-Za-z]){re.escape(field.spec.label)}(?![A-Za-z])")
            sections = self._section_names()
            for message in errors:
                prefix = message.split(":", 1)[0] if ":" in message else ""
                # A message prefixed with some OTHER section isn't about this
                # field. A message with no section prefix applies page-wide.
                if prefix in sections and prefix != section:
                    continue
                if pattern.search(message):
                    field.mark_invalid(True)
                    break

    def _section_names(self) -> set[str]:
        """The section prefixes used in field paths, for error scoping."""
        return {p.rsplit(".", 1)[0] for p in self.fields if "." in p}

    def _set_status(self, text: str, *, error: bool = False) -> None:
        self._status.configure(
            text=text, text_color=theme.ERROR if error else theme.TEXT_MUTED)

    # ==================================================================
    # Shell contract
    # ==================================================================

    def is_dirty(self) -> bool:
        """True when the form differs from the last saved or loaded state."""
        try:
            return self.to_config() != self._clean_snapshot
        except Exception:                       # noqa: BLE001
            return False

    def reset_to_defaults(self) -> None:
        """Blank the form. Called when the user goes back to the menu."""
        for field in self.fields.values():
            field.reset_to_default()
        self._loaded_path = None
        self._clean_snapshot = self.to_config()
        self._set_status("")

    def handle_shortcut(self, action: str) -> None:
        if action == "run":
            self._on_run()
        elif action == "save":
            self._on_save_preset()
        elif action == "load":
            self._on_load_preset()

    def on_show(self) -> None:
        self._clear_field_errors()
