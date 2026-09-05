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

        # Hide before anything is drawn, and stay hidden until reveal().
        #
        # This is what stopped the flashing. Building N windows in a loop used
        # to show each one the instant it was constructed: an empty white frame
        # appeared, then filled in when draw() finished, and CTkToplevel's own
        # deferred withdraw/deiconify (it re-shows the window to apply the dark
        # titlebar on Windows) reshuffled the whole stack every time another
        # was added. Several seconds of windows blinking on and off.
        #
        # Calling withdraw() this early also tells customtkinter the window was
        # deliberately hidden, so its titlebar routine leaves it alone instead
        # of deiconifying it behind our back.
        self.withdraw()

        self.title(title)
        self.geometry(f"{_DEFAULT_W}x{_DEFAULT_H}")
        self.minsize(480, 360)

        self._figure = figure
        self._canvas = None
        self._build()

        self.protocol("WM_DELETE_WINDOW", self.close)
        _OPEN.append(self)

    def reveal(self) -> None:
        """Make the window visible. Safe to call more than once."""
        try:
            self.deiconify()
        except Exception:                       # noqa: BLE001
            pass

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
        # No plt.close() here any more. The builders in src/common/plotting
        # use matplotlib's object API, so pyplot never holds a reference and
        # there is nothing global to release: dropping ours is enough.
        self._figure = None
        if self in _OPEN:
            _OPEN.remove(self)
        self.destroy()


def show_figure(parent, figure, title: str) -> FigureWindow:
    """Open one figure in its own window, fully drawn before it appears."""
    window = FigureWindow(parent, figure, title)
    window.reveal()
    window.lift()
    return window


def show_figures(parent, built: Iterable[tuple[str, object]],
                 *, on_progress=None) -> tuple[int, int, int]:
    """Open a window per figure.

    `built` yields (label, figure_or_None_or_Exception), the same shape the
    plot registries produce. Returns (drawn, skipped, failed): a builder
    returning None means this run has no data for that plot, which is normal;
    one that raises costs only itself.

    Windows are cascaded so a batch of five doesn't land in one stack.

    Two passes on purpose. Every window is built hidden first, then the whole
    set is revealed together, so the screen stays untouched while the figures
    render and they all arrive at once fully drawn.

    `on_progress(done)` fires after each figure. The first pass is slow and,
    because nothing appears while it runs, silent without it.
    """
    close_all()

    drawn = skipped = failed = 0
    pending: list[FigureWindow] = []

    for index, (label, result) in enumerate(built):
        if on_progress is not None:
            try:
                on_progress(index + 1)
            except Exception:                   # noqa: BLE001
                pass                            # a status line is never worth a crash
        if isinstance(result, BaseException):
            failed += 1
            continue
        if result is None:
            skipped += 1
            continue
        window = FigureWindow(parent, result, label)   # hidden until revealed
        _cascade(window, index)
        pending.append(window)
        drawn += 1

    for window in pending:
        window.reveal()

    _raise_all()
    return (drawn, skipped, failed)


def _raise_all() -> None:
    """Bring every open graph window in front of the main window and leave it
    there.

    A plain lift() is not enough. CTkToplevel schedules its own deferred
    lift/redraw a couple of hundred milliseconds after construction, so with
    two windows the second one's callback ran after our lift and the main
    window ended up on top — which is why one graph stayed in front and a
    2D + 3D pair flashed and sank.

    Setting -topmost wins that race outright, then we drop it again so the
    windows behave like normal windows once the user is looking at them.
    """
    for window in _OPEN:
        try:
            window.attributes("-topmost", True)
            window.lift()
        except Exception:                       # noqa: BLE001
            pass

    def release() -> None:
        for window in _OPEN:
            try:
                window.attributes("-topmost", False)
            except Exception:                   # noqa: BLE001
                pass

    if _OPEN:
        # Long enough to outlast CTk's own deferred lift.
        _OPEN[0].after(400, release)


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
