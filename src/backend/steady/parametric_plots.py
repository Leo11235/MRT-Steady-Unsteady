"""Parametric-study visualisation.

Two plot builders, both consuming the `parametric_results` block that
`simulate_parametric_study` writes into the output JSON:

    plot_parametric_2d(param_results, x_var, y_var, ...)
    plot_parametric_3d(param_results, x_var, y_var, z_var, ...)

Both open a matplotlib figure with plt.show(block=False) and return the
Figure object.  Callers should use ui.app.services.mpl_bringup.lift_all_figures()
after invoking these so the windows come to the foreground on Windows.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable

import numpy as np
import matplotlib.pyplot as plt


def _combo_matches_holds(combo, swept: list[str], holds: dict) -> bool:
    """True iff every held var's value in `combo` matches `holds[var]`
    within a small relative tolerance.  Empty `holds` always matches."""
    if not holds:
        return True
    for var, held_val in holds.items():
        if var not in swept:
            continue
        idx = swept.index(var)
        try:
            if not math.isclose(float(combo[idx]), float(held_val),
                                rel_tol=1e-6, abs_tol=1e-12):
                return False
        except (TypeError, ValueError):
            if combo[idx] != held_val:
                return False
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def swept_variables(param_results: dict) -> list[str]:
    """Names of the variables the user asked to sweep, in the order the
    solver stored them (this is also the column order of `combinations`)."""
    return list((param_results.get("variable_ranges") or {}).keys())


def available_output_variables(param_results: dict) -> list[str]:
    """Every output-variable key that appears in the per-combo
    rocket_parameters dicts.  De-duplicated and stable-ordered."""
    seen: dict[str, None] = {}
    for rp in (param_results.get("rocket_parameters") or []):
        if not isinstance(rp, dict):
            continue
        for k in rp:
            if k not in seen:
                seen[k] = None
    return list(seen.keys())


def _extract_series(
    param_results: dict,
    swept_vars: list[str],
    x_var: str,
    output_var: str,
    holds: dict | None = None,
) -> tuple[dict[tuple, list[tuple[float, float]]], list[str]]:
    """For a 2D plot: return ({non_x_vals_tuple: [(x, y), ...]}, other_var_names).

    `other_var_names` excludes both x_var AND any variable in `holds`
    (they're pinned so they aren't part of the "other axes" family of
    curves).  `holds` is a dict of {var_name: fixed_value_in_SI}.
    Combinations that don't match every hold are skipped."""
    holds = holds or {}
    x_idx = swept_vars.index(x_var)
    other_var_names = [v for v in swept_vars if v != x_var and v not in holds]
    other_indices = [swept_vars.index(v) for v in other_var_names]

    combos = param_results.get("combinations") or []
    rps    = param_results.get("rocket_parameters") or []

    grouped: dict[tuple, list[tuple[float, float]]] = defaultdict(list)
    for combo, rp in zip(combos, rps):
        if not isinstance(rp, dict):
            continue
        if not _combo_matches_holds(combo, swept_vars, holds):
            continue
        y_val = rp.get(output_var)
        if y_val is None:
            continue
        x_val = combo[x_idx]
        other_vals = tuple(combo[i] for i in other_indices)
        grouped[other_vals].append((float(x_val), float(y_val)))
    # sort each series by x
    for k in grouped:
        grouped[k].sort()
    return dict(grouped), other_var_names


