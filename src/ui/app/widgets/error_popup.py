"""
Modal dialogs for the two ways a run can fail to happen.

  show_error_list()        the config didn't validate, so nothing ran
  show_simulation_error()  the backend ran and raised

Both are modal and centre on the shell.  Both return only once dismissed, so a
caller can treat them as a blocking question.
"""

from __future__ import annotations

import json
from typing import Callable, Optional, Sequence

import customtkinter as ctk

from src.ui.app import theme


def _centre_on_parent(window: ctk.CTkToplevel, parent, width: int, height: int) -> None:
    """Put a dialog in the middle of the app rather than the screen.

    On a multi-monitor setup, screen-centring can land the dialog on a
    different display from the window that raised it.
    """
    window.update_idletasks()
    try:
        root = parent.winfo_toplevel()
        x = root.winfo_rootx() + (root.winfo_width() - width) // 2
        y = root.winfo_rooty() + (root.winfo_height() - height) // 3
        window.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
    except Exception:                           # noqa: BLE001
        window.geometry(f"{width}x{height}")


def _make_modal(parent, title: str, width: int, height: int) -> ctk.CTkToplevel:
    window = ctk.CTkToplevel(parent)
    window.title(title)
    window.transient(parent.winfo_toplevel())
    window.resizable(False, False)
    _centre_on_parent(window, parent, width, height)
    # grab_set has to come after the window is mapped, or the grab fails
    # silently on Windows and the dialog ends up non-modal.
    window.after(10, window.grab_set)
    return window


# =============================================================================
# Validation errors
# =============================================================================

def show_error_list(parent, errors: Sequence[str], *,
                    title: str = "Check these inputs",
                    subtitle: str = "The simulation was not started.") -> None:
    """List what's wrong with a config.  One OK button; nothing ran.

    Deliberately shows every problem at once rather than the first: fixing
    inputs one modal at a time is miserable.
    """
    window = _make_modal(parent, "Invalid configuration", 520, 380)

    ctk.CTkButton(window, text="OK", width=120, height=36,
                  command=window.destroy).pack(side="bottom", pady=theme.PAD_M)

    ctk.CTkLabel(
        window, text=title,
        font=ctk.CTkFont(size=theme.SIZE_H1, weight="bold"),
        text_color=theme.MRT_RED_THEMED,
    ).pack(side="top", pady=(theme.PAD_L, theme.PAD_XS))

    ctk.CTkLabel(
        window, text=f"{subtitle}  {len(errors)} problem"
                     f"{'s' if len(errors) != 1 else ''} found.",
        font=ctk.CTkFont(size=theme.SIZE_BODY),
        text_color=theme.TEXT_MUTED,
    ).pack(side="top", pady=(0, theme.PAD_M))

    body = ctk.CTkScrollableFrame(window, fg_color=("gray92", "gray17"))
    body.pack(side="top", fill="both", expand=True,
              padx=theme.PAD_M, pady=(0, theme.PAD_M))

    for message in errors:
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(row, text="•", width=14, anchor="w",
                     text_color=theme.ERROR).pack(side="left")
        ctk.CTkLabel(row, text=message, anchor="w", justify="left",
                     wraplength=420).pack(side="left", fill="x", expand=True)

    window.wait_window()


# =============================================================================
# Runtime failures
# =============================================================================

def show_simulation_error(
    parent,
    exc: BaseException,
    traceback_text: str,
    config: dict,
    *,
    back_button_text: str,
    back_target: str,
    report_title_prefix: str,
) -> None:
    """The backend raised.  Offer a way back, and a way to report it.

    Reporting hands the bug page a pre-filled title, the traceback, whatever
    the loading screen captured on stdout, and the config as its own field.
    That combination is usually enough to reproduce without a conversation.
    """
    shell = parent.winfo_toplevel()
    window = _make_modal(parent, "Simulation error", 520, 320)

    actions = ctk.CTkFrame(window, fg_color="transparent")
    actions.pack(side="bottom", pady=(0, theme.PAD_M))

    ctk.CTkLabel(
        window, text="The simulation stopped with an error",
        font=ctk.CTkFont(size=theme.SIZE_H1, weight="bold"),
        text_color=theme.MRT_RED_THEMED,
    ).pack(side="top", pady=(theme.PAD_L, theme.PAD_S))

    ctk.CTkLabel(
        window, text="Check the inputs and try again. If they look right, "
                     "this is worth reporting.",
        font=ctk.CTkFont(size=theme.SIZE_BODY),
        wraplength=440, justify="center",
    ).pack(side="top", pady=(0, theme.PAD_M), padx=theme.PAD_M)

    # Fixed height so a long exception scrolls internally instead of pushing
    # the buttons off the bottom of the dialog.
    details = ctk.CTkTextbox(
        window, wrap="word", height=90,
        font=ctk.CTkFont(family="Consolas", size=theme.SIZE_SMALL),
        fg_color=("gray92", "gray17"), text_color=theme.TEXT_MUTED,
    )
    details.pack(side="top", fill="x", padx=theme.PAD_M, pady=(0, theme.PAD_M))
    details.insert("0.0", f"{type(exc).__name__}: {exc}")
    details.configure(state="disabled")

    def go_back() -> None:
        window.destroy()
        shell.go(back_target)

    def go_report() -> None:
        window.destroy()
        loading = getattr(shell, "pages", {}).get("loading")
        terminal = (loading.get_terminal_text() if loading is not None
                    else "(no terminal output captured)")
        try:
            config_json = json.dumps(config, indent=4)
        except (TypeError, ValueError):
            config_json = repr(config)

        try:
            bug_page = shell._ensure_page("bug")    # noqa: SLF001 - shell's own API
            bug_page.prefill(
                title=f"{report_title_prefix}: {type(exc).__name__}",
                diagnostics=f"{terminal}\n\n{traceback_text}",
                config_json=config_json,
            )
        except Exception:                           # noqa: BLE001
            pass        # reporting is best-effort; never block the navigation
        shell.go("bug")

    ctk.CTkButton(actions, text=back_button_text, width=160, height=36,
                  command=go_back).pack(side="left", padx=theme.PAD_S)
    ctk.CTkButton(actions, text="Report a bug", width=160, height=36,
                  fg_color=theme.MRT_RED_THEMED,
                  hover_color=theme.MRT_RED_HOVER,
                  command=go_report).pack(side="left", padx=theme.PAD_S)

    window.wait_window()
