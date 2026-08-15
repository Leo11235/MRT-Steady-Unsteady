"""
User preferences.

Three groups: unit system, run behaviour, keyboard shortcuts. Every change is
held in the form until Save, so Cancel really does discard.

There is no appearance setting: the app is dark-only, and every colour in
theme.py is tuned against that background.

This page owns its own navigation via the buttons at the bottom, which is why
the shell suppresses the Home button here.
"""

from __future__ import annotations

import customtkinter as ctk

from src.ui.app import settings as user_settings
from src.ui.app import theme
from src.ui.app.services import shortcuts
from src.ui.app.widgets.help_icon import HelpIcon

UNIT_SYSTEMS = ("SI", "IMP", "MRT")

_LABEL_W = 260
_CONTROL_W = 200


class SettingsPage(ctk.CTkFrame):
    TITLE = "Settings"

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate

        self.units_var = ctk.StringVar()
        self.autosave_var = ctk.BooleanVar()
        # Edited bindings live here until Save, so Cancel can walk away.
        self._bindings: dict[str, str] = {}
        self._binding_labels: dict[str, ctk.CTkLabel] = {}

        self._build()
        self._load()

    # ==================================================================
    # Layout
    # ==================================================================

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="User preferences", anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_HERO, weight="bold")).grid(
            row=0, column=0, sticky="ew", padx=theme.PAD_XL,
            pady=(theme.PAD_XL, theme.PAD_L))

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew",
                  padx=theme.PAD_XL, pady=(0, theme.PAD_M))

        self._build_units(body)
        self._build_behaviour(body)
        self._build_shortcuts(body)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew",
                    padx=theme.PAD_XL, pady=(0, theme.PAD_XL))

        ctk.CTkButton(footer, text="Cancel", width=170, height=44,
                      fg_color="transparent", border_width=1,
                      text_color=theme.TEXT_MUTED, hover_color=theme.CARD_HOVER,
                      font=ctk.CTkFont(size=theme.SIZE_BODY),
                      command=self._on_cancel).pack(side="left")
        ctk.CTkButton(footer, text="Reset all to defaults", width=220, height=44,
                      fg_color="transparent", border_width=1,
                      text_color=theme.TEXT_MUTED, hover_color=theme.CARD_HOVER,
                      font=ctk.CTkFont(size=theme.SIZE_BODY),
                      command=self._on_reset).pack(side="left", padx=theme.PAD_S)
        ctk.CTkButton(footer, text="Save", width=200, height=44,
                      fg_color=theme.ACCENT_SLATE,
                      hover_color=theme.ACCENT_SLATE_HOVER,
                      font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
                      command=self._on_save).pack(side="right")

        self._status = ctk.CTkLabel(
            footer, text="", anchor="e", text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL))
        self._status.pack(side="right", padx=theme.PAD_M)

    def _section(self, parent, title: str) -> ctk.CTkFrame:
        ctk.CTkLabel(parent, text=title, anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_H1, weight="bold")).pack(
            fill="x", pady=(theme.PAD_L, theme.PAD_XS))
        rule = ctk.CTkFrame(parent, height=1, fg_color=theme.DIVIDER)
        rule.pack(fill="x", pady=(0, theme.PAD_S))
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x")
        return frame

    def _row(self, parent, label: str) -> ctk.CTkFrame:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text=label, width=_LABEL_W, anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_BODY)).pack(
            side="left", padx=(0, theme.PAD_S))
        return row

    # ---- groups -------------------------------------------------------

    def _build_units(self, parent) -> None:
        section = self._section(parent, "Unit system")
        row = self._row(section, "Default program units")
        ctk.CTkOptionMenu(row, variable=self.units_var, values=list(UNIT_SYSTEMS),
                          width=_CONTROL_W).pack(side="left")
        ctk.CTkLabel(
            row,
            text="input forms open in it, results pages start on it",
            text_color=theme.TEXT_FAINT,
            font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic")).pack(
            side="left", padx=(theme.PAD_M, 0))

    def _build_behaviour(self, parent) -> None:
        section = self._section(parent, "Running simulations")
        row = self._row(section, "Auto-save inputs on run")
        ctk.CTkCheckBox(row, text="", variable=self.autosave_var,
                        width=24).pack(side="left")
        ctk.CTkLabel(
            row,
            text="write the inputs to a preset automatically instead of "
                 "prompting for a name",
            text_color=theme.TEXT_FAINT, wraplength=520, justify="left",
            font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic")).pack(
            side="left", padx=(theme.PAD_S, 0))

    def _build_shortcuts(self, parent) -> None:
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", pady=(theme.PAD_L, theme.PAD_XS))
        ctk.CTkLabel(header, text="Keyboard shortcuts", anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_H1, weight="bold")).pack(
            side="left")
        HelpIcon(header,
                 "These work anywhere in the app. Run, Save and Load act on "
                 "whichever input page is open; Cancel only does anything "
                 "while a simulation is running, and needs two presses to "
                 "confirm.").pack(side="left", padx=(theme.PAD_XS, 0))

        rule = ctk.CTkFrame(parent, height=1, fg_color=theme.DIVIDER)
        rule.pack(fill="x", pady=(0, theme.PAD_S))
        section = ctk.CTkFrame(parent, fg_color="transparent")
        section.pack(fill="x")

        for action in shortcuts.ACTIONS:
            label = shortcuts.ACTION_LABELS.get(action, action)
            if action == "cancel":
                label += "  (double-press)"
            row = self._row(section, label)

            binding = ctk.CTkLabel(
                row, text="", width=140, anchor="w",
                text_color=theme.TEXT_MUTED,
                font=ctk.CTkFont(family="Consolas", size=theme.SIZE_BODY))
            binding.pack(side="left")
            self._binding_labels[action] = binding

            ctk.CTkButton(row, text="Rebind…", width=140, height=32,
                          font=ctk.CTkFont(size=theme.SIZE_BODY),
                          command=lambda a=action: self._rebind(a)).pack(side="left")

    # ==================================================================
    # Form state
    # ==================================================================

    def _load(self) -> None:
        """Populate from the saved settings. Called on build and on every show."""
        current = user_settings.load_settings()
        units = current.get("default_program_units", "SI")
        self.units_var.set(units if units in UNIT_SYSTEMS else "SI")
        self.autosave_var.set(bool(current.get("default_auto_save_inputs", True)))

        self._bindings = shortcuts.load_bindings()
        self._refresh_bindings()
        self._set_status("")

    def _refresh_bindings(self) -> None:
        for action, label in self._binding_labels.items():
            label.configure(text=shortcuts.humanize(self._bindings.get(action, "")))

    def _rebind(self, action: str) -> None:
        from src.ui.app.widgets.key_capture import capture_key

        sequence = capture_key(
            self, shortcuts.ACTION_LABELS.get(action, action))
        if not sequence:
            return

        # Two actions on one key means the second binding silently never
        # fires, so say which one is in the way rather than letting it break
        # quietly.
        clash = next((other for other, seq in self._bindings.items()
                      if seq == sequence and other != action), None)
        if clash:
            self._set_status(
                f"{shortcuts.humanize(sequence)} is already "
                f"{shortcuts.ACTION_LABELS.get(clash, clash)}", error=True)
            return

        self._bindings[action] = sequence
        self._refresh_bindings()
        self._set_status(f"{shortcuts.ACTION_LABELS.get(action, action)} "
                         f"is now {shortcuts.humanize(sequence)} — not saved yet")

    # ==================================================================
    # Actions
    # ==================================================================

    def _on_save(self) -> None:
        current = user_settings.load_settings()
        current["default_program_units"] = self.units_var.get()
        current["default_auto_save_inputs"] = bool(self.autosave_var.get())
        current["shortcuts"] = dict(self._bindings)
        user_settings.save_settings(current)

        # Shortcuts take effect immediately. The unit default only affects
        # pages built from here on.
        shell = self.winfo_toplevel()
        if hasattr(shell, "refresh_shortcuts"):
            try:
                shell.refresh_shortcuts()
            except Exception:                   # noqa: BLE001
                pass

        self._set_status("Saved")
        self.on_navigate("main")

    def _on_cancel(self) -> None:
        self._load()            # throw away the edits
        self.on_navigate("main")

    def _on_reset(self) -> None:
        user_settings.reset_to_defaults()
        self._load()
        shell = self.winfo_toplevel()
        if hasattr(shell, "refresh_shortcuts"):
            try:
                shell.refresh_shortcuts()
            except Exception:                   # noqa: BLE001
                pass
        self._set_status("Reset to defaults")

    def _set_status(self, text: str, *, error: bool = False) -> None:
        self._status.configure(
            text=text, text_color=theme.ERROR if error else theme.TEXT_MUTED)

    # ==================================================================
    # Shell contract
    # ==================================================================

    def on_show(self) -> None:
        # Re-read every time: a setting may have changed elsewhere, and any
        # abandoned edits from a previous visit should not survive.
        self._load()
