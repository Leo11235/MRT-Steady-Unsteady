"""
Shared helpers for the results pages.

Three things live here:

  1.  flatten_dict — walk a nested dict and produce a flat `{path: value}`
      dict where nested keys are joined by "/".  Used to turn either the
      Steady or the Unsteady result JSON into a single row for
      spreadsheet export.

  2.  build_tsv / copy / export helpers — turn a flat dict or a list of
      (header, value) pairs into text suitable for pasting into Google
      Sheets, or write a proper CSV.

  3.  flat_to_display_pairs / render_kv_row / build_unit_buttons — the
      unit-aware layer.  flat_to_display_pairs converts each entry using
      the results_units.py tables so the exported headers read
      "Peak thrust (N)" and values are in whichever unit system the
      caller asked for.  render_kv_row draws a single three-column row.
      build_unit_buttons adds the SI/IMP/MRT toggle.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app import display as display_mod
from src.ui.app.services.pretty_names import (
    get_field_info,
    unit_for_system,
    format_unit_label,
)
from src.ui.app.widgets.kv_row import KVRow


# ---------------------------------------------------------------------------
# Nested-dict → flat dict
# ---------------------------------------------------------------------------

def flatten_dict(
    d: dict,
    *,
    sep: str = "/",
    prefix: str = "",
    skip_keys: tuple[str, ...] = (),
    max_list_len: int = 10,
) -> dict:
    """
    Walk `d` recursively and return {"a/b/c": value, ...}.

    - Dicts are recursed.
    - Small lists (< max_list_len) of primitives are joined with ";".
    - Large lists (time-series arrays etc.) are DROPPED, since the user
      wants a one-row summary, not thousands of columns.
    - `skip_keys` names top-level keys to skip entirely (useful to drop
      time-series blocks like unsteady's "data").

    Values are left as-is (numbers stay numeric so CSV writers format them
    reasonably).  None becomes an empty string.
    """
    out: dict[str, Any] = {}
    for k, v in d.items():
        if k in skip_keys and prefix == "":
            continue
        key = f"{prefix}{sep}{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(flatten_dict(v, sep=sep, prefix=key,
                                    skip_keys=skip_keys,
                                    max_list_len=max_list_len))
        elif isinstance(v, (list, tuple)):
            if len(v) == 0:
                out[key] = ""
            elif (len(v) < max_list_len
                  and not any(isinstance(x, (dict, list, tuple)) for x in v)):
                out[key] = ";".join("" if x is None else str(x) for x in v)
            else:
                # too big / too nested — drop
                pass
        elif v is None:
            out[key] = ""
        else:
            out[key] = v
    return out


# ---------------------------------------------------------------------------
# One-row TSV / CSV helpers
# ---------------------------------------------------------------------------

def _stringify(v: Any) -> str:
    """Same 4-decimal cap as the on-screen renderer, so what you see is
    what you copy/export."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if abs(v) < 1e-15:
            return "0"
        if abs(v - round(v)) < 1e-9 and abs(v) < 1e15:
            return f"{int(round(v))}"
        if abs(v) < 1e-3:
            return f"{v:.4g}"
        s = f"{v:.4f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s
    return str(v)


def build_tsv_two_line(flat: dict) -> str:
    """Return 'header1\\theader2\\n value1\\tvalue2' — pastes cleanly into
    Google Sheets / Excel starting at the currently-selected cell."""
    keys   = list(flat.keys())
    values = [_stringify(flat[k]) for k in keys]
    return "\t".join(keys) + "\n" + "\t".join(values)


def copy_flat_to_clipboard(widget, flat: dict) -> None:
    """Put a two-line TSV of `flat` into the OS clipboard via `widget`."""
    widget.clipboard_clear()
    widget.clipboard_append(build_tsv_two_line(flat))


def export_flat_to_csv(path: Path, flat: dict) -> None:
    """Write `flat` to `path` as a two-row CSV (headers + values)."""
    keys   = list(flat.keys())
    values = [_stringify(flat[k]) for k in keys]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(keys)
        w.writerow(values)


# ============================================================================
# UNIT-AWARE LAYER
# ============================================================================

def _prettify_segment(s: str) -> str:
    """Prettify a raw path segment (used for header prefixes)."""
    if not s:
        return s
    cleaned = s.replace("_", " ").strip()
    if not cleaned:
        return s
    return cleaned[0].upper() + cleaned[1:]


def _convert_scalar(value: Any, key: str, system: str):
    """
    Return (converted_value, unit_label).

    - Non-numeric / dimensionless values pass through unchanged with unit "."
    - Numeric values with a known kind are converted from the JSON's SI
      unit into the target system's unit for that kind.
    """
    pretty, kind, si_unit = get_field_info(key)
    if kind is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return value, "."
    target_unit = unit_for_system(key, kind, system)
    try:
        converted = display_mod.convert(float(value), si_unit, target_unit, kind)
    except Exception:
        converted = value
    return converted, format_unit_label(target_unit)


def flat_to_display_pairs(flat: dict, system: str) -> list[tuple[str, Any]]:
    """
    Given a flat {path: value} dict and a target unit system, produce a
    list of (header, converted_value) pairs suitable for copy or export.

    Header format:
        - top-level:   "Pretty name (unit)"
        - nested:      "Parent segment - Pretty name (unit)"
    """
    pairs: list[tuple[str, Any]] = []
    for flat_key, value in flat.items():
        segments = flat_key.split("/")
        leaf = segments[-1]
        pretty, _kind, _si = get_field_info(leaf)
        converted, unit_label = _convert_scalar(value, leaf, system)
        if len(segments) > 1:
            parents = " - ".join(_prettify_segment(s) for s in segments[:-1])
            header = f"{parents} - {pretty} ({unit_label})"
        else:
            header = f"{pretty} ({unit_label})"
        pairs.append((header, converted))
    return pairs


def build_tsv_from_pairs(pairs: list[tuple[str, Any]]) -> str:
    headers = [h for h, _ in pairs]
    values  = [_stringify(v) for _, v in pairs]
    return "\t".join(headers) + "\n" + "\t".join(values)


def copy_pairs_to_clipboard(widget, pairs: list[tuple[str, Any]]) -> None:
    widget.clipboard_clear()
    widget.clipboard_append(build_tsv_from_pairs(pairs))


def export_pairs_to_csv(path: Path, pairs: list[tuple[str, Any]]) -> None:
    headers = [h for h, _ in pairs]
    values  = [_stringify(v) for _, v in pairs]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerow(values)


# ---------------------------------------------------------------------------
# On-screen row rendering (3 columns: name | value | unit)
# ---------------------------------------------------------------------------

def _format_scalar(v: Any) -> str:
    """Cap floats at 4 decimal places (with trailing zeros stripped).
    Falls back to 4-significant-figures for very small magnitudes so
    something like 3e-6 doesn't collapse to '0.0000'."""
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if abs(v) < 1e-15:
            return "0"
        if abs(v - round(v)) < 1e-9 and abs(v) < 1e15:
            return f"{int(round(v))}"
        if abs(v) < 1e-3:
            return f"{v:.4g}"
        s = f"{v:.4f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s
    if isinstance(v, int):
        return str(v)
    if isinstance(v, dict):
        return f"({len(v)} keys — nested)"
    if isinstance(v, list):
        return f"[{len(v)} items]"
    return str(v)


def render_kv_row(parent, key: str, value: Any, system: str,
                  *, name_width: int | None = None,
                  unit_width: int | None = None) -> "KVRow":
    """
    Add a three-column key/value/unit row to `parent` and return the
    widget so the caller can call `.update_system(system)` on it later
    without destroying + rebuilding — that's the fast path used by the
    Units toggle on the results pages.

    Backwards-compatible: existing callers that ignore the return value
    still work exactly as before.
    """
    row = KVRow(parent, key, value, system,
                name_width=name_width, unit_width=unit_width)
    row.pack(fill="x", pady=1)
    return row


# ---------------------------------------------------------------------------
# SI/IMP/MRT selector
# ---------------------------------------------------------------------------

def build_unit_buttons(parent, initial_system: str,
                       on_change: Callable[[str], None]) -> dict[str, ctk.CTkButton]:
    """
    Add the three unit-system buttons horizontally inside `parent`.
    Returns a dict {system: button} so the caller can toggle the active
    one via refresh_unit_buttons().
    """
    buttons: dict[str, ctk.CTkButton] = {}
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x")
    for system in ("SI", "IMP", "MRT"):
        btn = ctk.CTkButton(
            row, text=system,
            width=58, height=32,
            command=lambda s=system: on_change(s),
        )
        btn.pack(side="left", padx=2)
        buttons[system] = btn
    refresh_unit_buttons(buttons, initial_system)
    return buttons


def refresh_unit_buttons(buttons: dict[str, ctk.CTkButton],
                         current_system: str) -> None:
    """Disable + gray the button matching current_system; enable the others."""
    for system, btn in buttons.items():
        if system == current_system:
            btn.configure(state="disabled")
        else:
            btn.configure(state="normal")
