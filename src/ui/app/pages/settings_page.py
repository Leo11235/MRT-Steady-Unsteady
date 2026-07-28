"""
Settings page — edit user preferences.

Storage:
    user_data/default_ui_settings.json   committed baseline (reset target)
    user_data/ui_settings.json           per-user overrides (.gitignored)

Exposed settings:
    default_output_units   (SI / MRT / IMP)  — initial value of the
                                                Steady/Unsteady 'Output
                                                units' dropdown.
    language               (en / fr)         — interface language.
    shortcuts              (dict)            — keyboard-shortcut overrides
                                                for run / save / load /
                                                cancel.  See services/
                                                shortcuts.py.
"""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from src.ui.app import theme, settings as user_settings
from src.ui.app.services import i18n
from src.ui.app.services import shortcuts as sc


OUTPUT_UNIT_OPTIONS = ("SI", "MRT", "IMP")


class SettingsPage(ctk.CTkFrame):
    TITLE = "Settings"

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate
        self._build()

    # ---------------------------------------------------------------------
    # Layout
    # ---------------------------------------------------------------------

    def _build(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.place(relx=0.5, rely=0.05, anchor="n", relwidth=0.7, relheight=0.95)

        ctk.CTkLabel(
            wrap, text=i18n.t("settings.title"),
            font=ctk.CTkFont(size=theme.SIZE_TITLE, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(theme.PAD_M, theme.PAD_L))

        # =============================================================
        # SECTION 1 — Language
        # =============================================================
        ctk.CTkLabel(
            wrap, text=i18n.t("settings.section.language"),
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(theme.PAD_L, theme.PAD_XS))
        ctk.CTkFrame(wrap, height=1, fg_color=theme.DIVIDER) \
            .pack(fill="x", pady=(0, theme.PAD_S))

        self._lang_var = ctk.StringVar()
        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text=i18n.t("settings.language"), width=240,
                     anchor="w").pack(side="left")
        ctk.CTkOptionMenu(
            row, variable=self._lang_var,
            values=[i18n.LANGUAGE_DISPLAY[l] for l in i18n.LANGUAGES],
            dynamic_resizing=False, width=140,
        ).pack(side="left")

        # =============================================================
        # SECTION 2 — Unit system
        # =============================================================
        ctk.CTkLabel(
            wrap, text=i18n.t("settings.section.units"),
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(theme.PAD_L, theme.PAD_XS))
        ctk.CTkFrame(wrap, height=1, fg_color=theme.DIVIDER) \
            .pack(fill="x", pady=(0, theme.PAD_S))

        self._unit_var = ctk.StringVar()
        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text=i18n.t("settings.default_units"), width=240,
                     anchor="w").pack(side="left")
        ctk.CTkOptionMenu(
            row, variable=self._unit_var,
            values=list(OUTPUT_UNIT_OPTIONS),
            dynamic_resizing=False, width=140,
        ).pack(side="left")
        ctk.CTkLabel(
            row,
            text=i18n.t("settings.default_units_hint"),
            text_color=theme.TEXT_FAINT,
            font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
        ).pack(side="left", padx=(theme.PAD_M, 0))

        # =============================================================
        # SECTION 3 — Keyboard shortcuts
        # =============================================================
        ctk.CTkLabel(
            wrap, text=i18n.t("settings.section.keybinds"),
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(theme.PAD_L, theme.PAD_XS))
        ctk.CTkFrame(wrap, height=1, fg_color=theme.DIVIDER) \
            .pack(fill="x", pady=(0, theme.PAD_S))

        # StringVars holding the pretty Tk sequence for each action.
        # Populated by _load_into_form().
        self._shortcut_vars: dict[str, ctk.StringVar] = {
            action: ctk.StringVar() for action in sc.ACTIONS
        }
        # Labels — cached so we can update on Rebind.
        self._shortcut_labels: dict[str, ctk.CTkLabel] = {}

        for action in sc.ACTIONS:
            row = ctk.CTkFrame(wrap, fg_color="transparent")
            row.pack(fill="x", pady=theme.PAD_XS)
            ctk.CTkLabel(
                row, text=i18n.t(sc.ACTION_LABEL_KEYS[action]),
                width=240, anchor="w",
            ).pack(side="left")
            lbl = ctk.CTkLabel(
                row, textvariable=self._shortcut_vars[action],
                width=160, anchor="w",
                font=ctk.CTkFont(family="Consolas", size=theme.SIZE_BODY),
                text_color=theme.TEXT_MUTED,
            )
            lbl.pack(side="left")
            self._shortcut_labels[action] = lbl
            ctk.CTkButton(
                row, text=i18n.t("settings.rebind"), width=110, height=28,
                command=lambda a=action: self._open_rebind_dialog(a),
            ).pack(side="left", padx=theme.PAD_S)

        # ---- Status line -----------------------------------------------
        self._status_label = ctk.CTkLabel(
            wrap, text="", anchor="w",
            text_color=("gray35", "gray65"),
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
        )
        self._status_label.pack(fill="x", pady=(theme.PAD_L, theme.PAD_S))

        # ---- Action bar -------------------------------------------------
        actions = ctk.CTkFrame(wrap, fg_color="transparent")
        actions.pack(fill="x", pady=(theme.PAD_S, 0))

        # Cancel — outlined, unsaved changes discarded, navigate home.
        ctk.CTkButton(
            actions, text=i18n.t("settings.cancel"), width=140, height=40,
            fg_color="transparent",
            text_color=("gray25", "gray75"),
            border_width=1,
            command=self._on_cancel,
        ).pack(side="left")

        # Revert to default — outlined, reset all persisted settings.
        ctk.CTkButton(
            actions, text=i18n.t("settings.reset"), width=200, height=40,
            fg_color="transparent",
            text_color=("gray25", "gray75"),
            border_width=1,
            command=self._on_reset,
        ).pack(side="left", padx=theme.PAD_M)

        # Save — slate-blue accent so it reads as "commit changes"
        # without competing with the green Run buttons or the red
        # Cancel/error styling.  White text (CTkButton default).
        ctk.CTkButton(
            actions, text=i18n.t("settings.save"), width=180, height=40,
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            fg_color=theme.ACCENT_SLATE,
            hover_color=theme.ACCENT_SLATE_HOVER,
            command=self._on_save,
        ).pack(side="right")

    # ---------------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------------

    def on_show(self) -> None:
        # Refresh from disk every time so external edits show up.
        self._load_into_form()
        self._status_label.configure(text="", text_color=theme.TEXT_MUTED)

    def _load_into_form(self) -> None:
        s = user_settings.load_settings()
        val = s.get("default_output_units", "SI")
        if val not in OUTPUT_UNIT_OPTIONS:
            val = "SI"
        self._unit_var.set(val)

        lang = s.get("language", i18n.DEFAULT_LANGUAGE)
        if lang not in i18n.LANGUAGES:
            lang = i18n.DEFAULT_LANGUAGE
        self._lang_var.set(i18n.LANGUAGE_DISPLAY[lang])

        # Populate the shortcut labels with the current bindings, using
        # the humanised "Ctrl+R" form.  The raw Tk sequence is round-
        # tripped through the value of the StringVar itself but we show
        # the pretty form; on Save we parse back.
        bindings = sc.load_bindings()
        self._pending_bindings: dict[str, str] = dict(bindings)
        for action, seq in bindings.items():
            if action in self._shortcut_vars:
                self._shortcut_vars[action].set(sc.humanize(seq))

    # ---------------------------------------------------------------------
    # Actions
    # ---------------------------------------------------------------------

    def _current_form_settings(self) -> dict:
        # Map the pretty display-name back to the wire code.
        display_to_wire = {v: k for k, v in i18n.LANGUAGE_DISPLAY.items()}
        lang = display_to_wire.get(self._lang_var.get(), i18n.DEFAULT_LANGUAGE)
        return {
            "default_output_units": self._unit_var.get(),
            "language":             lang,
        }

    def _on_save(self) -> None:
        try:
            new_settings = self._current_form_settings()
            old_lang = i18n.get_language()
            s = user_settings.load_settings()
            s.update(new_settings)
            user_settings.save_settings(s)
            # Push the new language into i18n immediately so any labels
            # rebuilt this session pick it up.
            i18n.set_language(new_settings["language"])
            # Save keyboard shortcuts and tell the shell to re-bind.
            sc.save_bindings(self._pending_bindings)
            shell = self.winfo_toplevel()
            try:
                shell.refresh_shortcuts()
            except Exception:
                pass
            # If the language changed, force a rebuild of every page so
            # existing labels get retranslated.  CustomTkinter has no
            # live retranslate, so this "destroy + rebuild" is the
            # simplest reliable way.  Then navigate home.
            if new_settings["language"] != old_lang:
                try:
                    shell.rebuild_all_pages()
                    return  # rebuild_all_pages already navigated home
                except Exception:
                    pass
            # No language change (or rebuild failed) — just navigate home.
            self.on_navigate("main")
        except Exception as exc:
            messagebox.showerror("Could not save settings",
                                 f"{type(exc).__name__}: {exc}")

    # ---------------------------------------------------------------------
    # Rebind modal
    # ---------------------------------------------------------------------

    def _open_rebind_dialog(self, action: str) -> None:
        """Modal that captures the next non-modifier key combination the
        user presses and assigns it to `action` (in-memory only; the
        binding isn't persisted until the user hits Save)."""
        win = ctk.CTkToplevel(self)
        win.title(i18n.t("settings.press_key"))
        win.geometry("360x140")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.resizable(False, False)

        ctk.CTkLabel(
            win, text=i18n.t("settings.press_key"),
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
        ).pack(pady=(theme.PAD_L, theme.PAD_S))

        current_pretty = self._shortcut_vars[action].get()
        display = ctk.CTkLabel(
            win, text=f"→  {current_pretty}",
            font=ctk.CTkFont(family="Consolas", size=theme.SIZE_H2),
            text_color=theme.TEXT_MUTED,
        )
        display.pack()

        def on_key(event):
            seq = sc.parse_event(event)
            if not seq:
                # Lone modifier — ignore and keep waiting.
                return "break"
            # Store in-memory; the Save button at the bottom of the page
            # writes it to disk.
            self._pending_bindings[action] = seq
            self._shortcut_vars[action].set(sc.humanize(seq))
            win.destroy()
            return "break"

        # Bind on the modal itself so the shell's global bind_all doesn't
        # fire during capture (Escape would otherwise cancel).
        win.bind("<KeyPress>", on_key)
        win.focus_set()

    def _on_reset(self) -> None:
        if not messagebox.askyesno(
            "Reset all settings",
            "Restore every setting to the values in default_ui_settings.json?"
        ):
            return
        try:
            old_lang = i18n.get_language()
            user_settings.reset_to_defaults()
            self._load_into_form()
            # Apply the default language + shortcuts to the live session
            # so the rebuild picks them up.
            new_lang = user_settings.get("language", i18n.DEFAULT_LANGUAGE)
            if new_lang in i18n.LANGUAGES:
                i18n.set_language(new_lang)
            shell = self.winfo_toplevel()
            try:
                shell.refresh_shortcuts()
            except Exception:
                pass
            # If language changed, force a full retranslate.
            if new_lang != old_lang:
                try:
                    shell.rebuild_all_pages()
                    return
                except Exception:
                    pass
            self._status_label.configure(
                text="All settings reset to defaults.",
                text_color=theme.SUCCESS,
            )
        except Exception as exc:
            messagebox.showerror("Could not reset settings",
                                 f"{type(exc).__name__}: {exc}")

    def _on_cancel(self) -> None:
        """Discard any pending edits and go home.  We deliberately do
        NOT reload the form from disk — the user might come back to
        Settings later; if we cleared the form vars, they'd have to
        re-check their choices.  Since nothing was persisted, cancel
        is effectively free."""
        self.on_navigate("main")