def _grid_z(
    param_results: dict,
    swept_vars: list[str],
    x_var: str,
    y_var: str,
    z_var: str,
    holds: dict | None = None,
) -> tuple[list[float], list[float], np.ndarray, dict]:
    """For a 3D plot: build an (X, Y, Z) grid.

    Extra swept variables (not x, y) are pinned to whatever the caller
    put in `holds`; anything the caller didn't specify falls back to
    the first grid value (previous behaviour) so an unpinned surface is
    always defined.  The final `fixed` dict returned is what actually
    gets used for the slice — including both explicit holds and the
    implicit first-value fallbacks."""
    holds = dict(holds or {})
    variable_ranges = param_results.get("variable_ranges") or {}
    x_values = list(variable_ranges.get(x_var) or [])
    y_values = list(variable_ranges.get(y_var) or [])

    x_idx = swept_vars.index(x_var)
    y_idx = swept_vars.index(y_var)

    # For every non-axis swept var, use the explicit hold if provided,
    # else fall back to the first grid value.
    other_indices = [i for i, v in enumerate(swept_vars) if v not in (x_var, y_var)]
    fixed: dict[str, float] = {}
    for i in other_indices:
        v_name = swept_vars[i]
        if v_name in holds:
            fixed[v_name] = holds[v_name]
        else:
            fixed[v_name] = (variable_ranges[v_name] or [None])[0]

    Z = np.full((len(x_values), len(y_values)), np.nan, dtype=float)
    combos = param_results.get("combinations") or []
    rps    = param_results.get("rocket_parameters") or []
    for combo, rp in zip(combos, rps):
        if not isinstance(rp, dict):
            continue
        # Skip combos that don't sit on the chosen slice.
        if not _combo_matches_holds(combo, swept_vars, fixed):
            continue
        z_val = rp.get(z_var)
        if z_val is None:
            continue
        try:
            i = x_values.index(combo[x_idx])
            j = y_values.index(combo[y_idx])
        except ValueError:
            continue
        Z[i][j] = float(z_val)
    return x_values, y_values, Z, fixed


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def plot_parametric_2d(
    param_results: dict,
    x_var: str,
    y_var: str,
    *,
    holds: dict | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    x_transform=None,
    y_transform=None,
    hold_label_fn=None,
) -> "plt.Figure":
    """One 2D plot of (y_var) vs (x_var).

    When more than one variable was swept AND the user didn't pin them
    with `holds`, this produces one line per unique combination of the
    remaining (non-x, non-held) swept variables, with each line in the
    legend.  Pinning all non-x variables via holds gives a single line.

    holds : {wire_var: value_in_SI} — combinations whose value for
        that variable doesn't match are dropped from the plot.
    hold_label_fn : optional callable `(wire, value_in_SI) -> str` the
        caller can pass to have the "pinned to X" annotation show
        display units instead of raw SI in the title."""
    swept = swept_variables(param_results)
    if x_var not in swept:
        raise ValueError(f"{x_var!r} is not a parametric-swept variable "
                         f"(available: {swept})")

    grouped, other_vars = _extract_series(
        param_results, swept, x_var, y_var, holds=holds,
    )
    fx = x_transform or (lambda v: v)
    fy = y_transform or (lambda v: v)

    fig, ax = plt.subplots(figsize=(9, 6))
    for other_vals, series in sorted(grouped.items()):
        xs = [fx(p[0]) for p in series]
        ys = [fy(p[1]) for p in series]
        if other_vars:
            label = ", ".join(
                f"{other_vars[i]} = {v}" for i, v in enumerate(other_vals)
            )
            ax.plot(xs, ys, marker="o", label=label)
        else:
            ax.plot(xs, ys, marker="o")

    ax.set_xlabel(x_label or x_var)
    ax.set_ylabel(y_label or y_var)
    title = f"{y_label or y_var}  vs.  {x_label or x_var}"
    if holds:
        # Show the pinned holds in the subtitle so the reader knows the
        # slice.  hold_label_fn (if provided by caller) formats the
        # value with the display unit.
        _fmt = hold_label_fn or (lambda wire, v: f"{wire} = {v}")
        pinned = ", ".join(_fmt(w, v) for w, v in holds.items())
        title += f"\n(with {pinned})"
    ax.set_title(title, fontsize=11)
    ax.grid(True, alpha=0.35)
    if other_vars and grouped:
        ax.legend(fontsize="small", framealpha=0.85, loc="best")
    fig.tight_layout()
    plt.show(block=False)
    return fig


