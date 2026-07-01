"""
Settings page — edit user preferences.

Storage:
    user_data/default_ui_settings.json   committed baseline (reset target)
    user_data/ui_settings.json           per-user overrides (.gitignored)

Currently exposed setting:
    default_output_units   (SI / MRT / IMP)  ← used as the initial value
                                                of the Output Units dropdown
                                                on the Steady page.
"""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from src.ui.app import theme, settings as user_settings


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
            wrap, text="User preferences",
            font=ctk.CTkFont(size=theme.SIZE_TITLE, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(theme.PAD_M, theme.PAD_S))

        ctk.CTkLabel(
            wrap,
            text="These settings persist between launches.\n"
                 "They live in user_data/ui_settings.json and are per-user "
                 "(not committed to the repo).",
            text_color=("gray35", "gray65"),
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
            anchor="w",
            justify="left",
        ).pack(fill="x", pady=(0, theme.PAD_L))

        # ---- Default output units --------------------------------------
        self._unit_var = ctk.StringVar()
        row = ctk.CTkFrame(wrap, fg_color="transparent")
        row.pack(fill="x", pady=theme.PAD_XS)
        ctk.CTkLabel(row, text="Default output units", width=240,
                     anchor="w").pack(side="left")
        ctk.CTkOptionMenu(
            row, variable=self._unit_var,
            values=list(OUTPUT_UNIT_OPTIONS),
            dynamic_resizing=False, width=140,
        ).pack(side="left")
        ctk.CTkLabel(
            row,
            text="(this is what the Steady page's 'Output units' dropdown "
                 "starts on)",
            text_color=("gray40", "gray60"),
            font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
        ).pack(side="left", padx=(theme.PAD_M, 0))

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

        ctk.CTkButton(
            actions, text="Save", width=140, height=36,
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            fg_color=("#2a9d8f", "#2a9d8f"),
            hover_color=("#21867a", "#21867a"),
            command=self._on_save,
        ).pack(side="left")

        ctk.CTkButton(
            actions, text="Reset all to defaults", width=200, height=36,
            fg_color="transparent",
            text_color=("gray25", "gray75"),
            border_width=1,
            command=self._on_reset,
        ).pack(side="left", padx=theme.PAD_M)

        ctk.CTkButton(
            actions, text="Cancel", width=120, height=36,
            fg_color="transparent",
            text_color=("gray25", "gray75"),
            border_width=1,
            command=lambda: self.on_navigate("main"),
        ).pack(side="right")

    # ---------------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------------

    def on_show(self) -> None:
        # Refresh from disk every time so external edits show up.
        self._load_into_form()
        self._status_label.configure(text="", text_color=("gray35", "gray65"))

    def _load_into_form(self) -> None:
        s = user_settings.load_settings()
        val = s.get("default_output_units", "SI")
        if val not in OUTPUT_UNIT_OPTIONS:
            val = "SI"
        self._unit_var.set(val)

    # ---------------------------------------------------------------------
    # Actions
    # ---------------------------------------------------------------------

    def _current_form_settings(self) -> dict:
        return {
            "default_output_units": self._unit_var.get(),
        }

    def _on_save(self) -> None:
        try:
            s = user_settings.load_settings()
            s.update(self._current_form_settings())
            user_settings.save_settings(s)
            self._status_label.configure(
                text=f"Saved to {user_settings.user_settings_path()}",
                text_color=("#2a9d8f", "#5eead4"),
            )
        except Exception as exc:
            messagebox.showerror("Could not save settings",
                                 f"{type(exc).__name__}: {exc}")

    def _on_reset(self) -> None:
        if not messagebox.askyesno(
            "Reset all settings",
            "Restore every setting to the values in default_ui_settings.json?"
        ):
            return
        try:
            user_settings.reset_to_defaults()
            self._load_into_form()
            self._status_label.configure(
                text="All settings reset to defaults.",
                text_color=("#2a9d8f", "#5eead4"),
            )
        except Exception as exc:
            messagebox.showerror("Could not reset settings",
                                 f"{type(exc).__name__}: {exc}")
