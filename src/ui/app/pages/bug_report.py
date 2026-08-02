"""Bug-report page.  All Web3Forms transport lives in
`services.bug_report_client`; this file is now pure UI code.
"""

from __future__ import annotations

import re
import urllib.error

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app.services.bug_report_client import (
    submit_bug_report,
    friendly_network_error_hint,
    collect_environment,
)


# Placeholder text that seeds the description box.  Cleared on first
# focus.  If the user submits with the placeholder still present, we
# treat the description as empty.
_DESC_PLACEHOLDER = (
    "[What were you trying to do?]\n"
    "[Is this reproducible, or a one-off?]"
)


class BugReportPage(ctk.CTkFrame):
    TITLE = "Report a bug"

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate
        # (title, diagnostics, config_json) queued for the next on_show.
        self._pending_prefill: tuple[str, str, str] | None = None
        self._desc_has_placeholder = True
        self._build()

    # ---------------------------------------------------------------------
    # Prefill API — called by the error popup so the bug page opens
    # pre-loaded with the traceback + terminal output + config JSON.
    # ---------------------------------------------------------------------

    def prefill(self, title: str = "", diagnostics: str = "",
                config_json: str = "") -> None:
        """Queue values to apply on the next on_show."""
        self._pending_prefill = (title, diagnostics, config_json)

    # ---------------------------------------------------------------------
    # Reset — called by the shell when the user hits Home.
    # ---------------------------------------------------------------------

    def reset_to_defaults(self) -> None:
        self._pending_prefill = None
        self._name_var.set("")
        self._email_var.set("")
        self._title_var.set("")
        self._desc.delete("0.0", "end")
        self._install_desc_placeholder()
        self._set_diagnostics("")
        self._config_json = ""
        self._set_state("idle")

    # ---------------------------------------------------------------------
    # Layout
    # ---------------------------------------------------------------------

    def _build(self) -> None:
        # Whole page is scrollable so the diagnostics box + long forms
        # don't get cropped on small displays.
        wrap = ctk.CTkScrollableFrame(self, fg_color="transparent")
        wrap.place(relx=0.5, rely=0.02, anchor="n",
                   relwidth=0.78, relheight=0.96)

        ctk.CTkLabel(
            wrap, text="Tell us what went wrong.",
            font=ctk.CTkFont(size=theme.SIZE_TITLE, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(theme.PAD_M, theme.PAD_S))

        ctk.CTkLabel(
            wrap,
            text="Reports go straight to the MRT Steady-Unsteady bug "
                 "tracker. You don't have to do anything after clicking "
                 "Send.",
            text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
            anchor="w", justify="left", wraplength=740,
        ).pack(fill="x", pady=(0, theme.PAD_L))

        # ---- User info -------------------------------------------------
        self._section_header(wrap, "User info")

        self._name_var  = ctk.StringVar()
        self._email_var = ctk.StringVar()

        self._labeled_entry(wrap, "Name (optional)",  self._name_var,
                            placeholder="Who's filing this report?")
        self._labeled_entry(wrap, "Email (optional)", self._email_var,
                            placeholder="Where should we reply if we "
                                        "need more info?")

        # ---- Bug description ------------------------------------------
        self._section_header(wrap, "Bug description")

        self._title_var = ctk.StringVar()
        self._labeled_entry(wrap, "Title (optional)", self._title_var,
                            placeholder="One-line summary")

        ctk.CTkLabel(
            wrap, text="Description",
            anchor="w",
        ).pack(fill="x", pady=(theme.PAD_M, 2))

        self._desc = ctk.CTkTextbox(wrap, wrap="word", height=160)
        self._desc.pack(fill="x")
        self._desc.bind("<FocusIn>",  self._on_desc_focus_in)
        self._desc.bind("<FocusOut>", self._on_desc_focus_out)
        self._install_desc_placeholder()

        # ---- Diagnostics (hidden if empty) ----------------------------
        # Built once, packed/unpacked by _set_diagnostics().
        self._diag_container = ctk.CTkFrame(wrap, fg_color="transparent")

        self._section_header(self._diag_container,
                             "Diagnostics (auto-collected)")

        ctk.CTkLabel(
            self._diag_container,
            text="Terminal output and traceback from the failed run. "
                 "Read-only.",
            text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
            anchor="w", justify="left", wraplength=740,
        ).pack(fill="x", pady=(0, 2))

        self._diag = ctk.CTkTextbox(
            self._diag_container, wrap="none", height=220,
            font=ctk.CTkFont(family="Consolas", size=theme.SIZE_SMALL),
            fg_color=("gray92", "gray17"),
            text_color=theme.TEXT_MUTED,
        )
        self._diag.pack(fill="x")
        # Not packed yet — happens dynamically in _set_diagnostics.
        # Do NOT pack self._diag_container here.

        self._config_json = ""   # populated by prefill; sent as its own field

        # ---- Environment (always shown) -------------------------------
        self._section_header(wrap, "Environment")
        self._env = collect_environment()
        env_text = (
            f"App version:    {self._env.get('app_version', '?')}\n"
            f"Build:          {self._env.get('build',       '?')}\n"
            f"OS:             {self._env.get('os',          '?')}\n"
            f"Python:         {self._env.get('python',      '?')}"
        )
        ctk.CTkLabel(
            wrap, text=env_text, anchor="w", justify="left",
            font=ctk.CTkFont(family="Consolas", size=theme.SIZE_SMALL),
            text_color=theme.TEXT_MUTED,
        ).pack(fill="x", pady=(2, theme.PAD_L))

        # ---- Action bar -----------------------------------------------
        action_row = ctk.CTkFrame(wrap, fg_color="transparent")
        action_row.pack(fill="x", pady=(theme.PAD_M, 0))

        self._send_btn = ctk.CTkButton(
            action_row, text="Send report", width=160, height=40,
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            fg_color=theme.ACCENT_SLATE,
            hover_color=theme.ACCENT_SLATE_HOVER,
            command=self._on_send,
        )
        self._send_btn.pack(side="left")

        self._status_label = ctk.CTkLabel(
            action_row, text="", anchor="w",
            font=ctk.CTkFont(size=theme.SIZE_BODY),
            wraplength=520, justify="left",
        )
        self._status_label.pack(side="left", padx=(theme.PAD_M, 0),
                                fill="x", expand=True)

        # ---- Conditional buttons (built but hidden in idle state) -----
        self._extra_row = ctk.CTkFrame(wrap, fg_color="transparent")
        self._extra_row.pack(fill="x", pady=(theme.PAD_S, 0))

        self._copy_btn = ctk.CTkButton(
            self._extra_row, text="Copy report to clipboard", width=200,
            command=self._on_copy_to_clipboard,
        )
        self._home_btn = ctk.CTkButton(
            self._extra_row, text="Return to home", width=200,
            command=lambda: self.on_navigate("main"),
        )

    # ---------------------------------------------------------------------
    # Small layout helpers
    # ---------------------------------------------------------------------

    def _section_header(self, parent, text: str) -> None:
        """A muted-red divider header for a form section."""
        ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            text_color=theme.MRT_RED_THEMED,
            anchor="w",
        ).pack(fill="x", pady=(theme.PAD_L, theme.PAD_XS))
        ctk.CTkFrame(parent, height=1, fg_color=theme.TEXT_FAINT) \
            .pack(fill="x", pady=(0, theme.PAD_S))

    def _labeled_entry(self, parent, label_text: str,
                       variable: ctk.StringVar,
                       placeholder: str = "") -> None:
        ctk.CTkLabel(parent, text=label_text, anchor="w") \
            .pack(fill="x", pady=(theme.PAD_XS, 2))
        ctk.CTkEntry(parent, textvariable=variable,
                     placeholder_text=placeholder).pack(fill="x")

    # ---------------------------------------------------------------------
    # Description placeholder handling
    # ---------------------------------------------------------------------

    def _install_desc_placeholder(self) -> None:
        self._desc.delete("0.0", "end")
        self._desc.insert("0.0", _DESC_PLACEHOLDER)
        try:
            self._desc.configure(text_color=theme.TEXT_FAINT)
        except Exception:
            pass
        self._desc_has_placeholder = True

    def _on_desc_focus_in(self, _event=None) -> None:
        if self._desc_has_placeholder:
            self._desc.delete("0.0", "end")
            try:
                self._desc.configure(text_color=theme.TEXT_NORMAL)
            except Exception:
                # Falls back if TEXT_NORMAL doesn't exist; visible either way.
                pass
            self._desc_has_placeholder = False

    def _on_desc_focus_out(self, _event=None) -> None:
        if not self._desc.get("0.0", "end").strip():
            self._install_desc_placeholder()

    def _description_actual(self) -> str:
        """The user's description with the placeholder text treated as empty."""
        if self._desc_has_placeholder:
            return ""
        return self._desc.get("0.0", "end").strip()

    # ---------------------------------------------------------------------
    # Diagnostics visibility + content
    # ---------------------------------------------------------------------

    def _set_diagnostics(self, text: str) -> None:
        """Populate the read-only diagnostics box, or hide the whole
        section if there's nothing to show."""
        # Enable temporarily so we can rewrite content.
        self._diag.configure(state="normal")
        self._diag.delete("0.0", "end")
        if text:
            self._diag.insert("0.0", text)
            if not self._diag_container.winfo_ismapped():
                self._diag_container.pack(fill="x",
                                          pady=(theme.PAD_L, theme.PAD_S))
        else:
            if self._diag_container.winfo_ismapped():
                self._diag_container.pack_forget()
        self._diag.configure(state="disabled")

    # ---------------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------------

    def on_show(self) -> None:
        self._set_state("idle")

        if self._pending_prefill is not None:
            pref_title, pref_diag, pref_cfg = self._pending_prefill
            self._pending_prefill = None
            self._title_var.set(pref_title)
            self._set_diagnostics(pref_diag)
            self._config_json = pref_cfg
        else:
            # Manual entry from Home — no auto-diagnostics.
            self._set_diagnostics("")
            self._config_json = ""

    # ---------------------------------------------------------------------
    # State machine
    # ---------------------------------------------------------------------

    def _set_state(self, state: str, message: str = "") -> None:
        """state in {'idle', 'sending', 'error_empty', 'error_send',
        'error_email', 'success'}."""
        for w in (self._copy_btn, self._home_btn):
            if w.winfo_ismapped():
                w.pack_forget()

        if state == "idle":
            self._status_label.configure(text="", text_color=theme.TEXT_MUTED)
            self._send_btn.configure(state="normal", text="Send report")

        elif state == "sending":
            self._status_label.configure(
                text=message or "Sending...",
                text_color=theme.TEXT_MUTED,
            )
            self._send_btn.configure(state="disabled", text="Sending...")

        elif state == "error_empty":
            self._status_label.configure(
                text=message or ("Please describe the bug, or run the sim "
                                 "so it can auto-fill diagnostics."),
                text_color=theme.ERROR,
            )
            self._send_btn.configure(state="normal", text="Send report")

        elif state == "error_email":
            self._status_label.configure(
                text=message or "That email address doesn't look valid.",
                text_color=theme.ERROR,
            )
            self._send_btn.configure(state="normal", text="Send report")

        elif state == "error_send":
            self._status_label.configure(
                text=message or ("Couldn't send the report. Copy it below "
                                 "and pass it on by hand."),
                text_color=theme.ERROR,
            )
            self._send_btn.configure(state="normal", text="Try again")
            self._copy_btn.pack(side="left", padx=(0, theme.PAD_S))

        elif state == "success":
            self._status_label.configure(
                text=message or "Report sent. Thank you!",
                text_color=theme.SUCCESS,
            )
            self._send_btn.configure(state="disabled", text="Sent")
            self._home_btn.pack(side="left", padx=(0, theme.PAD_S))

    # ---------------------------------------------------------------------
    # Validation + Send
    # ---------------------------------------------------------------------

    _EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

    def _validate_email(self, email: str) -> bool:
        """Light shape check; empty is fine."""
        if not email:
            return True
        return bool(self._EMAIL_RE.match(email))

    def _diagnostics_text(self) -> str:
        """Return the diagnostics content (read-only widget) as a string."""
        return self._diag.get("0.0", "end").strip()

    def _on_send(self) -> None:
        name  = self._name_var.get().strip()
        email = self._email_var.get().strip()
        title = self._title_var.get().strip()
        desc  = self._description_actual()
        diag  = self._diagnostics_text()
        cfg   = self._config_json

        # Validation: if there's no diagnostics AND no description,
        # there's literally nothing to report.
        if not desc and not diag:
            self._set_state("error_empty")
            return

        # Email shape check.
        if not self._validate_email(email):
            self._set_state("error_email")
            return

        self._set_state("sending")
        # Force UI to repaint before the blocking HTTP call.
        self.update_idletasks()

        try:
            submit_bug_report(
                title=title,
                description=desc,
                name=name,
                email=email,
                diagnostics=diag,
                config_json=cfg,
                env=self._env,
            )
            self._set_state("success")
        except urllib.error.HTTPError as exc:
            self._set_state(
                "error_send",
                f"Server rejected the report: HTTP {exc.code} {exc.reason}",
            )
        except urllib.error.URLError as exc:
            reason_text = str(getattr(exc, "reason", exc))
            hint = friendly_network_error_hint(reason_text)
            self._set_state(
                "error_send",
                f"{hint}\n(Detail: {reason_text})",
            )
        except RuntimeError as exc:
            self._set_state("error_send", str(exc))
        except Exception as exc:
            self._set_state(
                "error_send",
                f"Couldn't send the report. {type(exc).__name__}: {exc}",
            )

    def _on_copy_to_clipboard(self) -> None:
        title = self._title_var.get().strip() or "(no title)"
        desc  = self._description_actual() or "(no description)"
        diag  = self._diagnostics_text()   or "(no diagnostics)"
        cfg   = self._config_json          or "(no config)"
        env   = self._env
        text = (
            f"Title: {title}\n\n"
            f"Reporter: {self._name_var.get().strip() or '(anonymous)'}\n"
            f"Email:    {self._email_var.get().strip() or '(none)'}\n\n"
            f"Environment:\n"
            f"  App version: {env.get('app_version', '?')}\n"
            f"  Build:       {env.get('build',       '?')}\n"
            f"  OS:          {env.get('os',          '?')}\n"
            f"  Python:      {env.get('python',      '?')}\n\n"
            f"Description:\n{desc}\n\n"
            f"Diagnostics:\n{diag}\n\n"
            f"Config:\n{cfg}\n"
        )
        self.clipboard_clear()
        self.clipboard_append(text)
        self._status_label.configure(
            text="Copied. Paste into an email, chat, or GitHub issue.",
            text_color=theme.SUCCESS,
        )
