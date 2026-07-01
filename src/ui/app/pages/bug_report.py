"""
Bug-report page — fill in a title + description, click "Send report",
the app POSTs the report to Web3Forms (which then emails it to the
maintainer).  Fully self-contained: no mail client involved, no user
follow-up needed.

------------------------------------------------------------------------
ONE-TIME SETUP — fill in the access key below.

  1.  Go to https://web3forms.com and click "Get Access Key".
  2.  Enter the email address that should receive bug reports.  Web3Forms
      sends you a confirmation email; click the link inside to verify.
  3.  Once verified, they show you a UUID-shaped access key that looks
      like  "abc12345-6789-4abc-def0-1234567890ab".
  4.  Paste that key into WEB3FORMS_ACCESS_KEY below.

That's it.  Every bug submission from the app will land as an email in
the inbox you registered — with the report title as the subject line and
the description in the body.  Free up to 1000 submissions/month.
------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import customtkinter as ctk

from src.ui.app import theme


# ============================================================================
# Web3Forms configuration — paste your access key here.
# ============================================================================

WEB3FORMS_ACCESS_KEY = "455cf761-6cfd-40a1-8efd-225140582053"
WEB3FORMS_ENDPOINT   = "https://api.web3forms.com/submit"


def _is_form_configured() -> bool:
    """
    Check that WEB3FORMS_ACCESS_KEY has been replaced with something that
    looks like a real UUID.

    We validate FORMAT (uuid-ish, dashes in the right places) rather than
    match a sentinel string, because a global find-and-replace of the
    placeholder would also rewrite any check that depended on it.
    """
    k = WEB3FORMS_ACCESS_KEY
    if not k or "PASTE" in k.upper():
        return False
    # UUIDs are 36 chars including 4 dashes (8-4-4-4-12).
    if len(k) < 30:
        return False
    if k.count("-") != 4:
        return False
    return True


def submit_bug_report(title: str, description: str,
                      timeout_s: float = 15.0) -> None:
    """
    POST the report to Web3Forms.

    Raises:
        RuntimeError  if the access key isn't configured yet, or Web3Forms
                      returns anything other than success.
        URLError      if the network request itself fails (offline, DNS,
                      firewall, etc.).
    """
    if not _is_form_configured():
        raise RuntimeError(
            "Bug-report Web3Forms access key is not configured.  Open "
            "src/ui/app/pages/bug_report.py and paste your access key "
            "into WEB3FORMS_ACCESS_KEY at the top of the file."
        )

    # Web3Forms accepts JSON directly and has good defaults for building the
    # email subject from a `subject` field and body from `message`.
    payload = {
        "access_key":  WEB3FORMS_ACCESS_KEY,
        "subject":     title or "Bug report (no title)",
        "from_name":   "MRT-Sim bug reporter",
        "message":     description,
        # Marks the submission in Web3Forms' dashboard, useful for filtering.
        "botcheck":    "",   # empty honeypot; leave blank
        "_source":     "mrt-sim-ui",
    }
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        WEB3FORMS_ENDPOINT, data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept":       "application/json",
            "User-Agent":   "Mozilla/5.0 (MRT-Sim bug-reporter)",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as response:
        raw = response.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"success": False, "message": raw[:200]}
        # Web3Forms returns 200 with { "success": bool, "message": str }.
        if response.status != 200 or not body.get("success"):
            msg = body.get("message") or f"HTTP {response.status}"
            raise RuntimeError(f"Web3Forms rejected the report: {msg}")


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
            fg_color=("#2a9d8f", "#2a9d8f"),
            hover_color=("#21867a", "#21867a"),
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
            self._status_label.configure(text="", text_color=("gray35", "gray65"))
            self._send_btn.configure(state="normal", text="Send report")

        elif state == "sending":
            self._status_label.configure(
                text=message or "Sending …",
                text_color=("gray35", "gray65"),
            )
            self._send_btn.configure(state="disabled", text="Sending…")

        elif state == "error_empty":
            self._status_label.configure(
                text=message or "Please write a description of the issue.",
                text_color=("#b00020", "#ff6b6b"),
            )
            self._send_btn.configure(state="normal", text="Send report")

        elif state == "error_send":
            self._status_label.configure(
                text=message or "Couldn't send the report. "
                                "Copy it below and pass it on by hand.",
                text_color=("#b00020", "#ff6b6b"),
            )
            self._send_btn.configure(state="normal", text="Try again")
            self._copy_btn.pack(side="left", padx=(0, theme.PAD_S))

        elif state == "success":
            self._status_label.configure(
                text=message or "Report sent — thank you!",
                text_color=("#2a9d8f", "#5eead4"),
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
            reason = getattr(exc, "reason", exc)
            reason_text = str(reason)
            rl = reason_text.lower()
            if "certificate" in rl or "ssl" in rl:
                hint = ("SSL certificate verification failed.  On Windows the "
                        "usual fix is:  pip install --upgrade certifi  "
                        "(or, on macOS, run "
                        "'Install Certificates.command' from your "
                        "Applications/Python folder).")
            elif "getaddrinfo" in rl or "name or service not known" in rl:
                hint = ("DNS lookup failed — confirm you can reach "
                        "api.web3forms.com in a browser.")
            elif "timed out" in rl or "timeout" in rl:
                hint = ("Connection timed out — a firewall or proxy may be "
                        "blocking api.web3forms.com.")
            elif "refused" in rl:
                hint = "Connection refused by api.web3forms.com."
            else:
                hint = "Network error."
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
            text_color=("#2a9d8f", "#5eead4"),
        )
