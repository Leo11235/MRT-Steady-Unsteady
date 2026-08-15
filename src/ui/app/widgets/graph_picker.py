"""
GraphPicker — choose which plots to render.

Reads the plot registry in src/common/plotting/unsteady_plots.py, so the list
is exactly what the PDF would contain, grouped the same way and in the same
order. Adding a plot to the registry makes it appear here with no change to
this file.

Rendering 28 matplotlib figures takes a few seconds and a lot of memory, so
nothing is drawn until you pick. The dialog opens with the summary panels and
the headline time series ticked, which is what you want nine times out of ten.
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from src.ui.app import theme

# Groups ticked when the dialog first opens.
_DEFAULT_GROUPS = ("Summary", "Time series")


def _registry():
    """Imported lazily: pulling in the plotting module drags in matplotlib,
    which is slow and shouldn't happen unless someone asks for a graph."""
    from src.common.plotting import unsteady_plots
    return unsteady_plots


def unsteady_specs():
    """The unsteady plot registry, imported on demand."""
    return _registry().plot_specs()


def steady_specs():
    """The steady flight-plot registry, imported on demand."""
    from src.common.plotting import steady_plots
    return steady_plots.plot_specs()


def show_graph_picker(parent, specs=None, *,
                      preselected: Optional[list[str]] = None,
                      defaults: Optional[list[str]] = None,
                      title: str = "Choose graphs") -> Optional[list[str]]:
    """Ask which plots to render.

    `specs` is any sequence of objects with name, label and group — both plot
    registries qualify. Defaults to the unsteady one, which is what the
    unsteady results page wants.

    Returns the chosen names in registry order, or None if cancelled, which is
    deliberately distinct from an empty list meaning "chose nothing".
    """
    if specs is None:
        specs = unsteady_specs()
    specs = list(specs)

    if preselected is not None:
        chosen = set(preselected)
    elif defaults is not None:
        chosen = set(defaults)
    else:
        chosen = {spec.name for spec in specs if spec.group in _DEFAULT_GROUPS}

    window = ctk.CTkToplevel(parent)
    window.title(title)
    window.transient(parent.winfo_toplevel())
    window.resizable(False, False)

    # Clamp to the screen and centre vertically. The old fixed 620 px hung off
    # the bottom of a laptop display once the taskbar took its cut, which hid
    # the Cancel and Render buttons.
    width, height = 560, 620
    window.update_idletasks()
    try:
        screen_h = window.winfo_screenheight()
        screen_w = window.winfo_screenwidth()
        # Leave room for the title bar and taskbar rather than assuming a
        # specific size for either.
        height = min(height, int(screen_h * 0.85))
        width = min(width, int(screen_w * 0.9))

        root = parent.winfo_toplevel()
        x = root.winfo_rootx() + (root.winfo_width() - width) // 2
        y = root.winfo_rooty() + (root.winfo_height() - height) // 2
        # Keep it fully on screen even if the main window is near an edge.
        x = max(0, min(x, screen_w - width))
        y = max(0, min(y, screen_h - height - 40))
        window.geometry(f"{width}x{height}+{x}+{y}")
    except Exception:                           # noqa: BLE001
        window.geometry(f"{width}x{height}")
    window.after(10, window.grab_set)

    result: dict = {"names": None}
    variables: dict[str, ctk.BooleanVar] = {}

    # ---- buttons first, so a long list can't push them off the bottom ----
    actions = ctk.CTkFrame(window, fg_color="transparent")
    actions.pack(side="bottom", pady=(0, theme.PAD_M))

    def cancel() -> None:
        result["names"] = None
        window.destroy()

    def confirm() -> None:
        # Registry order, not click order, so the output is always consistent.
        result["names"] = [s.name for s in specs if variables[s.name].get()]
        window.destroy()

    ctk.CTkButton(actions, text="Cancel", width=140, height=36,
                  command=cancel).pack(side="left", padx=theme.PAD_S)
    ctk.CTkButton(actions, text="Render", width=140, height=36,
                  fg_color=theme.ACCENT_SLATE,
                  hover_color=theme.ACCENT_SLATE_HOVER,
                  command=confirm).pack(side="left", padx=theme.PAD_S)
    window.protocol("WM_DELETE_WINDOW", cancel)

    # No heading and no blurb. The window title already says "Choose graphs",
    # and the list is self-explanatory; that space is better spent on the list.

    # ---- select-all / none -------------------------------------------
    bulk = ctk.CTkFrame(window, fg_color="transparent")
    bulk.pack(fill="x", padx=theme.PAD_M, pady=(theme.PAD_M, theme.PAD_XS))
    ctk.CTkButton(bulk, text="All", width=70, height=26,
                  fg_color="transparent", border_width=1,
                  text_color=theme.TEXT_MUTED,
                  command=lambda: [v.set(True) for v in variables.values()]).pack(side="left")
    ctk.CTkButton(bulk, text="None", width=70, height=26,
                  fg_color="transparent", border_width=1,
                  text_color=theme.TEXT_MUTED,
                  command=lambda: [v.set(False) for v in variables.values()]).pack(
        side="left", padx=(theme.PAD_XS, 0))

    # ---- the list, grouped -------------------------------------------
    body = ctk.CTkScrollableFrame(window, fg_color=("gray92", "gray17"))
    body.pack(fill="both", expand=True, padx=theme.PAD_M, pady=(0, theme.PAD_M))

    groups: list[str] = []
    for spec in specs:
        if spec.group not in groups:
            groups.append(spec.group)

    for group in groups:
        header = ctk.CTkFrame(body, fg_color="transparent")
        header.pack(fill="x", pady=(theme.PAD_S, 0))
        ctk.CTkLabel(header, text=group, anchor="w",
                     font=ctk.CTkFont(size=theme.SIZE_SMALL, weight="bold"),
                     text_color=theme.TEXT_MUTED).pack(side="left")

        group_specs = [s_ for s_ in specs if s_.group == group]

        def toggle_group(specs_in_group=group_specs) -> None:
            # Flip the whole group to whatever the majority isn't.
            turning_on = not all(variables[s.name].get() for s in specs_in_group)
            for spec in specs_in_group:
                variables[spec.name].set(turning_on)

        ctk.CTkButton(header, text="toggle", width=56, height=20,
                      fg_color="transparent", text_color=theme.TEXT_FAINT,
                      hover_color=theme.CARD_HOVER,
                      font=ctk.CTkFont(size=theme.SIZE_SMALL),
                      command=toggle_group).pack(side="right")

        for spec in group_specs:
            variables[spec.name] = ctk.BooleanVar(value=spec.name in chosen)
            ctk.CTkCheckBox(body, text=spec.label,
                            variable=variables[spec.name]).pack(
                fill="x", padx=(theme.PAD_M, 0), pady=1)

    window.wait_window()
    return result["names"]
