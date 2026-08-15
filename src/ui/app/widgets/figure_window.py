"""
Standalone graph windows.

Graphs open as their own resizable windows with the standard matplotlib
toolbar (pan, zoom, save), the way they always have. They are NOT embedded in
a results tab: you want to put a graph next to the numbers it came from, or on
a second monitor, and a tab can't do that.

Everything here runs on the main thread. Figures come from the plot registries
in src/common/plotting/, so a window and the same plot inside graphs.pdf are
built by the same code and cannot drift.

We deliberately do not use pyplot's window management (plt.show). matplotlib's
global backend is pinned to Agg so a worker thread can build figures safely;
FigureCanvasTkAgg works regardless of that setting because we drive it
ourselves.
"""

from __future__ import annotations

import tkinter as tk
from typing import Iterable

import customtkinter as ctk

from src.ui.app import theme

# Every window we've opened, so they can be closed as a group and so Python
# doesn't garbage-collect them out from under Tk.
_OPEN: list["FigureWindow"] = []

_DEFAULT_W, _DEFAULT_H = 980, 700


class FigureWindow(ctk.CTkToplevel):
    """One matplotlib Figure in its own window."""

    def __init__(self, parent, figure, title: str) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{_DEFAULT_W}x{_DEFAULT_H}")
        self.minsize(480, 360)

        self._figure = figure
        self._canvas = None
        self._build()

        self.protocol("WM_DELETE_WINDOW", self.close)
        _OPEN.append(self)

    def _build(self) -> None:
        from matplotlib.backends.backend_tkagg import (
            FigureCanvasTkAgg, NavigationToolbar2Tk,
        )

        # NavigationToolbar2Tk is a classic-tk widget that reconfigures its
        # parent's background. Give it a plain tk.Frame rather than a CTkFrame,
        # which would fight it over styling.
        toolbar_frame = tk.Frame(self, height=40)
        toolbar_frame.pack(side="bottom", fill="x")

        self._canvas = FigureCanvasTkAgg(self._figure, master=self)
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

        toolbar = NavigationToolbar2Tk(self._canvas, toolbar_frame,
                                       pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side="left", fill="x")

    def close(self) -> None:
        """Tear down the canvas and release the figure."""
        try:
            if self._canvas is not None:
                self._canvas.get_tk_widget().destroy()
        except Exception:                       # noqa: BLE001
            pass
        try:
            # The builders use pyplot, so pyplot holds a reference to every
            # figure. Without this the app leaks a figure per window.
            import matplotlib.pyplot as plt
            plt.close(self._figure)
        except Exception:                       # noqa: BLE001
            pass
        if self in _OPEN:
            _OPEN.remove(self)
        self.destroy()


def show_figure(parent, figure, title: str) -> FigureWindow:
    """Open one figure in its own window."""
    window = FigureWindow(parent, figure, title)
    window.lift()
    return window


def show_figures(parent, built: Iterable[tuple[str, object]]) -> tuple[int, int, int]:
    """Open a window per figure.

    `built` yields (label, figure_or_None_or_Exception), the same shape the
    plot registries produce. Returns (drawn, skipped, failed): a builder
    returning None means this run has no data for that plot, which is normal;
    one that raises costs only itself.

    Windows are cascaded so a batch of five doesn't land in one stack.
    """
    close_all()

    drawn = skipped = failed = 0
    for index, (label, result) in enumerate(built):
        if isinstance(result, BaseException):
            failed += 1
            continue
        if result is None:
            skipped += 1
            continue
        window = show_figure(parent, result, label)
        _cascade(window, index)
        drawn += 1

    # Bring the whole batch forward once, after they all exist.
    for window in _OPEN:
        try:
            window.lift()
        except Exception:                       # noqa: BLE001
            pass
    return (drawn, skipped, failed)


def close_all() -> None:
    """Close every open graph window. Called before drawing a new batch and
    when a results page is left, so figures don't accumulate."""
    for window in list(_OPEN):
        try:
            window.close()
        except Exception:                       # noqa: BLE001
            pass
    _OPEN.clear()


def _cascade(window, index: int) -> None:
    """Offset each window from the last so they don't perfectly overlap."""
    step = 32
    offset = (index % 8) * step
    try:
        window.geometry(f"{_DEFAULT_W}x{_DEFAULT_H}+{60 + offset}+{40 + offset}")
    except Exception:                           # noqa: BLE001
        pass
