"""
Plot registries, shared by the backend's PDF export and the UI's graph windows.

This file exists for one reason: to pin matplotlib to the Agg backend before
any submodule imports pyplot.

Figures get built on a worker thread (the UI's simulation runner, the test
suite). If matplotlib is left to choose its own backend it picks TkAgg
whenever tkinter is importable, and TkAgg creates Tk objects. Tk objects made
off the main thread produce, at best, a stream of

    Exception ignored in: <function Image.__del__ ...>
    RuntimeError: main thread is not in main loop

on the console, and at worst a hang. Agg is pure computation and thread-safe.

Displaying a figure still works: the UI drives FigureCanvasTkAgg itself, on the
main thread (see src/ui/app/widgets/figure_window.py). That path doesn't
consult the global backend setting, so pinning Agg here costs nothing.

Because Python runs a package's __init__ before any of its submodules, the
import below is guaranteed to land before the first `import matplotlib.pyplot`
in steady_plots, unsteady_plots or parametric_plots.
"""

import matplotlib

matplotlib.use("Agg")
