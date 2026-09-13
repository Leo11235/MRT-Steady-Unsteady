"""
KVRow — one row of a results table.

    [ Pretty name (unit) .................. ] [ value ........... ]

Rows remember the raw key and the raw SI value they were built from, so
switching the global unit system re-labels and re-converts in place with two
configure() calls.  Rebuilding a few hundred rows on every toggle was visibly
slow in the old UI.

The name and unit both come from the field registry, so a value shown here
carries the same label it had on the input form.  Result keys the registry
doesn't know about — computed outputs like `total_impulse`, which are never
inputs — fall back to the suffix parser below.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import customtkinter as ctk

from src.common import output_registry as outputs
from src.common.unit_labels import pretty_unit
from src.common import variable_conversions as vc
from src.ui.app import theme
from src.ui.app import field_registry as registry


# =============================================================================
# Working out what a result key means
# =============================================================================
#
# Two sources, in order:
#
#   1. The output registry, which covers everything the simulation computes,
#      under its current name and every older spelling.
#   2. The field registry, which covers everything that was an input.
#
# Unsteady output keys used to carry their unit in the name (peak_thrust_N,
# apogee_m_agl) and this module parsed the suffix to work out what they were.
# That convention is gone: src/common/output_registry.py holds the meanings
# now, so a name can be readable without losing its unit.
#
# Anything neither source explains renders unitless, which is right for ratios
# and exponents and merely unhelpful for the rest.

# Explicit entries for computed values whose names don't self-describe.
_COMPUTED_FIELDS: dict[str, tuple[str, str]] = {
    # key: (label, SI unit)
    "thrust":                          ("Thrust", "N"),
    "Isp":                             ("Isp", "s"),
    "burntime":                        ("Burn time", "s"),
    "total_impulse":                   ("Total impulse", "N*s"),
    "wet_mass":                        ("Wet mass", "kg"),
    "reached_apogee":                  ("Apogee reached", "m"),
    "apogee":                          ("Apogee", "m"),
    # steady flight_dict series. The Trajectory tab shows <name>_max and
    # <name>_final, which the suffix stripper below reduces to these.
    "altitude":                        ("Altitude", "m"),
    "velocity":                        ("Velocity", "m/s"),
    "acceleration":                    ("Acceleration", "m/s^2"),
    "drag_force":                      ("Drag force", "N"),
    "grav_force":                      ("Gravitational force", "N"),
    "time":                            ("Time", "s"),
    "chamber_temperature":             ("Chamber temperature", "K"),
    "nozzle_throat_area":              ("Nozzle throat area", "m^2"),
    "nozzle_exit_area":                ("Nozzle exit area", "m^2"),
    "nozzle_throat_radius":            ("Nozzle throat radius", "m"),
    "nozzle_exit_radius":              ("Nozzle exit radius", "m"),
    "nozzle_gas_exit_pressure":        ("Nozzle exit pressure", "Pa"),
    "nozzle_gas_exit_temperature":     ("Nozzle exit temperature", "K"),
    "nozzle_gas_exit_velocity":        ("Nozzle exit velocity", "m/s"),
    "average_fuel_mass_flow_rate":     ("Average fuel mass flow", "kg/s"),
    "total_propellant_mass_flow_rate": ("Total propellant flow", "kg/s"),
    "initial_internal_fuel_radius":    ("Initial internal fuel radius", "m"),
    # dimensionless, listed so they get a decent label rather than a raw key
    "average_oxidizer_to_fuel_ratio":  ("Average O/F ratio", "."),
    "thrust_to_weight_ratio":          ("Thrust-to-weight ratio", "."),
    "heat_capacity_ratio":             ("Heat capacity ratio", "."),
    "nozzle_gas_exit_mach_number":     ("Nozzle exit Mach", "."),
    "chamber_gas_molar_weight":        ("Chamber gas molar mass", "kg/mol"),
}


# How far the rocket WENT, as opposed to how big a part of it is. A key whose
# name contains one of these is a mission distance: metres and feet, not
# centimetres and inches.
#
# Matched on the name rather than enumerated, because unsteady emits dozens of
# these (apogee_m_asl, apogee_m_agl, max_altitude_m, downrange_m, ...) and any
# fixed list would go stale the first time someone adds an output.
_DISTANCE_WORDS = (
    "apogee", "altitude", "downrange", "range", "distance", "asl", "agl",
)


def category_of_key(key: str) -> Optional[str]:
    """The DISPLAY category for a result key, or None if we can't tell.

    Needed because "length" and "distance" share a unit table: both are metres
    in SI, so the unit string alone can't say whether a value is a grain
    diameter (centimetres, inches) or an apogee (metres, feet).

    The registry wins when it knows the key. Otherwise, if the key is
    length-dimensioned, the name decides.
    """
    spec = outputs.find(key)
    if spec is not None:
        return None if spec.category in (outputs.DIMENSIONLESS, outputs.TEXT) else spec.category

    if registry.has(key):
        category = registry.get(key).category
        return None if category == "dimensionless" else category

    _label, si_unit = _describe_uncategorised(key)
    if si_unit and vc.category_of(si_unit) == "length":
        lowered = key.lower()
        if any(word in lowered for word in _DISTANCE_WORDS):
            return "distance"
        return "length"
    return None


def display_scale_of(key: str) -> float:
    """What to multiply a stored value by before showing it.

    2.0 for the radius keys, 1.0 for everything else. The physics stores radii and
    people read diameters, and this is the single place that gap is bridged.
    """
    spec = outputs.find(key)
    return spec.display_scale if spec is not None else 1.0


def describe(key: str) -> tuple[str, Optional[str]]:
    """(label, SI unit) for a result key.  Unit is None when dimensionless."""
    described = outputs.describe(key)
    if described is not None:
        return described
    if registry.has(key):
        spec = registry.get(key)
        if spec.category == "dimensionless":
            return spec.label, None
        return spec.label, vc.SI_UNITS[spec.category]
    return _describe_uncategorised(key)


def _describe_uncategorised(key: str) -> tuple[str, Optional[str]]:
    """The half of describe() that doesn't consult the field registry.

    Split out so category_of_key() can reach it without recursing back through
    describe(), which would call category_of_key() again.
    """
    if key in _COMPUTED_FIELDS:
        label, unit = _COMPUTED_FIELDS[key]
        return label, (None if unit == "." else unit)

    # The trajectory tab summarises each series as <name>_max / <name>_final.
    # Those aren't separate quantities, so resolve the stem and keep the
    # qualifier in the label.
    for qualifier in ("_max", "_final"):
        if key.endswith(qualifier) and key[: -len(qualifier)] in _COMPUTED_FIELDS:
            label, unit = _COMPUTED_FIELDS[key[: -len(qualifier)]]
            return (f"{label} ({qualifier.lstrip('_')})",
                    None if unit == "." else unit)

    return _prettify(key), None


def _prettify(key: str) -> str:
    """Turn a snake_case key into something readable."""
    return key.replace("_", " ").strip().capitalize() or key


# =============================================================================
# Formatting
# =============================================================================

# Narrow no-break space. A plain space would let a number wrap across two lines,
# and a non-breaking space is wide enough to read as two separate numbers.
_GROUP_SEP = "\u202f"


def _group_digits(text: str) -> str:
    """Space the integer part into threes: 34693.08 -> 34\u202f693.08.

    Display only. Everything that exports a number takes it from
    value_for_display() instead, so no separator ever reaches a CSV cell or the
    clipboard. Scientific notation is left alone: grouping the mantissa of
    1.32e-04 helps nobody.
    """
    if "e" in text or "E" in text:
        return text
    sign = ""
    if text[:1] in "+-":
        sign, text = text[0], text[1:]
    whole, dot, frac = text.partition(".")
    if len(whole) > 3:
        groups = [whole[max(0, i - 3):i] for i in range(len(whole), 0, -3)][::-1]
        whole = _GROUP_SEP.join(groups)
    return f"{sign}{whole}{dot}{frac}"


def format_scalar(value: Any) -> str:
    """Render one value for display.

    Trims trailing zeros, drops a pointless ".0", switches to scientific notation
    for very small numbers instead of showing "0", and groups long integer parts
    so a six-digit figure can be read at a glance.
    """
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return _group_digits(str(value))
    if isinstance(value, float):
        if value != value:                  # NaN
            return "—"
        if abs(value) < 1e-15:
            return "0"
        if abs(value - round(value)) < 1e-9 and abs(value) < 1e15:
            return _group_digits(str(int(round(value))))
        if abs(value) < 1e-3 or abs(value) >= 1e7:
            return f"{value:.4g}"
        # Decimals earn their place by how much sits to the left of the point.
        # 616.7358 is false precision and 8.019 is not, so the count shrinks as the
        # number grows. Below 1 there is nothing to the left to count, so fall back
        # to significant figures: a fixed three decimals would round 0.0015 to 0.002.
        magnitude = abs(value)
        if magnitude < 1:
            return f"{value:.4g}"
        if magnitude < 10:
            decimals = 3
        elif magnitude < 100:
            decimals = 2
        else:
            decimals = 1
        return _group_digits(f"{value:.{decimals}f}".rstrip("0").rstrip("."))
    if isinstance(value, dict):
        return f"({len(value)} keys)"
    if isinstance(value, (list, tuple)):
        return f"[{len(value)} items]"
    return str(value)


def as_pair(value: Any) -> Optional[tuple[float, str]]:
    """Recognise a config-style [value, unit] pair.

    Results files echo the inputs back verbatim, pairs included, so a results
    page will meet them. Without this they render as "[2 items]", which is
    both useless and slightly insulting.
    """
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    number, unit = value
    if isinstance(number, bool) or not isinstance(number, (int, float)):
        return None
    if not isinstance(unit, str) or not vc.is_known_unit(unit):
        return None
    return float(number), unit


def native_system_of(results: dict) -> str:
    """Which unit system a results file's numbers are actually stored in.

    NOT always SI. steady_main rewrites every dict in place when
    simulation_settings.output_units is "MRT", so an MRT run's file holds feet
    and psi. Read it back as SI and every number on the page is wrong by a
    conversion factor — which is how the shortfall dialog came to announce a
    45000 ft target as "45000 m".

    Only "MRT" triggers that rewrite in the backend; "IMP" falls through and
    the file stays SI. Mirror that rather than what the setting is named.
    """
    units = ((results or {}).get("simulation_settings") or {}).get("output_units")
    return "MRT" if units == "MRT" else "SI"


def value_for_display(value: Any, si_unit: Optional[str], system: str,
                      category: Optional[str] = None,
                      native_system: str = "SI") -> tuple[Any, str]:
    """(converted value, unit label) for a value in the given unit system.

    The number itself, NOT a formatted string. Conversion and formatting are
    separate on purpose: the screen wants a rounded, grouped, human-readable
    string, and an export wants the number. Producing the string first and
    parsing it back is how a CSV ends up full of text cells.

    `category` overrides what would otherwise be inferred from `si_unit`. Pass
    it whenever you know it: metres are both "length" and "distance", and only
    the caller can say which.

    `native_system` is the system the STORED value is in. See
    native_system_of(); it is not always SI.

    Non-numeric values and dimensionless quantities pass through untouched.
    """
    # A pair carries its own unit, which beats whatever the registry guessed
    # for the key.
    pair = as_pair(value)
    if pair is not None:
        number, unit = pair
        try:
            target = vc.unit_for_system(vc.category_of(unit), system)
            return vc.convert(number, unit, target), target
        except (ValueError, KeyError):
            return number, unit

    if si_unit is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return value, ""
    try:
        resolved = category or vc.category_of(si_unit)
        source = vc.storage_unit(resolved, native_system)
        target = vc.unit_for_system(resolved, system)
        return vc.convert(float(value), source, target), target
    except (ValueError, KeyError):
        return value, si_unit


def convert_for_display(value: Any, si_unit: Optional[str], system: str,
                        category: Optional[str] = None,
                        native_system: str = "SI") -> tuple[str, str]:
    """(formatted value, unit label) for a value in the given unit system.

    The display half of value_for_display(). Everything that puts a number on
    screen goes through here; anything exporting one goes through the other.
    """
    raw, unit = value_for_display(value, si_unit, system, category, native_system)
    return format_scalar(raw), unit


# =============================================================================
# The widget
# =============================================================================

class KVRow(ctk.CTkFrame):
    """A name/value row that can re-unit itself without being rebuilt."""

    _NAME_WIDTH = 340

    def __init__(self, master, key: str, value: Any, system: str = "SI",
                 *, name_width: Optional[int] = None,
                 native_system: str = "SI",
                 label: Optional[str] = None) -> None:
        super().__init__(master, fg_color="transparent")

        self.key = key
        self._value = value
        self._label, self._si_unit = describe(key)
        if label is not None:
            # Some rows are named by where they sit rather than by their key:
            # "Diameter" under Pre chamber, "Length" under Fuel cell.
            self._label = label
        self._category = category_of_key(key)
        self._native_system = native_system

        # Kept so exports can carry the number rather than re-parsing the label.
        # Same quantity and same unit as the screen shows, just unrounded and
        # ungrouped. See _as_table() in results_page.
        self._scale = display_scale_of(key)
        self._raw, unit_label = value_for_display(self._scaled(value), self._si_unit,
                                                  system, self._category, native_system)
        self._unit_label = unit_label
        shown = self._compose_value(self._raw, unit_label)

        self._name_widget = ctk.CTkLabel(
            self, text=self._compose_name(unit_label),
            width=name_width or self._NAME_WIDTH, anchor="w",
        )
        self._name_widget.pack(side="left", padx=(0, theme.PAD_S))

        self._value_widget = ctk.CTkLabel(
            self, text=shown, anchor="w", justify="left", wraplength=520,
        )
        self._value_widget.pack(side="left", fill="x", expand=True,
                                padx=(0, theme.PAD_L))

    def _scaled(self, value: Any) -> Any:
        """`value` with the registry's display scale applied, if it has one."""
        if self._scale == 1.0 or not isinstance(value, (int, float)) or isinstance(value, bool):
            return value
        return value * self._scale

    def _compose_name(self, unit_label: str) -> str:
        """The name column. Just the name: the unit belongs beside the number.

        "Internal diameter ... 20 cm" reads the way a person says it. Putting the
        unit in the name column instead leaves the value dangling and pushes the
        unit away from the figure it qualifies.
        """
        return self._label

    def _compose_value(self, raw: Any, unit_label: str) -> str:
        shown = pretty_unit(unit_label)
        text = format_scalar(raw)
        return f"{text} {shown}" if shown and text != "—" else text

    def update_system(self, system: str) -> None:
        """Re-label and re-convert for a new unit system.  No rebuild."""
        self._raw, unit_label = value_for_display(self._scaled(self._value), self._si_unit,
                                                  system, self._category, self._native_system)
        self._unit_label = unit_label
        self._name_widget.configure(text=self._compose_name(unit_label))
        self._value_widget.configure(text=self._compose_value(self._raw, unit_label))

    @property
    def label(self) -> str:
        """The row's display name, after any per-row override.

        What the search matches against: the name of the thing, not the section
        it sits in or the number it currently holds.
        """
        return self._label

    @property
    def raw_value(self) -> Any:
        """The number behind the label, in the unit currently on screen.

        What exports should use. The displayed string is rounded and, once digit
        grouping lands, will carry separators too, neither of which belongs in a
        CSV cell or on the clipboard.
        """
        return self._raw

    @property
    def unit_label(self) -> str:
        """The unit currently shown beside this value, or "" when there is none."""
        return self._unit_label

    def matches(self, query: str) -> bool:
        """Whether this row's NAME contains the query.

        Name only. Searching "chamber" should find the values actually called
        chamber something, not every row that happens to live inside CV4, and not
        every row whose current number contains those digits.
        """
        if not query or not query.strip():
            return True
        return query.lower().strip() in self._label.lower()



