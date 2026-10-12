"""
The "it didn't get there" modal.

A fuel-mass convergence run searches for the fuel mass that puts the rocket at
the target apogee. Sometimes no such mass exists: even with the smallest port
the engine allows, the rocket comes up short. The run still SUCCEEDS — it
produces a complete, valid result — so nothing else in the pipeline flags it,
and the results page looks exactly like a converged one until you read the
apogee number.

This says so before the results appear, and offers the two things you'd
actually want next: go back and change the inputs, or look at the result
anyway.

The backend sets `rocket_parameters.target_apogee_reached`. That's a separate
key from `reached_apogee`, which is the altitude actually achieved.

Neither number is necessarily in SI. steady_main rewrites the whole results
dict into MRT when the run's output_units said so, which is why both altitudes
arrive with a `native` system rather than as assumed metres.
"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from src.common import variable_conversions as vc
from src.ui.app import theme
from src.ui.app.widgets.kv_row import format_scalar

_W, _H = 560, 340


def show_apogee_shortfall(parent, *, reached: Optional[float],
                          target: Optional[float],
                          system: str = "SI",
                          native: str = "SI") -> bool:
    """Report a convergence run that never reached the target.

    `reached` and `target` are in `native`'s units, not necessarily SI;
    `system` is what to display them in.

    Returns True to open the results anyway, False to go back to the inputs.
    Closing the window counts as going back: the run is still saved, so the
    conservative default is the one that lets you fix something.
    """
    window = ctk.CTkToplevel(parent)
    window.title("Target apogee not reached")
    window.transient(parent.winfo_toplevel())
    window.resizable(False, False)
    _centre(window, parent)
    window.after(10, window.grab_set)

    choice = {"show_results": False}

    # Buttons first so a long message can never push them off the bottom.
    actions = ctk.CTkFrame(window, fg_color="transparent")
    actions.pack(side="bottom", pady=(0, theme.PAD_L))

    ctk.CTkLabel(window, text="The rocket did not reach the target apogee",
                 font=ctk.CTkFont(size=theme.SIZE_H1, weight="bold"),
                 text_color=theme.WARNING_STRONG).pack(
        pady=(theme.PAD_XL, theme.PAD_S), padx=theme.PAD_L)

    ctk.CTkLabel(
        window,
        text="Convergence searches for the fuel mass that hits your target. "
             "This configuration can't get there: even at the smallest port "
             "the settings allow, it falls short.",
        text_color=theme.TEXT_MUTED, wraplength=_W - 2 * theme.PAD_XL,
        justify="left",
        font=ctk.CTkFont(size=theme.SIZE_BODY)).pack(
        padx=theme.PAD_XL, pady=(0, theme.PAD_M))

    numbers = _summary(reached, target, system, native)
    if numbers:
        ctk.CTkLabel(window, text=numbers, justify="left",
                     font=ctk.CTkFont(family="Consolas",
                                      size=theme.SIZE_BODY)).pack(
            padx=theme.PAD_XL, pady=(0, theme.PAD_M))

    ctk.CTkLabel(
        window,
        text="More thrust, less dry mass or a lower target would all help.",
        text_color=theme.TEXT_FAINT, wraplength=_W - 2 * theme.PAD_XL,
        justify="left",
        font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic")).pack(
        padx=theme.PAD_XL, pady=(0, theme.PAD_S))

    def back() -> None:
        choice["show_results"] = False
        window.destroy()

    def show() -> None:
        choice["show_results"] = True
        window.destroy()

    ctk.CTkButton(actions, text="Back to inputs", width=190, height=40,
                  fg_color=theme.ACCENT_SLATE,
                  hover_color=theme.ACCENT_SLATE_HOVER,
                  font=ctk.CTkFont(size=theme.SIZE_BODY, weight="bold"),
                  command=back).pack(side="left", padx=theme.PAD_S)
    ctk.CTkButton(actions, text="See results anyway", width=190, height=40,
                  fg_color="transparent", border_width=1,
                  text_color=theme.TEXT_MUTED, hover_color=theme.CARD_HOVER,
                  font=ctk.CTkFont(size=theme.SIZE_BODY),
                  command=show).pack(side="left", padx=theme.PAD_S)

    window.protocol("WM_DELETE_WINDOW", back)
    window.wait_window()
    return choice["show_results"]


def _as_number(value, native: str):
    """(number, its unit) from a bare value or a [value, unit] pair.

    A bare number is in `native`'s distance unit — feet for an MRT run, metres
    otherwise — because that's what the backend wrote. A pair carries its own
    unit and overrides that.
    """
    from src.ui.app.widgets.kv_row import as_pair
    pair = as_pair(value)
    if pair is not None:
        return pair
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return float(value), vc.storage_unit("distance", native)
    except (ValueError, KeyError):
        return float(value), "m"


def _summary(reached, target, system: str, native: str = "SI") -> str:
    """The two altitudes and the shortfall, in the page's unit system."""
    got = _as_number(reached, native)
    want = _as_number(target, native)
    if got is None or want is None:
        return ""

    unit = vc.unit_for_system("distance", system)
    try:
        reached_v = vc.convert(got[0], got[1], unit)
        target_v = vc.convert(want[0], want[1], unit)
    except (ValueError, KeyError):
        return ""

    return (f"Target   {format_scalar(target_v):>12} {unit}\n"
            f"Reached  {format_scalar(reached_v):>12} {unit}\n"
            f"Short by {format_scalar(target_v - reached_v):>12} {unit}")


def _centre(window, parent) -> None:
    window.geometry(f"{_W}x{_H}")
    try:
        root = parent.winfo_toplevel()
        x = root.winfo_rootx() + (root.winfo_width() - _W) // 2
        y = root.winfo_rooty() + (root.winfo_height() - _H) // 2
        window.geometry(f"{_W}x{_H}+{max(x, 0)}+{max(y, 0)}")
    except Exception:                           # noqa: BLE001
        pass
