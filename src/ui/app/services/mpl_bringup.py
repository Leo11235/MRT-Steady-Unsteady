"""Helper: force matplotlib windows to the foreground on show.

Symptom we fix: when the results-page 'Show graphs' button is clicked,
matplotlib figures render initially in front of the main UI, but as
they paint their contents (initial blank → axes → data) they end up
covered by the main window on some Windows setups.

Workaround: after `plt.show()` returns, walk the figure manager list,
briefly toggle each window's `-topmost` attribute so Tk lifts it to
the front, then untoggle after a short delay so the user can still
Alt-Tab back to the main UI later.

Robust to non-Tk backends (Agg / Qt) — anything that raises during the
attribute call is silently ignored.
"""

from __future__ import annotations


def lift_all_figures() -> None:
    """Bring every currently-open matplotlib figure to the front."""
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return

    for num in plt.get_fignums():
        try:
            mgr = plt.figure(num).canvas.manager
            win = getattr(mgr, "window", None)
            if win is None:
                continue
            # Tk backend: attributes; briefly-topmost trick.
            try:
                win.attributes("-topmost", True)
                # Turn topmost off after 300 ms so the user can still
                # Alt-Tab freely later.
                win.after(300, lambda w=win: _untop(w))
            except Exception:
                # PyQt / other backends — try raise_() instead.
                if hasattr(win, "raise_"):
                    try:
                        win.raise_()
                    except Exception:
                        pass
                if hasattr(win, "activateWindow"):
                    try:
                        win.activateWindow()
                    except Exception:
                        pass
        except Exception:
            continue


def _untop(win) -> None:
    try:
        win.attributes("-topmost", False)
    except Exception:
        pass
