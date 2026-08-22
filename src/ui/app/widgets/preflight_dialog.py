"""
The preflight warning modal.

Sits between clicking Run and the simulation starting, whenever
`preflight_steady` / `preflight_unsteady` return anything.  Unsteady runs take
tens of seconds to minutes, so surfacing a suspect input here rather than at
the end of a run is most of the value.

Returns True to proceed and False to go back and edit.  Closing the window with
the X counts as going back, because dismissing a warning should never be the
same as agreeing with it.

Warnings arrive as {id: {"severity": ..., "message": ...}}. Severity is
"advisory", "caution" or "critical"; anything else renders as advisory.
"""

from __future__ import annotations

import customtkinter as ctk

from src.ui.app import theme


# Severity presentation, worst first.
_SEVERITY_ORDER = ("critical", "caution", "advisory")

_SEVERITY_STYLE: dict[str, tuple[str, tuple]] = {
    # id: (heading shown on the group, colour)
    "critical": ("Critical", theme.ERROR),
    "caution":  ("Caution", theme.WARNING_STRONG),
    "advisory": ("Advisory", theme.WARNING),
}


def show_preflight_warnings(parent, warnings: dict, *,
                            run_anyway_text: str = "Run anyway") -> bool:
    """Show the warnings and ask whether to continue.

    True means run, False means go back to the form.  A critical warning
    changes the wording and the button colour but does not remove the option to
    proceed: the checks are heuristics, and the user may know better.
    """
    if not warnings:
        return True

    has_critical = any(
        (entry or {}).get("severity") == "critical"
        for entry in warnings.values() if isinstance(entry, dict)
    )

    window = ctk.CTkToplevel(parent)
    window.title("Check these inputs before running")
    window.transient(parent.winfo_toplevel())
    window.resizable(False, False)

    width, height = 560, 460
    window.update_idletasks()
    try:
        root = parent.winfo_toplevel()
        x = root.winfo_rootx() + (root.winfo_width() - width) // 2
        y = root.winfo_rooty() + (root.winfo_height() - height) // 3
        window.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
    except Exception:                           # noqa: BLE001
        window.geometry(f"{width}x{height}")
    window.after(10, window.grab_set)

    # Default to NOT running. Every path that isn't an explicit click on
    # "Run anyway" leaves this False, including the window manager's close
    # button, which is the behaviour you want from a warning dialog.
    decision = {"proceed": False}

    # ---- actions, packed first so they can't be pushed off the bottom ----
    actions = ctk.CTkFrame(window, fg_color="transparent")
    actions.pack(side="bottom", pady=(0, theme.PAD_M))

    def go_back() -> None:
        decision["proceed"] = False
        window.destroy()

    def proceed() -> None:
        decision["proceed"] = True
        window.destroy()

    ctk.CTkButton(actions, text="Back to inputs", width=170, height=36,
                  command=go_back).pack(side="left", padx=theme.PAD_S)
    ctk.CTkButton(
        actions, text=run_anyway_text, width=170, height=36,
        fg_color=theme.ERROR if has_critical else theme.WARNING_STRONG,
        command=proceed,
    ).pack(side="left", padx=theme.PAD_S)

    window.protocol("WM_DELETE_WINDOW", go_back)

    # ---- heading -------------------------------------------------------
    count = len(warnings)
    ctk.CTkLabel(
        window,
        text=("These inputs will probably fail" if has_critical
              else "These inputs look unusual"),
        font=ctk.CTkFont(size=theme.SIZE_H1, weight="bold"),
        text_color=theme.ERROR if has_critical else theme.WARNING_STRONG,
    ).pack(side="top", pady=(theme.PAD_L, theme.PAD_XS))

    ctk.CTkLabel(
        window,
        text=(f"{count} thing{'s' if count != 1 else ''} worth a look before "
              f"committing to a run."),
        font=ctk.CTkFont(size=theme.SIZE_BODY),
        text_color=theme.TEXT_MUTED,
    ).pack(side="top", pady=(0, theme.PAD_M))

    # ---- the list, worst first -----------------------------------------
    body = ctk.CTkScrollableFrame(window, fg_color=("gray92", "gray17"))
    body.pack(side="top", fill="both", expand=True,
              padx=theme.PAD_M, pady=(0, theme.PAD_M))

    def severity_of(entry) -> str:
        value = (entry or {}).get("severity") if isinstance(entry, dict) else None
        return value if value in _SEVERITY_STYLE else "advisory"

    for severity in _SEVERITY_ORDER:
        group = {k: v for k, v in warnings.items() if severity_of(v) == severity}
        if not group:
            continue
        heading, colour = _SEVERITY_STYLE[severity]
        ctk.CTkLabel(
            body, text=f"{heading} ({len(group)})", anchor="w",
            text_color=colour,
            font=ctk.CTkFont(size=theme.SIZE_SMALL, weight="bold"),
        ).pack(fill="x", pady=(theme.PAD_S, theme.PAD_XS))

        for warning_id, entry in group.items():
            message = (entry or {}).get("message") if isinstance(entry, dict) else str(entry)
            card = ctk.CTkFrame(body, fg_color=("gray88", "gray22"),
                                corner_radius=6)
            card.pack(fill="x", pady=2)
            ctk.CTkLabel(
                card, text=str(message or warning_id), anchor="w",
                justify="left", wraplength=440,
            ).pack(fill="x", padx=theme.PAD_S, pady=(theme.PAD_S, 2))
            # The ID is what to grep for in warnings.py when someone asks
            # "why did it say that?", so it's worth showing quietly.
            ctk.CTkLabel(
                card, text=warning_id, anchor="w",
                text_color=theme.TEXT_FAINT,
                font=ctk.CTkFont(family="Consolas", size=theme.SIZE_SMALL),
            ).pack(fill="x", padx=theme.PAD_S, pady=(0, theme.PAD_S))

    window.wait_window()
    return decision["proceed"]