# =============================================================================
# Search results
# =============================================================================
#
# One line per hit:
#
#     Hardware & Parameters › CV6: Trajectory › Flight parameters ›
#     Horizontal distance at landing ......... 4 210.5 m
#
# The breadcrumb is muted and the name is not, because the name is what was
# searched for and the path is only there to say where to click next time.
#
# TWO RULES, BOTH LEARNED THE HARD WAY
#
# A row never writes to itself from inside a <Configure> handler. The dot
# leader has to be measured, and measuring inside the event that layout fires
# means every measurement can provoke the next one; the results page calls
# draw_dots() from a debounced timer instead, so a write lands after layout has
# settled rather than in the middle of it.
#
# No cell is ever allowed to reach zero width. Tk asks Windows for an
# off-screen bitmap the size of the widget it is drawing, CreateDIBSection
# refuses a zero-sized one, and Tk's response to that is to panic and abort the
# process rather than to raise something Python could catch. Hence grid with a
# minsize on every column, rather than pack with an expanding filler that gets
# squeezed to nothing the moment a row's content overflows.
#
# Rows are also reused rather than rebuilt: show() re-points an existing row at
# a different result. Building three hundred CustomTkinter widgets per
# keystroke, each one a canvas, is what put the process near that limit.

_CRUMB = "  ›  "          # single right-pointing angle quote, with air around it

