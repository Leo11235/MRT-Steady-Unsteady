"""
Bug-report page.  All the Web3Forms transport lives in
`services.bug_report_client`; this file is now pure UI code.
"""

from __future__ import annotations

import urllib.error

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app.services.bug_report_client import (
    submit_bug_report,
    friendly_network_error_hint,
)


# =============================================================================
# Page
# =============================================================================


class BugReportPage(ctk.CTkFrame):
    TITLE = "Report a bug"

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate
        # Queue of (title, description) to fill in on the next on_show call.
        self._pending_prefill: tuple[str, str] | None = None
        self._build()

    # ---------------------------------------------------------------------
    # Prefill API — used by the error popup so the bug-report comes
    # pre-loaded with the stdout/traceback and the JSON inputs.
    # ---------------------------------------------------------------------

    def prefill(self, title: str, description: str) -> None:
        """Queue a (title, description) pair to apply on the next on_show."""
        self._pending_prefill = (title, description)

    # ---------------------------------------------------------------------
    # Reset — called by the shell when the user hits Home
    # ---------------------------------------------------------------------

    def reset_to_defaults(self) -> None:
        """Empty the form + clear any pending prefill."""
        self._pending_prefill = None
        self._title_var.set("")
        self._desc.delete("0.0", "end")
        self._set_state("idle")

    # ---------------------------------------------------------------------
    # Layout
    # ---------------------------------------------------------------------

    def _build(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.place(relx=0.5, rely=0.05, anchor="n", relwidth=0.75, relheight=0.95)

        ctk.CTkLabel(
            wrap,
            text="Tell us what went wrong.",
            font=ctk.CTkFont(size=theme.SIZE_TITLE, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(theme.PAD_M, theme.PAD_S))

        ctk.CTkLabel(
            wrap,
            text="Reports go straight to the MRT Steady-Unsteady bug tracker. "
                 "You don't have to do anything after clicking Send.",
            text_color=("gray35", "gray65"),
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
            anchor="w",
            justify="left",
            wraplength=700,
        ).pack(fill="x", pady=(0, theme.PAD_L))

        # ---- Title field ------------------------------------------------
        ctk.CTkLabel(wrap, text="Title (optional)",
                     anchor="w").pack(fill="x", pady=(0, 2))
        self._title_var = ctk.StringVar()
        ctk.CTkEntry(wrap, textvariable=self._title_var,
                     placeholder_text="One-line summary").pack(fill="x")

        # ---- Description field ------------------------------------------
        ctk.CTkLabel(wrap, text="Description of the issue",
                     anchor="w").pack(fill="x", pady=(theme.PAD_M, 2))
        self._desc = ctk.CTkTextbox(wrap, wrap="word", height=240)
        self._desc.pack(fill="both", expand=False)

        # ---- Action bar -------------------------------------------------
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
        )
        self._status_label.pack(side="left", padx=(theme.PAD_M, 0))

        # ---- Conditional buttons (built but hidden in idle state) -------
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
        # neither packed yet — _set_state controls that

    # ---------------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------------

    def on_show(self) -> None:
        # Reset on every navigation in so a previous send doesn't leave
        # stale "Return home" buttons hanging around.
        self._set_state("idle")
        # Apply queued prefill if there is one (e.g. came from an error popup).
        if self._pending_prefill is not None:
            pref_title, pref_desc = self._pending_prefill
            self._pending_prefill = None
            self._title_var.set(pref_title)
            self._desc.delete("0.0", "end")
            self._desc.insert("0.0", pref_desc)

    # ---------------------------------------------------------------------
    # State machine
    # ---------------------------------------------------------------------

    def _set_state(self, state: str, message: str = "") -> None:
        """state ∈ {'idle', 'sending', 'error_empty', 'error_send', 'success'}"""
        # hide the extras
        for w in (self._copy_btn, self._home_btn):
            if w.winfo_ismapped():
                w.pack_forget()

        if state == "idle":
            self._status_label.configure(text="", text_color=theme.TEXT_MUTED)
            self._send_btn.configure(state="normal", text="Send report")

        elif state == "sending":
            self._status_label.configure(
                text=message or "Sending …",
                text_color=theme.TEXT_MUTED,
            )
            self._send_btn.configure(state="disabled", text="Sending…")

        elif state == "error_empty":
            self._status_label.configure(
                text=message or "Please write a description of the issue.",
                text_color=theme.ERROR,
            )
            self._send_btn.configure(state="normal", text="Send report")

        elif state == "error_send":
            self._status_label.configure(
                text=message or "Couldn't send the report. "
                                "Copy it below and pass it on by hand.",
                text_color=theme.ERROR,
            )
            self._send_btn.configure(state="normal", text="Try again")
            self._copy_btn.pack(side="left", padx=(0, theme.PAD_S))

        elif state == "success":
            self._status_label.configure(
                text=message or "Report sent — thank you!",
                text_color=theme.SUCCESS,
            )
            self._send_btn.configure(state="disabled", text="Sent ✓")
            self._home_btn.pack(side="left", padx=(0, theme.PAD_S))

    # ---------------------------------------------------------------------
    # Send action
    # ---------------------------------------------------------------------

    def _description(self) -> str:
        return self._desc.get("0.0", "end").strip()

    def _on_send(self) -> None:
        body = self._description()
        if body == "":
            self._set_state("error_empty")
            return

        title = self._title_var.get().strip() or "Bug report"
        self._set_state("sending")
        # Force the UI to repaint before we block on the HTTP call.  The
        # request is short so we don't bother threading it; if it ever
        # grows past a few seconds we should move it to a worker.
        self.update_idletasks()

        try:
            submit_bug_report(title, body)
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
            # Most commonly: access key isn't configured yet.
            self._set_state("error_send", str(exc))
        except Exception as exc:
            self._set_state(
                "error_send",
                f"Couldn't send the report — {type(exc).__name__}: {exc}",
            )

    def _on_copy_to_clipboard(self) -> None:
        title = self._title_var.get().strip() or "(no title)"
        body  = self._description()
        text  = f"Title: {title}\n\n{body}"
        # Tk's clipboard persists after the app closes on Windows/macOS;
        # on Linux it goes away with the app but stays around long enough
        # to paste into something.
        self.clipboard_clear()
        self.clipboard_append(text)
        self._status_label.configure(
            text="Copied. Paste into an email, chat, or GitHub issue.",
            text_color=theme.SUCCESS,
        )
