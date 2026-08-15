"""
InputPage — everything the steady and unsteady forms have in common.

LAYOUT
------
    +--------------------------------------+-------------+
    | [Tab] [Tab] [Tab]                    |  Actions    |
    |                                      |  Load       |
    |   scrollable form                    |  Save       |
    |                                      |  [ Run ]    |
    |                                      |  [x] auto   |
    +--------------------------------------+-------------+
    | status line                                        |
    +----------------------------------------------------+

Tabs on the left, a fixed action sidebar on the right, one status line across
the bottom. The sidebar stays put while the form scrolls, so Run is always in
the same place no matter how far down the tab you are.

WHAT A SUBCLASS PROVIDES
------------------------
    KIND            "steady" or "unsteady"
    TITLE           top-bar title
    _build_tabs()   add tabs and fill them
    to_config()     the form as a config dict
    from_config()   populate the form from one
    _validate()     list of problems, via backend_bridge
    _preflight()    warnings dict, via backend_bridge

WHAT IT GETS BACK
-----------------
The tab/sidebar/status frame, Load, Save and Run wired up, dirty tracking,
keyboard shortcuts, validation and preflight modals, the advanced-lock
mechanism, and order-preserving show/hide for conditional fields.

FIELD PATHS
-----------
Fields live in self.fields under a dotted path. Steady is flat, unsteady nests
per control volume:

    "fuel_length"
    "CV1_tank.tank_internal_diameter"

The last segment is always the registry key. That one convention lets this
class walk every field without knowing how the page is organised.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from src.ui.app import backend_bridge, theme
from src.ui.app import field_registry as registry
from src.ui.app import settings as user_settings
from src.ui.app.services import recent_presets
from src.ui.app.widgets.error_popup import show_error_list
from src.ui.app.widgets.form_field import LabeledField
from src.ui.app.widgets.preflight_dialog import show_preflight_warnings
from src.ui.app.widgets.recent_preset_menu import RecentPresetMenu


# The label column width every form row shares. Notes and model descriptions
# are indented by this much so they line up under the value column rather than
# under the labels.
LABEL_WIDTH = 220
VALUE_INDENT = LABEL_WIDTH + theme.PAD_S

_SIDEBAR_MIN_W = 200
_ACTION_W = 180


class InputPage(ctk.CTkFrame):
    """Base class for the two simulator input forms."""

    TITLE = ""
    KIND = ""

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate

        self.fields: dict[str, LabeledField] = {}
        # Fields inside an advanced (locked) section, by path.
        self._advanced_paths: list[str] = []
        self._advanced_locked = ctk.BooleanVar(value=True)
        self._lock_buttons: list[ctk.CTkButton] = []
        # Where this form was loaded from, so Save can offer to overwrite.
        self._loaded_path: Optional[Path] = None
        # Original sibling order per parent, so a hidden field can be put back
        # where it belongs instead of jumping to the bottom. See _show_in_order.
        self._build_order: dict = {}

        self.auto_save_var = ctk.BooleanVar(
            value=bool(user_settings.get("default_auto_save_inputs", True)))

        # Which units a blank form starts in. Read once at build time; a loaded
        # preset overrides it per field, since a preset carries its own units.
        self.system = user_settings.get("default_output_units", "SI")

        self._build_frame()
        self._build_tabs()
        # Order has to be captured BEFORE anything is hidden, otherwise a field
        # that starts hidden has no recorded position to be restored to.
        self._capture_build_order()
        self._apply_advanced_lock()
        # Only now can conditional visibility run. Doing it during _build_tabs
        # left every field on screen until the first user interaction, because
        # set_packed had no build order to work from.
        self._after_build()

        # Baseline for is_dirty(): re-taken on every load and save.
        self._clean_snapshot = self.to_config()

    # ==================================================================
    # Frame
    # ==================================================================

    def _build_frame(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=_SIDEBAR_MIN_W)
        self.grid_rowconfigure(0, weight=1)

        self.tabs = ctk.CTkTabview(self, anchor="w")
        self.tabs.grid(row=0, column=0, sticky="nsew",
                       padx=(theme.PAD_M, theme.PAD_S), pady=theme.PAD_M)

        sidebar = ctk.CTkFrame(self, fg_color="transparent")
        sidebar.grid(row=0, column=1, sticky="ns",
                     padx=(theme.PAD_S, theme.PAD_M), pady=theme.PAD_M)
        self._build_sidebar(sidebar)

        self.status_label = ctk.CTkLabel(
            self, text="", anchor="w", text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
        )
        self.status_label.grid(row=1, column=0, columnspan=2, sticky="ew",
                               padx=theme.PAD_M, pady=(0, theme.PAD_S))

    def _build_sidebar(self, parent) -> None:
        """Load, Save and Run, fixed beside the form.

        Run is the tallest and the only coloured one, because it's the thing
        you came here to do.
        """
        ctk.CTkLabel(parent, text="Actions", anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold")).pack(
            fill="x", pady=(0, theme.PAD_S))

        ctk.CTkButton(parent, text="Load preset…", width=_ACTION_W, height=36,
                      command=self._on_load_preset).pack(pady=theme.PAD_XS)

        # Reopening yesterday's preset is the commonest way a session starts,
        # so it gets one click rather than a file dialog.
        self._recent_menu = RecentPresetMenu(
            parent, self.KIND, self.load_preset, width=_ACTION_W)
        self._recent_menu.pack(pady=(0, theme.PAD_XS))

        ctk.CTkButton(parent, text="Save preset…", width=_ACTION_W, height=36,
                      command=self._on_save_preset).pack(pady=theme.PAD_XS)

        ctk.CTkButton(parent, text="Run simulation", width=_ACTION_W, height=44,
                      font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
                      fg_color=theme.ACCENT_SLATE,
                      hover_color=theme.ACCENT_SLATE_HOVER,
                      command=self._on_run).pack(pady=(theme.PAD_M, theme.PAD_XS))

        ctk.CTkCheckBox(parent, text="Auto-save inputs\nas new preset",
                        variable=self.auto_save_var).pack(pady=(theme.PAD_S, 0))

    def add_tab(self, name: str) -> ctk.CTkScrollableFrame:
        """Add a tab and return the scrollable frame to build inside."""
        tab = self.tabs.add(name)
        wrap = ctk.CTkScrollableFrame(tab, label_text="")
        wrap.pack(fill="both", expand=True)
        return wrap

    # ==================================================================
    # Form building
    # ==================================================================

    def add_field(self, parent, path: str, **kwargs) -> LabeledField:
        """Build a field from its registry spec and remember it under `path`."""
        key = path.rsplit(".", 1)[-1]
        field = LabeledField(parent, registry.get(key), system=self.system,
                             label_width=LABEL_WIDTH, **kwargs)
        field.pack(fill="x", pady=theme.PAD_XS)
        self.fields[path] = field
        return field

    def add_note(self, parent, text: str) -> ctk.CTkLabel:
        """A grey italic aside, indented to sit under the value column.

        Used above 'fill exactly one of' pairs, so the rule is read before the
        fields it governs rather than after them.
        """
        label = ctk.CTkLabel(
            parent, text=text, anchor="w", justify="left",
            text_color=theme.TEXT_MUTED, wraplength=820,
            font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
        )
        label.pack(fill="x", padx=(VALUE_INDENT, 0),
                   pady=(theme.PAD_S, theme.PAD_XS))
        return label

    def add_section_title(self, parent, text: str) -> ctk.CTkLabel:
        label = ctk.CTkLabel(parent, text=text, anchor="w",
                             font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"))
        label.pack(fill="x", pady=(theme.PAD_S, theme.PAD_XS))
        return label

    def add_divider(self, parent) -> ctk.CTkFrame:
        rule = ctk.CTkFrame(parent, height=1, fg_color=theme.DIVIDER)
        rule.pack(fill="x", pady=theme.PAD_S)
        return rule

    # ---- advanced (locked) sections ----------------------------------

    def add_advanced_header(self, parent, title: str = "Advanced") -> None:
        """A section header with a padlock that unlocks the fields below it.

        These are inputs with defensible defaults — propellant properties,
        regression-law constants — that most runs never touch. Locking them
        keeps them visible for reference while making it deliberate to change
        one, which stops a stray keystroke silently altering the physics.
        """
        ROW_H = 32
        row = ctk.CTkFrame(parent, fg_color="transparent", height=ROW_H)
        row.pack(fill="x", pady=(theme.PAD_S, theme.PAD_XS))
        row.pack_propagate(False)       # honour the explicit height

        ctk.CTkLabel(row, text=title, anchor="w", height=ROW_H,
                     font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold")).pack(side="left")

        lock = ctk.CTkButton(
            row, text="🔒", width=32, height=ROW_H, corner_radius=6,
            fg_color="transparent", hover_color=theme.CARD_HOVER,
            command=self._toggle_advanced_lock,
        )
        lock.pack(side="left", padx=(theme.PAD_S, 0))
        self._lock_buttons.append(lock)

        # Explicit height and width: without them the font padding crops the
        # descender on this label at small sizes.
        ctk.CTkLabel(row, text="click to edit", anchor="w",
                     height=ROW_H, width=85, text_color=theme.TEXT_FAINT,
                     font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic")).pack(
            side="left", padx=(theme.PAD_XS, 0))

    def add_advanced_field(self, parent, path: str, **kwargs) -> LabeledField:
        field = self.add_field(parent, path, **kwargs)
        self._advanced_paths.append(path)
        return field

    def _toggle_advanced_lock(self) -> None:
        self._advanced_locked.set(not self._advanced_locked.get())
        self._apply_advanced_lock()

    def _apply_advanced_lock(self) -> None:
        locked = self._advanced_locked.get()
        for button in self._lock_buttons:
            button.configure(text="🔒" if locked else "🔓")
        for path in self._advanced_paths:
            field = self.fields.get(path)
            if field is not None:
                field.set_locked(locked)

    # ---- order-preserving show/hide ----------------------------------

    def _capture_build_order(self) -> None:
        """Snapshot each parent's child order, once, after the form is built.

        Tk's pack() appends, so re-showing a hidden widget would drop it at the
        bottom of its section. Remembering the original order lets us pack it
        back before the right sibling instead.
        """
        self._build_order = {}
        for field in self.fields.values():
            parent = field.master
            if parent not in self._build_order:
                self._build_order[parent] = list(parent.winfo_children())

    def _show_in_order(self, widget, pack_kwargs: Optional[dict] = None) -> None:
        """Pack a widget back at its original position among its siblings."""
        pack_kwargs = pack_kwargs or {"fill": "x", "pady": theme.PAD_XS}
        siblings = self._build_order.get(widget.master, [])
        if widget in siblings:
            index = siblings.index(widget)
            for later in siblings[index + 1:]:
                try:
                    if later.winfo_manager() == "pack":
                        widget.pack(before=later, **pack_kwargs)
                        return
                except Exception:               # noqa: BLE001
                    continue
        widget.pack(**pack_kwargs)

    def set_packed(self, widget, visible: bool,
                   pack_kwargs: Optional[dict] = None) -> None:
        """Show or hide a widget, preserving its position when it comes back."""
        try:
            is_packed = widget.winfo_manager() == "pack"
        except Exception:                       # noqa: BLE001
            return
        if visible and not is_packed:
            self._show_in_order(widget, pack_kwargs)
        elif not visible and is_packed:
            widget.pack_forget()

    # ==================================================================
    # Subclass hooks
    # ==================================================================

    def _build_tabs(self) -> None:
        raise NotImplementedError

    def _after_build(self) -> None:
        """Runs once, after the form exists and its layout order is recorded.

        Conditional visibility belongs here rather than in _build_tabs: hiding
        a field before _capture_build_order() runs means it has no recorded
        position, so re-showing it later would append it to the bottom.
        """

    def to_config(self) -> dict:
        raise NotImplementedError

    def from_config(self, config: dict) -> None:
        raise NotImplementedError

    def _validate(self, config: dict) -> list[str]:
        raise NotImplementedError

    def _preflight(self, config: dict) -> dict:
        raise NotImplementedError

    def _default_run_name(self) -> str:
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
        if chosen:
            self.load_preset(Path(chosen))

    def load_preset(self, path: Path) -> None:
        """Populate the form from a file, reporting failures in the status line."""
        try:
            config = backend_bridge.load_jsonc(path)
        except Exception as exc:                # noqa: BLE001
            self._set_status(f"Could not read {path.name}: {exc}", error=True)
            # An unreadable file shouldn't stay in the recent menu offering
            # itself again.
            try:
                recent_presets.forget(self.KIND, path)
                self._recent_menu.refresh()
            except Exception:                   # noqa: BLE001
                pass
            return
        try:
            self.from_config(config)
        except Exception as exc:                # noqa: BLE001
            self._set_status(f"{path.name} isn't a {self.KIND} config: {exc}",
                             error=True)
            return
        self._loaded_path = path
        self._clean_snapshot = self.to_config()
        self._remember(path)
        self._set_status(f"Loaded {path.name}")

    def _remember(self, path: Path) -> None:
        """Push a preset to the top of the recent list and refresh the menu."""
        try:
            recent_presets.remember(self.KIND, path)
            self._recent_menu.refresh()
        except Exception:                       # noqa: BLE001
            pass    # a bookkeeping failure must never block a load or save

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
        if chosen:
            self.save_preset(Path(chosen))

    def save_preset(self, path: Path) -> bool:
        try:
            backend_bridge.save_jsonc(path, self.to_config())
        except Exception as exc:                # noqa: BLE001
            self._set_status(f"Could not save: {exc}", error=True)
            return False
        self._loaded_path = path
        self._clean_snapshot = self.to_config()
        self._remember(path)
        self._set_status(f"Saved {path.name}")
        return True

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

        if self.auto_save_var.get():
            self._auto_save(config)

        self._launch(config)

    def _auto_save(self, config: dict) -> None:
        """Write the inputs beside the run without prompting.

        Overwrites the loaded preset when there is one, so re-running a preset
        keeps a single file rather than accumulating copies.
        """
        target = self._loaded_path
        if target is None:
            target = self._presets_dir() / f"{self._default_run_name()}.jsonc"
        try:
            backend_bridge.save_jsonc(target, config)
            self._loaded_path = target
            self._clean_snapshot = config
        except Exception:                       # noqa: BLE001
            pass    # never let a save problem stop a run

    def _launch(self, config: dict) -> None:
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
        shell = self.winfo_toplevel()
        target = "steady_results" if self.KIND == "steady" else "unsteady_results"

        # _ensure_page, not pages.get: on the first run of a session the
        # results page hasn't been built yet, so .get() returns None, show_run
        # never fires, and go() then builds an empty page. Opening the same run
        # from the browser worked because the browser calls _ensure_page.
        page = shell._ensure_page(target)       # noqa: SLF001 - the shell's own API
        if hasattr(page, "show_run"):
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
        Two refinements keep that honest:

        - Word boundaries, so "Drag coefficient" isn't rung by an error about
          the "Drogue drag coefficient".
        - Section scoping, so a message prefixed with a control volume only
          rings fields in that control volume. Three CVs have a field whose
          label ends in "drag coefficient".
        """
        sections = self._section_names()
        for path, field in self.fields.items():
            section = path.rsplit(".", 1)[0] if "." in path else ""
            pattern = re.compile(
                rf"(?<![A-Za-z]){re.escape(field.spec.label)}(?![A-Za-z])")
            for message in errors:
                prefix = message.split(":", 1)[0] if ":" in message else ""
                if prefix in sections and prefix != section:
                    continue
                if pattern.search(message):
                    field.mark_invalid(True)
                    break

    def _section_names(self) -> set[str]:
        return {p.rsplit(".", 1)[0] for p in self.fields if "." in p}

    def _set_status(self, text: str, *, error: bool = False) -> None:
        self.status_label.configure(
            text=text, text_color=theme.ERROR if error else theme.TEXT_MUTED)

    # ==================================================================
    # Shell contract
    # ==================================================================

    def is_dirty(self) -> bool:
        try:
            return self.to_config() != self._clean_snapshot
        except Exception:                       # noqa: BLE001
            return False

    def reset_to_defaults(self) -> None:
        for field in self.fields.values():
            field.reset_to_default()
        self._loaded_path = None
        self._advanced_locked.set(True)
        self._apply_advanced_lock()
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
