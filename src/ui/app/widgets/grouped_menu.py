"""Dropdown entries split into named groups.

CTkOptionMenu has no notion of a non-selectable entry, so a group header is a
normal item wearing box-drawing characters, and selecting one silently reverts.
That trick started in the parametric graph dialog; the steady results page now
uses the same dropdown to rank a sweep, and two copies of a convention like
this is how they drift apart.

    values = grouped_values([("Common outputs", [("Specific impulse", "Isp")]),
                             ("All other outputs", [...])])
    menu = ctk.CTkOptionMenu(parent, variable=var, values=values)
    guard_headers(var, values)
"""

from __future__ import annotations

import customtkinter as ctk

PREFIX = "── "
SUFFIX = " ──"


def header(text: str) -> str:
    return f"{PREFIX}{text}{SUFFIX}"


def is_header(value: str) -> bool:
    return value.startswith(PREFIX) and value.endswith(SUFFIX)


def grouped_values(groups: list) -> list[str]:
    """[(group name, [(label, wire), ...]), ...] -> a flat list of menu entries.

    Empty groups are dropped rather than shown as a header with nothing under
    it. A list with no entries at all still returns one item, because a menu
    with no values renders as a blank box with no hint that anything is wrong.
    """
    values: list[str] = []
    for name, pairs in groups:
        if not pairs:
            continue
        values.append(header(name))
        values.extend(label for label, _wire in pairs)
    return values or ["(none)"]


def first_selectable(values: list[str], preferred: str = "") -> str:
    """What to start on: the caller's choice if it is really in the list."""
    if preferred and preferred in values and not is_header(preferred):
        return preferred
    for value in values:
        if not is_header(value):
            return value
    return values[0] if values else ""


def guard_headers(var: ctk.StringVar, values: list[str]) -> None:
    """Revert if a group header gets selected.

    Silently: an error message for clicking a label would be worse than the
    click simply not taking.
    """
    last = {"value": var.get()}

    def on_write(*_args) -> None:
        current = var.get()
        if is_header(current):
            var.set(last["value"])
        else:
            last["value"] = current

    var.trace_add("write", on_write)
