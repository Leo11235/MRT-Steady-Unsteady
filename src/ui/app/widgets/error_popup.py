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
    """Open the modal error popup.  Blocks input to the underlying
    window until the user clicks a button.

    Parameters
    ----------
    parent            : any widget from which winfo_toplevel() returns the shell.
    exc               : the exception raised by the backend.
    tb                : formatted traceback string.
    cfg               : the config dict that was used; passed to the bug
                        page as its own structured field.
    back_button_text  : label for the "back" action, e.g. "Back to Steady".
    back_target       : shell key to navigate to on Back, e.g. "steady".
    error_title_prefix: e.g. "Error while running steady" — the bug-report
                        title becomes "<prefix>: <ExcName>".
    error_body_prefix : first sentence of the diagnostics block, e.g.
                        "While running steady, the following message stack
                        occurred:".
    """
    shell = parent.winfo_toplevel()

    win = ctk.CTkToplevel(parent)
    win.title("Simulation error")
    win.geometry("480x280")
    win.transient(shell)
    win.grab_set()
    win.resizable(False, False)

    # Pack the buttons FIRST at the bottom of the window so they stay
    # visible no matter how tall the exception-message textbox above
    # them grows.
    actions = ctk.CTkFrame(win, fg_color="transparent")
    actions.pack(side="bottom", pady=(0, theme.PAD_M))

    # Top-down: title, subtitle, then the scrollable exception details.
    ctk.CTkLabel(
        win, text="Error during simulation",
        font=ctk.CTkFont(size=theme.SIZE_H1, weight="bold"),
        text_color=theme.MRT_RED_THEMED,
    ).pack(side="top", pady=(theme.PAD_L, theme.PAD_S))

    ctk.CTkLabel(
        win,
        text="Please verify all your inputs are correct, and run again.",
        font=ctk.CTkFont(size=theme.SIZE_BODY),
        wraplength=420, justify="center",
    ).pack(side="top", pady=(0, theme.PAD_M), padx=theme.PAD_M)

    # Scrollable read-only textbox for the exception message.  Fixed
    # height keeps the dialog compact; anything longer than that
    # scrolls internally instead of pushing the buttons out of view.
    err_box = ctk.CTkTextbox(
        win, wrap="word", height=80,
        font=ctk.CTkFont(family="Consolas", size=theme.SIZE_SMALL),
        fg_color=("gray92", "gray17"),
        text_color=theme.TEXT_MUTED,
    )
    err_box.pack(side="top", fill="x",
                 padx=theme.PAD_M, pady=(0, theme.PAD_M))
    err_box.insert("0.0", f"{type(exc).__name__}: {exc}")
    err_box.configure(state="disabled")

    def go_back():
        win.destroy()
        shell.go(back_target)

    def go_report():
        win.destroy()

        # Grab the loading page's captured terminal output (if any).
        loading = shell.pages.get("loading")
        terminal_text = (loading.get_terminal_text() if loading is not None
                         else "(terminal output unavailable)")

        # Config gets sent as its own structured Web3Forms field, so
        # it does NOT go into the diagnostics blob.
        try:
            cfg_json = json.dumps(cfg, indent=4)
        except Exception:
            cfg_json = repr(cfg)

        title = f"{error_title_prefix}: {type(exc).__name__}"
        diagnostics = (
            f"{error_body_prefix}\n\n"
            f"{terminal_text}\n\n"
            f"{tb}"
        )

        try:
            bug_page = shell._ensure_page("bug")
        except Exception:
            bug_page = None
        if bug_page is not None:
            bug_page.prefill(title=title, diagnostics=diagnostics,
                             config_json=cfg_json)
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
