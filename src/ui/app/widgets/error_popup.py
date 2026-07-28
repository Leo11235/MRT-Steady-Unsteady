"""Shared "Error during simulation" popup.

Both Steady and Unsteady pages had a near-identical copy of this dialog.
This module owns the layout; the caller supplies the back-button target
and the details for the bug-report pre-fill.
"""

from __future__ import annotations

import json
from typing import Callable

import customtkinter as ctk

from src.ui.app import theme


def show_simulation_error(
    parent,
    exc: BaseException,
    tb: str,
    cfg: dict,
    *,
    back_button_text: str,
    back_target: str,
    error_title_prefix: str,
    error_body_prefix: str,
) -> None:
    """
    Open the modal error popup.  Blocks input to the underlying window
    until the user clicks a button.

    Parameters
    ----------
    parent            : any widget from which winfo_toplevel() returns the shell.
    exc               : the exception raised by the backend.
    tb                : formatted traceback string.
    cfg               : the config dict that was used; pretty-printed into
                        the bug-report pre-fill body.
    back_button_text  : label for the "back" action, e.g. "Back to Steady".
    back_target       : shell key to navigate to on Back, e.g. "steady".
    error_title_prefix: e.g. "Error while running steady" — the bug-report
                        title becomes "<prefix>: <ExcName>".
    error_body_prefix : first sentence of the bug-report body, e.g.
                        "While running steady, the following message stack
                        occurred:".
    """
    shell = parent.winfo_toplevel()

    win = ctk.CTkToplevel(parent)
    win.title("Simulation error")
    win.geometry("480x230")
    win.transient(shell)
    win.grab_set()
    win.resizable(False, False)

    ctk.CTkLabel(
        win, text="Error during simulation",
        font=ctk.CTkFont(size=theme.SIZE_H1, weight="bold"),
        text_color=theme.MRT_RED_THEMED,
    ).pack(pady=(theme.PAD_L, theme.PAD_S))

    ctk.CTkLabel(
        win,
        text="Please verify all your inputs are correct, and run again.",
        font=ctk.CTkFont(size=theme.SIZE_BODY),
        wraplength=420, justify="center",
    ).pack(pady=(0, theme.PAD_M), padx=theme.PAD_M)

    ctk.CTkLabel(
        win,
        text=f"{type(exc).__name__}: {exc}",
        text_color=theme.TEXT_MUTED,
        font=ctk.CTkFont(family="Consolas", size=theme.SIZE_SMALL),
        wraplength=420, justify="center",
    ).pack(pady=(0, theme.PAD_L), padx=theme.PAD_M)

    actions = ctk.CTkFrame(win, fg_color="transparent")
    actions.pack(pady=(0, theme.PAD_M))

    def go_back():
        win.destroy()
        shell.go(back_target)

    def go_report():
        win.destroy()
        loading = shell.pages.get("loading")
        terminal_text = (loading.get_terminal_text() if loading is not None
                         else "(terminal output unavailable)")
        try:
            cfg_json = json.dumps(cfg, indent=4)
        except Exception:
            cfg_json = repr(cfg)

        # Include the app version at the top of every auto-generated
        # bug body so triaging against a specific release is trivial.
        try:
            from src.ui.app.version import VERSION as _APP_VERSION
        except Exception:
            _APP_VERSION = "unknown"

        title = f"{error_title_prefix}: {type(exc).__name__}"
        body = (
            f"App version: {_APP_VERSION}\n\n"
            f"{error_body_prefix}\n\n"
            f"{terminal_text}\n\n"
            f"{tb}\n"
            "The following simulation inputs were used:\n\n"
            f"{cfg_json}\n"
        )
        try:
            bug_page = shell._ensure_page("bug")
        except Exception:
            bug_page = None
        if bug_page is not None:
            bug_page.prefill(title, body)
        shell.go("bug")

    ctk.CTkButton(
        actions, text=back_button_text, width=160, height=36,
        command=go_back,
    ).pack(side="left", padx=theme.PAD_S)

    ctk.CTkButton(
        actions, text="Report a bug", width=160, height=36,
        fg_color=theme.MRT_RED_THEMED,
        hover_color=theme.MRT_RED_HOVER,
        command=go_report,
    ).pack(side="left", padx=theme.PAD_S)