def plot_parametric_3d(
    param_results: dict,
    x_var: str,
    y_var: str,
    z_var: str,
    *,
    holds: dict | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    z_label: str | None = None,
    x_transform=None,
    y_transform=None,
    z_transform=None,
    hold_label_fn=None,
) -> "plt.Figure":
    """One 3D surface of (z_var) over (x_var, y_var).  When more than two
    variables were swept, the extras are pinned at their first grid value
    and that pinning is called out in the title.

    x/y/z_transform are optional callables `float -> float` applied to
    every raw value before plotting (SI → display unit).

    Mouse drag allows normal azimuth (left/right) and elevation
    (up/down) rotation, but ROLL is locked to zero so the scene never
    appears to twist clockwise or counterclockwise as the user drags."""
    swept = swept_variables(param_results)
    if x_var not in swept:
        raise ValueError(f"{x_var!r} is not a parametric-swept variable "
                         f"(available: {swept})")
    if y_var not in swept:
        raise ValueError(f"{y_var!r} is not a parametric-swept variable "
                         f"(available: {swept})")
    if x_var == y_var:
        raise ValueError("3D plot needs two DIFFERENT swept variables "
                         "for the x and y axes.")

    xs, ys, Z, fixed = _grid_z(
        param_results, swept, x_var, y_var, z_var, holds=holds,
    )
    if not xs or not ys:
        raise ValueError("Not enough grid points for a 3D surface — "
                         "did the parametric run finish?")

    fx = x_transform or (lambda v: v)
    fy = y_transform or (lambda v: v)
    fz = z_transform or (lambda v: v)

    xs_display = [fx(v) for v in xs]
    ys_display = [fy(v) for v in ys]
    Z_display  = np.vectorize(fz)(Z)

    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection="3d")

    X, Y = np.meshgrid(xs_display, ys_display, indexing="ij")
    surf = ax.plot_surface(
        X, Y, Z_display,
        cmap="viridis", alpha=0.92,
        edgecolor="k", linewidth=0.25,
        antialiased=True,
    )
    ax.set_xlabel(x_label or x_var)
    ax.set_ylabel(y_label or y_var)
    ax.set_zlabel(z_label or z_var)

    title = (f"{z_label or z_var}  vs.  "
             f"{x_label or x_var}  and  {y_label or y_var}")
    if fixed:
        _fmt = hold_label_fn or (lambda wire, v: f"{wire} = {v}")
        pinned = ", ".join(_fmt(k, v) for k, v in fixed.items())
        title += f"\n(with {pinned})"
    ax.set_title(title, fontsize=11)

    fig.colorbar(surf, ax=ax, shrink=0.6, aspect=14, pad=0.1)

    # Initial view.  Elev and azim are left free for the user to
    # drag; roll is locked to zero (see _lock_roll below).
    try:
        ax.view_init(elev=22, azim=-55, roll=0)
    except TypeError:
        # matplotlib < 3.6 didn't accept a `roll` kwarg
        ax.view_init(elev=22, azim=-55)

    def _lock_roll(event):
        # Fires after matplotlib's built-in rotation handler updates
        # ax.elev / ax.azim / ax.roll.  We snap roll back to 0 so the
        # scene never rotates around the viewing axis.
        if event.inaxes is not ax:
            return
        current_roll = getattr(ax, "roll", 0)
        if current_roll != 0:
            try:
                ax.view_init(elev=ax.elev, azim=ax.azim, roll=0)
            except TypeError:
                # old matplotlib; roll wasn't a thing, nothing to lock
                return
            fig.canvas.draw_idle()

    fig.canvas.mpl_connect("motion_notify_event", _lock_roll)

    fig.tight_layout()
    plt.show(block=False)
    return fig