# How much wider than measured to assume a dot is, and how many to leave off
# the end. Both exist so a row underfills rather than overflows: the font is
# measured at its nominal size while Tk draws it scaled, so the measurement is
# an underestimate on any display that is not at 100%.
_DOT_FUDGE = 1.15
_DOT_HEADROOM = 4


class SearchResultRow(ctk.CTkFrame):
    """One search hit. Built once, then re-pointed with show()."""

    def __init__(self, master, *, system: str = "SI",
                 native_system: str = "SI") -> None:
        super().__init__(master, fg_color="transparent")

        self.key = ""
        self._label = ""
        self._value: Any = None
        self._raw: Any = None
        self._text_builder: Optional[Callable[[str], str]] = None
        self._si_unit: Optional[str] = None
        self._category: Optional[str] = None
        self._scale = 1.0
        self._system = system
        self._native_system = native_system
        self._dot_count = -1

        for column, weight, minsize in ((0, 0, 8), (1, 0, 8), (2, 1, 16), (3, 0, 8)):
            self.grid_columnconfigure(column, weight=weight, minsize=minsize)

        self._crumb_widget = ctk.CTkLabel(self, text="", anchor="w",
                                          text_color=theme.TEXT_MUTED)
        self._crumb_widget.grid(row=0, column=0, sticky="w")

        self._name_widget = ctk.CTkLabel(self, text="", anchor="w")
        self._name_widget.grid(row=0, column=1, sticky="w")

        self._dots = ctk.CTkLabel(self, text="", anchor="w",
                                  text_color=theme.TEXT_MUTED)
        self._dots.grid(row=0, column=2, sticky="ew", padx=theme.PAD_XS)

        self._value_widget = ctk.CTkLabel(self, text="", anchor="e")
        self._value_widget.grid(row=0, column=3, sticky="e",
                                padx=(theme.PAD_S, 0))

    # ------------------------------------------------------------------

    def show(self, *, key: str, label: str, value: Any, path: tuple,
             system: str, native_system: str,
             text_builder: Optional[Callable[[str], str]] = None) -> None:
        """Point this row at a result. Replaces text; creates no widgets."""
        self.key = key
        self._label = label
        self._value = value
        self._system = system
        self._native_system = native_system
        self._text_builder = text_builder
        if text_builder is None:
            self._si_unit = describe(key)[1]
            self._category = category_of_key(key)
            self._scale = display_scale_of(key)
        else:
            # A verdict in words, or two numbers sharing one unit. Nothing in
            # the registry describes those; the builder is the whole answer.
            self._si_unit, self._category, self._scale = None, None, 1.0

        self._crumb_widget.configure(
            text=(_CRUMB.join(path) + _CRUMB) if path else "")
        self._name_widget.configure(text=label)
        self._dot_count = -1
        self._dots.configure(text="")
        self._write_value()

    def update_system(self, system: str) -> None:
        """Re-convert for a new unit system, same as an ordinary row."""
        self._system = system
        self._write_value()

    @property
    def raw_value(self) -> Any:
        return self._raw

    @property
    def label(self) -> str:
        return self._label

    # ------------------------------------------------------------------

    def _write_value(self) -> None:
        if self._text_builder is not None:
            try:
                text = self._text_builder(self._system)
            except Exception:                   # noqa: BLE001
                text = "—"
            self._raw = text
            self._value_widget.configure(text=text)
            return

        scaled = self._value
        if (self._scale != 1.0 and isinstance(self._value, (int, float))
                and not isinstance(self._value, bool)):
            scaled = self._value * self._scale
        raw, unit = value_for_display(scaled, self._si_unit, self._system,
                                      self._category, self._native_system)
        self._raw = raw
        shown = pretty_unit(unit)
        text = format_scalar(raw)
        self._value_widget.configure(
            text=f"{text} {shown}" if shown and text != "—" else text)

    def draw_dots(self, available: int) -> None:
        """Fill the gap with a leader, given the width the row has to work in.

        Called from the page, never from an event on this widget. `available`
        is the width of the list, not of this row: asking the row how wide it
        is means asking about a layout this call is about to change.
        """
        if available <= 1:
            return
        try:
            used = (self._crumb_widget.winfo_reqwidth()
                    + self._name_widget.winfo_reqwidth()
                    + self._value_widget.winfo_reqwidth()
                    + 6 * theme.PAD_S)
            count = max(int((available - used) // self._dot_width())
                        - _DOT_HEADROOM, 0)
            if count == self._dot_count:
                return
            self._dot_count = count
            self._dots.configure(text="." * count)
        except Exception:                       # noqa: BLE001
            self._dot_count = 0
            self._dots.configure(text="")

    def _dot_width(self) -> int:
        """Width of one dot in real pixels, rounded up.

        cget("font") reports the nominal size; CustomTkinter draws it
        multiplied by the display's widget scaling, so the raw measurement is
        an underestimate on a display that is not at 100%. Overestimating
        costs a few dots. Underestimating overflows the row.
        """
        font = self._dots.cget("font")
        try:
            scaling = ctk.ScalingTracker.get_widget_scaling(self)
        except Exception:                       # noqa: BLE001
            scaling = 1.0
        return max(int(round(font.measure(".") * scaling * _DOT_FUDGE)), 1)
