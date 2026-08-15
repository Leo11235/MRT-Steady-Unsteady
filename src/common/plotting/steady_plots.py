"""
Plots for steady runs that produced a trajectory.

Same shape as unsteady_plots: a registry of named builders taking the results
dict and returning a Figure. Only fuel-mass convergence produces a flight_dict,
so these apply to that alone — a hotfire has no trajectory and a parametric
study has one per point, which is what parametric_plots covers.

Builders return None when the run lacks the series they need, which is normal
rather than an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import matplotlib.pyplot as plt
from matplotlib.figure import Figure


@dataclass(frozen=True)
class PlotSpec:
    name: str
    label: str
    group: str
    builder: Callable[[dict], Optional["Figure"]]


GROUP_FLIGHT = "Flight"

_LINE = 1.8


def _series(results: dict, key: str) -> list:
    return (results.get("flight_dict") or {}).get(key) or []


def _has_time(results: dict) -> bool:
    return bool(_series(results, "time"))


def make_kinematics_plot(results: dict) -> Optional[Figure]:
    """Altitude, velocity and acceleration against time, stacked."""
    if not _has_time(results):
        return None
    time = _series(results, "time")
    panels = [("altitude", "Altitude [m]"),
              ("velocity", "Velocity [m/s]"),
              ("acceleration", "Acceleration [m/s2]")]
    available = [(k, label) for k, label in panels if _series(results, k)]
    if not available:
        return None

    figure, axes = plt.subplots(len(available), 1, figsize=(10, 8),
                                sharex=True, num="Kinematics")
    if len(available) == 1:
        axes = [axes]
    for axis, (key, label) in zip(axes, available):
        axis.plot(time, _series(results, key), linewidth=_LINE)
        axis.set_ylabel(label)
        axis.grid(True, alpha=0.3)
    axes[-1].set_xlabel("Time [s]")
    axes[0].set_title("Rocket kinematics")
    figure.tight_layout()
    return figure


def make_thrust_plot(results: dict) -> Optional[Figure]:
    """Thrust against time over the burn."""
    if not _has_time(results) or not _series(results, "thrust"):
        return None
    figure, axis = plt.subplots(figsize=(10, 5), num="Thrust")
    axis.plot(_series(results, "time"), _series(results, "thrust"),
              linewidth=_LINE, color="#e63946")
    axis.set_xlabel("Time [s]")
    axis.set_ylabel("Thrust [N]")
    axis.set_title("Thrust vs. time")
    axis.grid(True, alpha=0.3)
    figure.tight_layout()
    return figure


def make_forces_plot(results: dict) -> Optional[Figure]:
    """Thrust, drag, weight and the net of them, on one axis.

    Overlaying them is the point: the crossover where drag and weight overtake
    thrust is what sets the burnout condition.
    """
    if not _has_time(results):
        return None
    time = _series(results, "time")
    forces = [("thrust", "Thrust", "#e63946"),
              ("drag_force", "Drag", "#f4a261"),
              ("grav_force", "Weight", "#2a9d8f"),
              ("net_force", "Net", "#264653")]
    available = [(k, label, colour) for k, label, colour in forces
                 if _series(results, k)]
    if not available:
        return None

    figure, axis = plt.subplots(figsize=(10, 5), num="Forces")
    for key, label, colour in available:
        axis.plot(time, _series(results, key), linewidth=_LINE,
                  label=label, color=colour)
    axis.axhline(0, color="gray", linewidth=0.8)
    axis.set_xlabel("Time [s]")
    axis.set_ylabel("Force [N]")
    axis.set_title("Forces vs. time")
    axis.grid(True, alpha=0.3)
    axis.legend()
    figure.tight_layout()
    return figure


PLOTS: tuple[PlotSpec, ...] = (
    PlotSpec("kinematics", "Kinematics (altitude, velocity, acceleration)",
             GROUP_FLIGHT, make_kinematics_plot),
    PlotSpec("thrust", "Thrust vs. time", GROUP_FLIGHT, make_thrust_plot),
    PlotSpec("forces", "Forces vs. time", GROUP_FLIGHT, make_forces_plot),
)

PLOTS_BY_NAME: dict[str, PlotSpec] = {spec.name: spec for spec in PLOTS}

# What the picker ticks by default.
DEFAULT_SELECTION = ("kinematics", "thrust")


def plot_specs(group: str | None = None) -> list[PlotSpec]:
    if group is None:
        return list(PLOTS)
    return [spec for spec in PLOTS if spec.group == group]


def plot_groups() -> list[str]:
    seen: list[str] = []
    for spec in PLOTS:
        if spec.group not in seen:
            seen.append(spec.group)
    return seen


def plot_names() -> list[str]:
    return [spec.name for spec in PLOTS]
def label_of(name: str) -> str:
    """Human-readable title for a plot, used as its window title."""
    spec = PLOTS_BY_NAME.get(name)
    return spec.label if spec else name


def build_figure(name: str, results: dict) -> Optional[Figure]:
    if name not in PLOTS_BY_NAME:
        raise KeyError(f"Unknown plot {name!r}. Registered: {', '.join(plot_names())}")
    return PLOTS_BY_NAME[name].builder(results)
