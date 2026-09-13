"""
Unit conversions for the whole program (backend + UI)
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence


# Dimensionless
# ratios, coefficients, exponents, counts.  "." is the canonical spelling used throughout the config files
# left here to simplify some functions (this way we don't need to check if a value actually has a unit before converting)
DIMENSIONLESS: dict[str, float] = {".": 1.0,}

# Length
# SI: m
LENGTH: dict[str, float] = {
    "m": 1.0,
    "mm": 1e-3,
    "cm": 1e-2,
    "km": 1e3,
    "in": 0.0254,
    "ft": 0.3048,
    "yd": 0.9144,
    "mi": 1609.344,
}

# Area
# SI: m^2
AREA: dict[str, float] = {
    "m^2": 1.0,
    "mm^2": 1e-6,
    "cm^2": 1e-4,
    "in^2": 0.0254 ** 2, # 6.4516e-4
    "ft^2": 0.3048 ** 2, # 0.09290304
}

# Volume
# SI: m^3
VOLUME: dict[str, float] = {
    "m^3": 1.0,
    "mm^3": 1e-9,
    "cm^3": 1e-6,
    "L": 1e-3,
    "in^3": 0.0254 ** 3, # 1.6387064e-5
    "ft^3": 0.3048 ** 3, # 0.028316846592
    "gal": 3.785411784e-3, # US liquid gallon
}

# Mass
# SI: kg
MASS: dict[str, float] = {
    "kg": 1.0,
    "g": 1e-3,
    "mg": 1e-6,
    "t": 1e3, # metric tonne
    "lb": 0.45359237,
    "oz": 0.45359237 / 16.0, # 0.028349523125
}

# Density
# SI: kg/m^3
DENSITY: dict[str, float] = {
    "kg/m^3": 1.0,
    "g/cm^3": 1e3,
    "g/L": 1.0, # identical to kg/m^3, but people write both
    "kg/L": 1e3,
    "lb/ft^3": 0.45359237 / 0.028316846592, # 16.018463373960142
    "lb/in^3": 0.45359237 / 1.6387064e-5, # 27679.904710203125
}

# Pressure
# SI: Pa
PRESSURE: dict[str, float] = {
    "Pa": 1.0,
    "kPa": 1e3,
    "MPa": 1e6,
    "bar": 1e5,
    "mbar": 1e2,
    "psi": 6894.757293168361,
    "atm": 101325.0,
    "torr": 101325.0 / 760.0,  # 133.32236842105263
}

# Temperature
# SI: K
# The only category with an offset, so it gets functions instead of a factor table.
# TEMPERATURE still lists the accepted units so the generic helpers and the UI dropdowns can find them.
TEMPERATURE: dict[str, float] = {
    "K": 1.0,
    "C": 1.0, # offset handled below
    "F": 1.0, # offset + scale handled below
    "R": 1.0, # Rankine: pure scale, no offset
}

def temperature_to_SI(value: float, unit: str) -> float:
    """Any accepted temperature unit --> kelvin."""
    unit = _canonical(unit)
    if unit == "K":
        return value
    if unit == "C":
        return value + 273.15
    if unit == "F":
        return (value - 32.0) * 5.0 / 9.0 + 273.15
    if unit == "R":
        return value * 5.0 / 9.0
    raise ValueError(f"Unknown temperature unit: {unit!r}")

def temperature_from_SI(value_K: float, unit: str) -> float:
    """Kelvin --> any accepted temperature unit."""
    unit = _canonical(unit)
    if unit == "K":
        return value_K
    if unit == "C":
        return value_K - 273.15
    if unit == "F":
        return (value_K - 273.15) * 9.0 / 5.0 + 32.0
    if unit == "R":
        return value_K * 9.0 / 5.0
    raise ValueError(f"Unknown temperature unit: {unit!r}")



# Time
# SI: s
TIME: dict[str, float] = {
    "s": 1.0,
    "ms": 1e-3,
    "us": 1e-6,
    "min": 60.0,
    "h": 3600.0,
}

# Angle
# SI: rad
# note to_SI() gives radians
ANGLE: dict[str, float] = {
    "rad": 1.0,
    "deg": 0.017453292519943295,   # pi / 180
    "grad": 0.015707963267948967,   # pi / 200
}

# Velocity
# SI: m/s
VELOCITY: dict[str, float] = {
    "m/s": 1.0,
    "km/h": 1000.0 / 3600.0, # 0.2777777777777778
    "ft/s": 0.3048,
    "mph": 1609.344 / 3600.0, # 0.44704
    "kn": 1852.0 / 3600.0, # 0.5144444444444445
}

# Acceleration
# SI: m/s^2
ACCELERATION: dict[str, float] = {
    "m/s^2":  1.0,
    "ft/s^2": 0.3048,
    "g0":    9.80665, # standard gravity in case we ever want to measure in g's
}

# Force
# SI: N
FORCE: dict[str, float] = {
    "N": 1.0,
    "kN": 1e3,
    "lbf": 4.4482216152605,
}

# Impulse
# SI: N*s
IMPULSE: dict[str, float] = {
    "N*s": 1.0,
    "kN*s": 1e3,
    "lbf*s": 4.4482216152605,
}

# Mass flow rate
# SI: kg/s
MASS_FLOW: dict[str, float] = {
    "kg/s": 1.0,
    "g/s": 1e-3,
    "lb/s": 0.45359237,
}

# Molar mass
# SI: kg/mol
# CEA reports chamber molecular weight, which surfaces in the results tables
MOLAR_MASS: dict[str, float] = {
    "kg/mol": 1.0,
    "g/mol": 1e-3,
}


################################################################################################################
# REGISTRY
# these three tables are what the generic helpers, the UI dropdowns, and the config validator all read "distance" shares the LENGTH table but is a separate DISPLAY category.
CATEGORIES: dict[str, dict[str, float]] = {
    "dimensionless": DIMENSIONLESS,
    "length": LENGTH,
    "canopy_length": LENGTH,
    "injector_length": LENGTH,
    "distance": LENGTH,
    "area": AREA,
    "canopy_area": AREA,
    "injector_area": AREA,
    "volume": VOLUME,
    "mass": MASS,
    "density": DENSITY,
    "pressure": PRESSURE,
    "temperature": TEMPERATURE,
    "time": TIME,
    "angle": ANGLE,
    "velocity": VELOCITY,
    "acceleration": ACCELERATION,
    "force": FORCE,
    "impulse": IMPULSE,
    "mass_flow": MASS_FLOW,
    "molar_mass": MOLAR_MASS,
}

# SI unit of each category
# parachutes, injectors, etc have special units (ie m, mm, etc)
SI_UNITS: dict[str, str] = {
    "dimensionless": ".",
    "length": "m",
    "distance": "m", # same physical dimension as length; see CATEGORIES
    "area": "m^2",
    "volume": "m^3",
    "canopy_length": "m",
    "canopy_area": "m^2",
    "injector_length": "m",
    "injector_area": "m^2",
    "mass": "kg",
    "density": "kg/m^3",
    "pressure": "Pa",
    "temperature": "K",
    "time": "s",
    "angle": "rad",
    "velocity": "m/s",
    "acceleration": "m/s^2",
    "force": "N",
    "impulse": "N*s",
    "mass_flow": "kg/s",
    "molar_mass": "kg/mol",
    "regression_coefficient": "(m/s)/(kg/m^2/s)^n",
}

# alternate spellings people (and older config files) use (maps alias --> canonical unit string)
# "g" --> gram (not standard gravity; write "g0")
# "kn" --> knot (not kilonewton, write "kN"; case matters)
# "ms" --> millisecond (not metres per second, write "m/s")
ALIASES: dict[str, str] = {
    # dimensionless
    "": ".",
    "-": ".",
    "unitless": ".",
    # length
    "meter": "m", "metre": "m", "meters": "m", "metres": "m",
    "inch": "in", "inches": "in", '"': "in",
    "foot": "ft", "feet": "ft", "'": "ft",
    # area.  The bare forms were the canonical spelling before v1.6, so every one of
    # them has to keep resolving: results files and saved presets still hold them.
    "m2": "m^2", "m**2": "m^2", "m²": "m^2",
    "mm2": "mm^2", "mm**2": "mm^2", "cm2": "cm^2", "cm**2": "cm^2",
    "in2": "in^2", "in**2": "in^2", "sq_in": "in^2",
    "ft2": "ft^2", "ft**2": "ft^2", "sq_ft": "ft^2",
    # volume
    "m3": "m^3", "m**3": "m^3", "m³": "m^3",
    "mm3": "mm^3", "cm3": "cm^3", "cc": "cm^3",
    "in3": "in^3", "ft3": "ft^3",
    "l": "L", "liter": "L", "litre": "L",
    # mass
    "lbm": "lb", "lbs": "lb", "pound": "lb",
    "kilogram": "kg", "gram": "g", "tonne": "t",
    # density
    "kg/m3": "kg/m^3", "kg/m**3": "kg/m^3", "kg/m³": "kg/m^3", "kgm3": "kg/m^3",
    "g/cm3": "g/cm^3", "g/cc": "g/cm^3", "g/cm**3": "g/cm^3",
    "lbm/ft3": "lb/ft^3", "lb/ft3": "lb/ft^3", "lbm/ft^3": "lb/ft^3",
    "lbm/in3": "lb/in^3", "lb/in3": "lb/in^3", "lbm/in^3": "lb/in^3",
    # pressure
    "pa": "Pa", "PA": "Pa", "kpa": "kPa", "mpa": "MPa",
    "PSI": "psi", "Bar": "bar", "ATM": "atm", "Torr": "torr",
    # temperature
    "degC": "C", "°C": "C", "celsius": "C",
    "degK": "K", "kelvin": "K",
    "degF": "F", "°F": "F", "fahrenheit": "F",
    "degR": "R", "rankine": "R",
    # time
    "sec": "s", "secs": "s", "seconds": "s",
    "µs": "us", "μs": "us",
    "minute": "min", "hr": "h", "hour": "h",
    # angle
    "degree": "deg", "degrees": "deg", "°": "deg",
    "radian": "rad", "radians": "rad",
    # velocity
    "m/sec": "m/s",
    "fps": "ft/s", "ft/sec": "ft/s",
    "kph": "km/h", "knot": "kn", "knots": "kn",
    # acceleration
    "m/s2": "m/s^2", "m/s**2": "m/s^2", "m/s²": "m/s^2",
    "ft/s2": "ft/s^2", "ft/s**2": "ft/s^2",
    # force
    "newton": "N",
    # impulse
    "Ns": "N*s", "N.s": "N*s", "N s": "N*s",
    "lbf.s": "lbf*s", "lbfs": "lbf*s",
    # mass flow
    "kg/sec": "kg/s", "lbm/s": "lb/s", "lb/sec": "lb/s",
    # molar mass
    "kg/kmol": "g/mol", # numerically identical
}


# lookup helpers
def _canonical(unit: Any) -> str:
    """
    resolve a user-written unit string to its canonical spelling
    """
    if unit is None:
        return "."
    u = str(unit).strip()
    if _find_category(u) is not None:
        return u
    if u in ALIASES:
        return ALIASES[u]
    lowered = u.lower()
    for alias, canonical in ALIASES.items():
        if alias.lower() == lowered:
            return canonical
    return u


def _find_category(unit: str) -> Optional[str]:
    """category containing this EXACT unit string, or None (no alias lookup)"""
    if unit in REGRESSION_UNITS:
        return REGRESSION_COEFFICIENT
    for category, table in CATEGORIES.items():
        if unit in table:
            return category
    return None


def category_of(unit: Any) -> str:
    """
    which physical category a unit belongs to
        category_of("psi") --> "pressure"
        category_of("kg/m^3") --> "density"
    """
    u = _canonical(unit)
    category = _find_category(u)
    if category is None:
        raise ValueError(f"Unknown unit: {unit!r}. Accepted units listed in CATEGORIES in variable_conversions.py.")
    return category


def SI_unit_of(unit: Any) -> str:
    """The SI unit of whatever category this unit belongs to. eg "in" --> "m"."""
    return SI_UNITS[category_of(unit)]


def units_in_category(category: str) -> list[str]:
    """
    every accepted unit in a category
    """
    if category == REGRESSION_COEFFICIENT:
        return list(REGRESSION_UNITS)
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category: {category!r}")
    return list(CATEGORIES[category].keys())


def is_known_unit(unit: Any) -> bool:
    """True if this unit string (or an alias of it) resolves to something"""
    return _find_category(_canonical(unit)) is not None


def same_category(unit_a: Any, unit_b: Any) -> bool:
    """True if both units measure the same physical quantity"""
    return category_of(unit_a) == category_of(unit_b)


########################################################################################################################################
# conversions
# convert a value from a user-facing unit into SI
def to_SI(value: Optional[float], unit: Any) -> Optional[float]:
    if value is None:
        return None
    u = _canonical(unit)
    category = category_of(u)
    if category == "temperature":
        return temperature_to_SI(float(value), u)
    if category == REGRESSION_COEFFICIENT:
        raise ValueError(_REGRESSION_MISUSE.format(unit=u, fn="regression_to_SI"))
    return float(value) * CATEGORIES[category][u]

# opposite of to_SI
def from_SI(value: Optional[float], unit: Any) -> Optional[float]:
    if value is None:
        return None
    u = _canonical(unit)
    category = category_of(u)
    if category == "temperature":
        return temperature_from_SI(float(value), u)
    if category == REGRESSION_COEFFICIENT:
        raise ValueError(_REGRESSION_MISUSE.format(unit=u, fn="regression_from_SI"))
    return float(value) / CATEGORIES[category][u]

# convert between any two units of the same category
def convert(value: Optional[float], from_unit: Any, to_unit: Any) -> Optional[float]:
    if value is None:
        return None
    src, dst = _canonical(from_unit), _canonical(to_unit)
    if category_of(src) != category_of(dst):
        raise ValueError(f"Cannot convert {src!r} ({category_of(src)}) to {dst!r} ({category_of(dst)}) — different categories.")
    return from_SI(to_SI(value, src), dst)

# takes a [value, unit] config pair, returns just 'value' as an SI float
def pair_to_SI(pair: Any) -> Any:
    if pair is None:
        return None
    if isinstance(pair, (list, tuple)):
        if len(pair) != 2:
            raise ValueError(f"Expected a [value, unit] pair, got {len(pair)} element(s): {pair!r}")
        value, unit = pair
        if value is None or value == "":
            return None
        if isinstance(value, str):
            return value
        return to_SI(value, unit)
    if isinstance(pair, bool): # bool is an int subclass; check first
        return pair
    if isinstance(pair, (int, float)): # legacy bare number, already SI
        return float(pair)
    return pair # strings and anything else

# returns a [value, unit] pair from an SI value, expressed in 'unit'
def pair_from_SI(value: Optional[float], unit: Any) -> list:
    return [from_SI(value, unit), _canonical(unit)]

# convert an entire config block of [value, unit] pairs into bare SI floats
def block_to_SI(block: dict, skip: Iterable[str] = ("model",)) -> dict:
    skip_set = set(skip)
    out: dict = {}
    for key, value in block.items():
        if key in skip_set:
            out[key] = value
            continue
        try:
            out[key] = pair_to_SI(value)
        except ValueError as exc:
            raise ValueError(f"{key}: {exc}") from exc
    return out



# Named shorthands

#
# The old module exposed these by name and the steady MRT-output path still
# calls them.  They're thin wrappers over convert() now, kept so that code
# reads the way it always did. 

def m_to_ft(value): return convert(value, "m", "ft")
def m_to_in(value): return convert(value, "m", "in")
def ft_to_m(value): return convert(value, "ft", "m")
def in_to_m(value): return convert(value, "in", "m")

def m2_to_in2(value): return convert(value, "m^2", "in^2")
def in2_to_m2(value): return convert(value, "in^2", "m^2")

def Pa_to_psi(value): return convert(value, "Pa", "psi")
def psi_to_Pa(value): return convert(value, "psi", "Pa")

def ms_to_fts(value): return convert(value, "m/s", "ft/s")
def fts_to_ms(value): return convert(value, "ft/s", "m/s")

def K_to_C(value): return convert(value, "K", "C")
def C_to_K(value): return convert(value, "C", "K")

def deg_to_rad(value): return convert(value, "deg", "rad")
def rad_to_deg(value): return convert(value, "rad", "deg")



# Output unit systems override from SI default (display only)
UNIT_SYSTEMS: dict[str, dict[str, str]] = {
    "SI": {
        # Radians are the SI unit and what the physics uses, but nobody types a launch angle in radians
        "angle": "deg",
        # most hardware measured in cm
        "length": "cm",
        "area": "cm^2",
        "volume": "L",
        "canopy_length": "m",
        "canopy_area": "m^2",
        "injector_length": "mm",
        "injector_area": "mm^2",
        # display pressures in kPa
        "pressure": "kPa",
        # this is a whole thing, TODO: include an explanation in docs/developer_manual
        "regression_coefficient": "(mm/s)/(kg/m^2/s)^n",
    },
    "MRT": {
        "angle": "deg",
        "length": "in", # hardware
        "distance": "ft", # apogees, altitudes
        "area": "in^2",
        "volume": "in^3", # hardware volume follows hardware length, as in SI
        "canopy_length": "ft",
        "canopy_area": "ft^2",
        "injector_length": "mm",
        "injector_area": "mm^2",
        "pressure": "psi",
        "velocity": "ft/s",
        "acceleration": "ft/s^2",
        "regression_coefficient": "(mm/s)/(kg/m^2/s)^n",
    },
    "IMP": {
        "angle": "deg",
        "length": "in", # hardware
        "distance": "ft", # apogees, altitudes
        "area": "in^2",
        "volume": "in^3",
        "canopy_length": "ft",
        "canopy_area": "ft^2",
        "injector_length": "in",
        "injector_area": "in^2",
        "mass": "lb",
        "density": "lb/ft^3",
        "pressure": "psi",
        "temperature": "F",
        "velocity": "ft/s",
        "acceleration": "ft/s^2",
        "force": "lbf",
        "impulse": "lbf*s",
        "mass_flow": "lb/s",
        "regression_coefficient": "(in/s)/(lbm/in^2/s)^n",
    },
}

# display unit a given unit system wants for a category
def unit_for_system(category: str, system: str = "SI") -> str:
    if category not in SI_UNITS:
        raise ValueError(f"Unknown category: {category!r}")
    return UNIT_SYSTEMS.get(system, {}).get(category, SI_UNITS[category])

def storage_unit(category: str, system: str = "SI") -> str:
    """The unit a results FILE stores this category in, for a given system.

    Not the same as unit_for_system(), which is a DISPLAY preference. An SI
    results file holds SI base units — metres, pascals — while the SI display
    system shows hardware lengths in centimetres. Confusing the two makes a
    0.6096 m fuel grain read as 0.6096 cm.

    Only "MRT" makes the backend rewrite a file away from SI (see
    steady_main.convert_*_SI_to_MRT), and it rewrites into exactly the units
    the MRT display table names, so that case can share the table.
    """
    if category not in SI_UNITS:
        raise ValueError(f"Unknown category: {category!r}")
    if system == "SI":
        return SI_UNITS[category]
    return unit_for_system(category, system)


def to_system(value: Optional[float], category: str, system: str = "SI") -> Optional[float]:
    """Convert an SI value into whatever unit 'system' displays that category in."""
    return from_SI(value, unit_for_system(category, system))

##########################################
# REGRESSION COEFFICIENT
#
# fuel regression law: r_dot = a * G_ox ** n
# [a] = L^(1+2n) * M^(-n) * T^(n-1)
#
###### n implicit, eg "0.132 mm/s per (kg/m^2/s)^n"
# a_SI = a_unit * rate_in_m_per_s * flux_in_SI ** (-n) is the new convention

REGRESSION_COEFFICIENT = "regression_coefficient"

REGRESSION_UNITS: dict[str, tuple[str, str, str]] = {
    "(m/s)/(kg/m^2/s)^n": ("m",  "kg", "m^2"), # SI base; what results files store
    "(mm/s)/(kg/m^2/s)^n": ("mm", "kg", "m^2"), # what the literature quotes
    "(in/s)/(lbm/in^2/s)^n": ("in", "lb", "in^2"), # disgusting IMPs
}

# raiseerror message
_REGRESSION_MISUSE = "Unit {unit!r} is a regression coefficient: its dimensions depend on the regression exponent n, so it cannot go through the generic converter. Use {fn}(value, unit, n) instead."

# true if this unit string names one of the regression-law conventions
def is_regression_unit(unit: Any) -> bool:
    return _canonical(unit) in REGRESSION_UNITS

# multiplies 'unit' by n to get the SI coefficient
    # ie 
    # regression_factor("(mm/s)/(kg/m^2/s)^n", 0.555) --> 1e-3
    # regression_factor("(in/s)/(lbm/in^2/s)^n", 0.555) --> 6.6796e-4
# "." is accepted and returns 1 so that older configs don't break
def regression_factor(unit: Any, n: float) -> float:
    u = _canonical(unit)
    if u == ".":
        return 1.0
    if u not in REGRESSION_UNITS:
        raise ValueError(f"Unknown regression coefficient unit: {unit!r}. Accepted: {', '.join(REGRESSION_UNITS)}")
    length_unit, mass_unit, area_unit = REGRESSION_UNITS[u]
    rate = CATEGORIES["length"][length_unit]                     # m per rate length unit
    flux = CATEGORIES["mass"][mass_unit] / CATEGORIES["area"][area_unit]
    return rate * flux ** (-float(n))

# returns regression coef in 'unit' at exponent 'n' as an SI float
def regression_to_SI(value: Optional[float], unit: Any, n: float) -> Optional[float]:
    if value is None:
        return None
    return float(value) * regression_factor(unit, n)

# opposive of regression_to_SI
def regression_from_SI(value: Optional[float], unit: Any, n: float) -> Optional[float]:
    if value is None:
        return None
    return float(value) / regression_factor(unit, n)

# pair_to_SI() for the one input that needs the exponent alongside it
    # ie regression_pair_to_SI([0.132, "(mm/s)/(kg/m^2/s)^n"], 0.555) returns 0.000132
def regression_pair_to_SI(pair: Any, n: Optional[float]) -> Optional[float]:
    if pair is None:
        return None
    if isinstance(pair, (list, tuple)):
        if len(pair) != 2:
            raise ValueError(f"Expected a [value, unit] pair, got {pair!r}")
        value, unit = pair
    else:
        value, unit = pair, "."
    if value is None or value == "":
        return None
    u = _canonical(unit)
    # only the imperial convention actually needs n, so a missing exponent is harmless there and fatal here.
    if n is None and u != "." and REGRESSION_UNITS.get(u, ("", "", ""))[1:] != ("kg", "m^2"):
        raise ValueError(f"Cannot read a regression coefficient in {u!r} without the regression exponent n. Load n before a.")
    return regression_to_SI(float(value), u, 0.0 if n is None else n)

# pair_from_SI() for the regression coefficient
def regression_pair_from_SI(value: Optional[float], unit: Any, n: float) -> list:
    return [regression_from_SI(value, unit, n), _canonical(unit)]

