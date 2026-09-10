"""
generates one PDF describing a finished simulation

split into two parts: 
    1. run info: inputs by control volume, performance by category, per-phase breakdown, event log, warnings
    2. graphs: one plot per page

the report is always titled "Unsteady Sim Report: <run name>"

generate_report() builds its own figures through the plot registry in src/common/plotting/unsteady_plots.py rather than reading the graphs/ folder, so a report can be generated for a run that never saved PNGs
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import BaseDocTemplate, Frame, Image, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle

REPORT_FILENAME = "sim_report.pdf"

####### palette
INK = colors.HexColor("#1b1f24")
MUTED = colors.HexColor("#5b6672")
FAINT = colors.HexColor("#8a95a1")
RULE = colors.HexColor("#d4dae1")
HEADER_BG = colors.HexColor("#eef2f6")
BAND_BG = colors.HexColor("#f7f9fb")
ACCENT = colors.HexColor("#1f6feb")
SEVERITY_COLOUR = {
    "critical": "#b00020",
    "caution": "#c2410c",
    "advisory": "#0b7285",
    "debug": "#8a95a1",
}

PAGE = letter
MARGIN = 0.6 * inch
USABLE = PAGE[0] - 2 * MARGIN
FIGURE_DPI = 150 # rasterisation resolution for embedded plots, 150 good for keeping graphs readable


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=21, leading=25, textColor=INK, alignment=TA_LEFT, spaceAfter=2),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontSize=10.5, leading=14, textColor=MUTED, spaceAfter=14),
        "part": ParagraphStyle("part", parent=base["Heading1"], fontSize=15, leading=19, textColor=ACCENT, spaceBefore=6, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=11.5, leading=15, textColor=INK, spaceBefore=12, spaceAfter=5),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontSize=10, leading=13, textColor=MUTED, spaceBefore=8, spaceAfter=3),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontSize=9.5, leading=13, textColor=INK, spaceAfter=4),
        "note": ParagraphStyle("note", parent=base["BodyText"], fontSize=8.5, leading=11.5, textColor=MUTED, spaceAfter=4),
        "cell": ParagraphStyle("cell", parent=base["BodyText"], fontSize=8.5, leading=11, textColor=INK, spaceAfter=0),
        "cellhead": ParagraphStyle("cellhead", parent=base["BodyText"], fontSize=8.5, leading=11, textColor=MUTED, spaceAfter=0),
        "cellnum": ParagraphStyle("cellnum", parent=base["BodyText"], fontSize=8.5, leading=11, textColor=INK, alignment=2, spaceAfter=0),
    }


####### labels & units
try:
    from src.ui.app import field_registry as _registry
except Exception: 
    _registry = None

# result keys carry their dimension as a suffix rather than in the registry; this is an artifact from when output units were in SI only. should remove this suffix entirely in the future but that will be a ######
_SUFFIX_CATEGORIES = [("_Ns", "impulse"), ("_kg", "mass"), ("_Pa", "pressure"), ("_K", "temperature"), ("_ms", "velocity"), ("_N", "force"), ("_s", "time"),]
# geometry the loader derives rather than reads
_DERIVED_CATEGORIES = [("_radius", "length"), ("_area", "area"), ("_volume", "volume"), ("_length", "length"), ("_delta_p", "pressure"),]

# add superscripts for to be easier on the eyes to the PDF reader
_UNIT_LABELS = {
    "m^2": "m²", "mm^2": "mm²", "cm^2": "cm²", "in^2": "in²", "ft^2": "ft²",
    "m^3": "m³", "mm^3": "mm³", "cm^3": "cm³", "in^3": "in³", "ft^3": "ft³",
    "m/s^2": "m/s²", "ft/s^2": "ft/s²",
    "N*s": "N·s", "lbf*s": "lbf·s",
    "kg/m^3": "kg/m³", "g/cm^3": "g/cm³", "lb/ft^3": "lb/ft³", "lb/in^3": "lb/in³",
    "deg": "°", "C": "°C", "F": "°F", ".": "",
}


def _describe(key: str):
    """
    (label, category) for any input or result key

    category is a variable_conversions category name, or None when the value carries no unit at all (ratios, counts, flags, text).
    """
    if _registry is not None and _registry.has(key):
        spec = _registry.get(key)
        return spec.label, (None if spec.category == "dimensionless" else spec.category)

    # keep distinction between AGL or ASL, otherwise they both appear as "Apogee"
    for suffix, datum in (("_m_agl", "AGL"), ("_m_asl", "ASL")):
        if key.endswith(suffix):
            return f"{_prettify(key[: -len(suffix)])} {datum}", "distance"

    for suffix, category in _SUFFIX_CATEGORIES:
        if key.endswith(suffix):
            return _prettify(key[: -len(suffix)]), category
    for suffix, category in _DERIVED_CATEGORIES:
        if key.endswith(suffix):
            return _prettify(key), category
    return _prettify(key), None


###### unit system
# the report is drawn in whichever system was selected when it was asked for

def _native_system_of(results: Optional[dict]):
    """
    returns the unit system this results file's numbers are actually stored in
    """
    units = ((results or {}).get("simulation_settings") or {}).get("output_units")
    return "MRT" if units == "MRT" else "SI"


class _Units:
    """
    Converts one stored value into the report's display system
        'system': what the user picked (SI / IMP / MRT)
        'native': what the file holds
    """

    def __init__(self, system: str, native: str):
        from src.common import variable_conversions as vc
        self._vc = vc
        self.system = system if system in vc.UNIT_SYSTEMS else "SI"
        self.native = native

    def unit(self, category: Optional[str]):
        """
        returns prettified display unit label for a category, or "" if none
        """
        if not category:
            return ""
        try:
            raw = self._vc.unit_for_system(category, self.system)
        except ValueError:
            return ""
        return _UNIT_LABELS.get(raw, raw)

    def value(self, value, category: Optional[str]):
        """
        returns stored value expressed in the display unit, ignores non numbers
        """
        if not category or value is None or isinstance(value, bool):
            return value
        if not isinstance(value, (int, float)):
            return value
        try:
            src = self._vc.storage_unit(category, self.native)
            dst = self._vc.unit_for_system(category, self.system)
            return self._vc.convert(float(value), src, dst)
        except (ValueError, KeyError):
            return value # unknown category: show it raw

    def row(self, key: str, value):
        """
        (label, converted value, unit) format which the triple _kv_table expects
        """
        label, category = _describe(key)
        return label, self.value(value, category), self.unit(category)

def _prettify(key: str):
    text = re.sub(r"\bOF\b", "O/F", key.replace("_", " ").strip(), flags=re.I)
    return text[:1].upper() + text[1:]

# formats numbers nicely
def _fmt(value):
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        magnitude = abs(value)
        if magnitude == 0:
            return "0"
        # whole numbers stored as floats read badly as "36.000"
        if value.is_integer() and magnitude < 1e9:
            return f"{int(value):,}"
        if magnitude < 1e-3:
            return f"{value:.4g}"
        if magnitude >= 1e6:
            return f"{value:,.0f}"
        if magnitude >= 100:
            return f"{value:,.1f}"
        if magnitude >= 1:
            return f"{value:,.3f}"
        return f"{value:.4g}"
    return str(value)

# reportlab parses a small XML dialect, so these three must be escaped
def _esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


###### tables
def _kv_table(st, rows, widths=(0.56, 0.28, 0.16)):
    """l
    abel / value / unit -- the shape every block in part 1 uses
    """
    data = [[Paragraph(_esc(label), st["cell"]), Paragraph(_esc(_fmt(value)), st["cellnum"]), Paragraph(_esc(unit or ""), st["cellhead"])] for label, value, unit in rows]
    
    table = Table(data, colWidths=[w * USABLE for w in widths], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, BAND_BG]),
    ]))
    return table


def _grid_table(st, headers, rows, widths, left_align_first=True):
    """
    returns a bordered table whose header repeats when it splits across pages
    """
    data = [[Paragraph(_esc(h), st["cellhead"]) for h in headers]]
    for row in rows:
        data.append([Paragraph(_esc(cell), st["cell"] if (i == 0 and left_align_first) else st["cellnum"]) for i, cell in enumerate(row)])
    
    table = Table(data, colWidths=[w * USABLE for w in widths], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


###### content model
CV_TITLES = {
    "CV1_tank": "CV1 -- Oxidiser tank",
    "CV2_valve": "CV2 -- Main valve",
    "CV3_injector": "CV3 -- Injector",
    "CV4_chamber": "CV4 -- Combustion chamber",
    "CV5_nozzle": "CV5 -- Nozzle",
    "CV6_trajectory": "CV6 -- Trajectory",
}

# once again ugly anachronistic suffix system, should be removed eventually, this is a workaround
PERF_CATEGORIES = [
    ("Engine", ["burntime_s", "total_impulse_Ns", "peak_thrust_N", "average_thrust_N", "peak_chamber_pressure_Pa", "peak_chamber_temperature_K", "average_OF_ratio"]),
    ("Flight", ["pad_thrust_to_weight", "apogee_m_agl", "apogee_m_asl"]),
    ("Propellant", ["ox_mass_available_kg", "ox_mass_consumed_kg", "ox_mass_remaining_kg", "fuel_mass_available_kg", "fuel_mass_consumed_kg", "fuel_mass_remaining_kg", "total_propellant_available_kg", "total_propellant_consumed_kg"]),
]

PHASE_LABELS = {
    "phase_1": "1 -- Ignition", 
    "phase_2": "2 -- Liquid blowdown",
    "phase_3": "3 -- Gaseous blowdown", 
    "phase_4a": "4a -- Vapour purge",
    "phase_4c": "4c -- Dry blowdown", 
    "phase_5": "5 -- Coast",
    "phase_6": "6 -- Drogue descent", 
    "phase_7": "7 -- Main descent",
}


def _inputs_by_cv(rocket_inputs: dict, units: "_Units"):
    """
    group the flat rocket_inputs dict back under its control volumes
    the results file stores inputs flat and post-conversion, so the grouping has to come from the schema
    """
    models = rocket_inputs.get("CV_models", {}) or {}
    schema = _registry.unsteady_schema_keys() if _registry is not None else {}

    claimed: set[str] = set()
    groups = []
    for cv, model in models.items():
        rows = []
        for key in schema.get((cv, model), []):
            actual = key
            if actual not in rocket_inputs and "diameter" in key:
                before, after = key.split("diameter")
                actual = f"{before}radius{after}"
            if actual in rocket_inputs:
                value = rocket_inputs[actual]
                # describe by the SCHEMA key so a halved radius still reads under the diameter name the user entered
                label, category = _describe(key)
                if actual != key and isinstance(value, (int, float)) and not isinstance(value, bool):
                    value = 2.0 * value
                rows.append((label, units.value(value, category), units.unit(category)))
                claimed.add(actual)
        groups.append((CV_TITLES.get(cv, cv), model, rows))

    derived = []
    for key, value in rocket_inputs.items():
        if key in claimed or key == "CV_models" or isinstance(value, dict):
            continue
        derived.append(units.row(key, value))
    return groups, sorted(derived, key=lambda r: r[0])


###### figures
def _figure_pngs(results: dict, on_progress=None):
    """
    renders every active plot to PNG bytes in registry order
    """
    from src.common.plotting import unsteady_plots

    specs = unsteady_plots.plot_specs()
    out: list[tuple[str, io.BytesIO]] = []
    for index, spec in enumerate(specs):
        if on_progress is not None:
            try:
                on_progress(index + 1, len(specs))
            except Exception: 
                pass # progress is never worth a crash
        try:
            figure = spec.builder(results)
        except Exception: 
            continue # one bad plot costs only itself
        if figure is None:
            continue # this run has no data for it
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=FIGURE_DPI, bbox_inches="tight")
        buffer.seek(0)
        out.append((spec.label, buffer))
    return out


##### document
class _ReportDoc(BaseDocTemplate):
    def __init__(self, path: Path, run_name: str):
        super().__init__(
            str(path), pagesize=PAGE,
            leftMargin=MARGIN, rightMargin=MARGIN,
            topMargin=MARGIN, bottomMargin=0.75 * inch,
            title=f"Unsteady Sim Report: {run_name}", author="MRT Simulator",
        )
        self.run_name = run_name
        frame = Frame(MARGIN, 0.75 * inch, USABLE, PAGE[1] - MARGIN - 0.75 * inch, id="body")
        self.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=self._decorate)])

    def _decorate(self, canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 0.62 * inch, PAGE[0] - MARGIN, 0.62 * inch)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(FAINT)
        canvas.drawString(MARGIN, 0.45 * inch, f"Unsteady Sim Report: {self.run_name}"[:95])
        canvas.drawRightString(PAGE[0] - MARGIN, 0.45 * inch, str(doc.page))
        canvas.restoreState()


def generate_report(run_dir, 
                    results: Optional[dict] = None, 
                    on_progress=None,
                    system: Optional[str] = None, 
                    on_stage=None):
    """
    writes run report
        run_dir: folder holding sim_data.json
        results: already-parsed sim_data, when the caller has it in hand
        on_progress: optional (done, total) callback, fired per figure
        on_stage: optional (message) callback for the stretches that have no per-figure tick to hang off. done to save time
        system: "SI", "IMP" or "MRT", the unit system you want to use
    returns the path written to
    """
    def stage(message: str) -> None:
        if on_stage is None:
            return
        try:
            on_stage(message)
        except Exception: 
            pass # progress is never worth a crash

    run_dir = Path(run_dir)
    if results is None:
        results = json.loads((run_dir / "sim_data.json").read_text(encoding="utf-8"))

    native = _native_system_of(results)
    units = _Units(system or native, native)

    stage("Generating PDF report...")
    run_name = run_dir.name
    st = _styles()
    flow: list = []
    add = flow.append

    meta = results.get("metadata") or {}
    performance = results.get("performance") or {}
    overall = performance.get("overall") or {}
    by_phase = performance.get("by_phase") or {}
    events = results.get("event_log") or []
    warnings = results.get("warnings")
    rocket_inputs = (results.get("static") or {}).get("rocket_inputs") or {}

    ### title page section
    add(Paragraph(f"Unsteady Sim Report: {_esc(run_name)}", st["title"]))
    level = warnings.get("overall_warning_level") if isinstance(warnings, dict) else None
    add(Paragraph(
        ("Completed nominally" if meta.get("completed_nominally") else "Did not complete nominally")
        + f"&nbsp;·&nbsp; terminal state <b>{_esc(meta.get('terminal_state', '?'))}</b>"
        + f"&nbsp;·&nbsp; {_fmt(meta.get('total_simulation_time'))} s simulated over {_fmt(meta.get('total_timesteps'))} steps"
        + (f"&nbsp;·&nbsp; warning level <b>{_esc(level)}</b>" if level else "")
        + f"&nbsp;·&nbsp; {_esc(units.system)} units", st["subtitle"]))
    if meta.get("terminal_reason"):
        add(Paragraph(_esc(meta["terminal_reason"]), st["note"]))
        add(Spacer(1, 8))

    # PART 1: inputs, outputs, phases, warnings, etc... all except graphs
    add(Paragraph("Run information", st["part"]))

    add(Paragraph("1.1 &nbsp; Inputs, by control volume", st["h2"]))
    add(Paragraph(f"As the user entered them - diameters as diameters - shown in {_esc(units.system)} units.", st["note"]))
    groups, derived = _inputs_by_cv(rocket_inputs, units)
    for title, model, rows in groups:
        if rows:
            add(KeepTogether([
                Paragraph(f"{_esc(title)} &nbsp;&nbsp;<font color='#8a95a1'>model: {_esc(model)}</font>", st["h3"]), _kv_table(st, rows)]))
    if derived:
        add(Paragraph("Derived at load time", st["h3"]))
        add(Paragraph("Computed from the inputs above by compute_rocket_variables, not entered by the user.", st["note"]))
        add(_kv_table(st, derived))

    add(PageBreak())
    add(Paragraph("1.2 &nbsp; Performance", st["h2"]))
    seen: set[str] = set()
    for heading, keys in PERF_CATEGORIES:
        rows = []
        for key in keys:
            if key in overall:
                rows.append(units.row(key, overall[key]))
                seen.add(key)
        if rows:
            add(KeepTogether([Paragraph(_esc(heading), st["h3"]), _kv_table(st, rows)]))
    rest = [units.row(k, v) for k, v in overall.items() if k not in seen]
    if rest:
        add(KeepTogether([Paragraph("Other", st["h3"]), _kv_table(st, sorted(rest, key=lambda r: r[0]))]))

    if by_phase:
        add(Paragraph("1.3 &nbsp; By flight phase", st["h2"]))
        # (key, heading, category) -- the heading's unit is filled in from the display system rather than baked into the string
        columns = [("duration_s", "Duration", "time"),
                   ("total_impulse_Ns", "Impulse", "impulse"),
                   ("peak_thrust_N", "Peak thrust", "force"),
                   ("average_thrust_N", "Mean thrust", "force"),
                   ("peak_chamber_pressure_Pa", "Peak p_C", "pressure"),
                   ("average_OF_ratio", "Mean O/F", None)]

        def _head(text, category):
            unit = units.unit(category)
            return f"{text} ({unit})" if unit else text

        rows = []
        for phase in sorted(by_phase):
            data = by_phase[phase] or {}
            rows.append([PHASE_LABELS.get(phase, phase), _fmt(units.value(data.get("t_start_s"), "time"))] + [_fmt(units.value(data.get(key), category)) for key, _, category in columns])
        add(_grid_table(st, ["Phase", _head("Start", "time")] + [_head(lab, cat) for _, lab, cat in columns], rows, [0.20, 0.10, 0.11, 0.13, 0.12, 0.12, 0.12, 0.10]))
        add(Paragraph("Coast and descent phases produce no thrust, so their engine columns are empty by construction.", st["note"]))

    add(Paragraph("1.4 &nbsp; Event log", st["h2"]))
    if events:
        rows = [[_fmt(e.get("t_s")), e.get("event_type", ""), e.get("message", "")] for e in events if isinstance(e, dict)]
        add(_grid_table(st, ["t (s)", "Event", "Detail"], rows, [0.10, 0.24, 0.66], left_align_first=False))
    else:
        add(Paragraph("No events logged.", st["note"]))

    add(Paragraph("1.5 &nbsp; Warnings", st["h2"]))
    if warnings == "disabled":
        add(Paragraph("Warnings were switched off for this run.", st["note"]))
    elif isinstance(warnings, dict) and warnings.get("triggered_warnings"):
        triggered = warnings["triggered_warnings"]
        add(Paragraph(f"Overall level: <b>{_esc(warnings.get('overall_warning_level', '?'))}</b>", st["body"]))
        for severity in ("critical", "caution", "advisory", "debug"):
            group = {k: v for k, v in triggered.items()
                     if isinstance(v, dict) and v.get("severity") == severity}
            if not group:
                continue
            add(Paragraph(f"<font color='{SEVERITY_COLOUR[severity]}'>{severity.capitalize()} ({len(group)})</font>", st["h3"]))
            for key, entry in group.items():
                add(Paragraph(_esc(entry.get("message", key)), st["cell"]))
                add(Paragraph(f"<font face='Courier' size='7.5'>{_esc(key)}</font>", st["note"]))
    else:
        add(Paragraph("No warnings. The run looked clean.", st["note"]))

    # PART 2: graphs
    stage("Generating PDF report... loading the plot library")
    figures = _figure_pngs(results, on_progress=on_progress)
    add(PageBreak())
    add(Paragraph("Graphs", st["part"]))
    if not figures:
        add(Paragraph("No plots could be built from this run.", st["note"]))
    else:
        add(Paragraph(f"{len(figures)} plots, one per page, in registry order.", st["note"]))
        for index, (label, buffer) in enumerate(figures):
            add(PageBreak())
            add(Paragraph(f"{index + 1}. {_esc(label)}", st["h2"]))
            image = Image(buffer)
            scale = min(USABLE / image.imageWidth, (PAGE[1] - 2.4 * inch) / image.imageHeight)
            image.drawWidth = image.imageWidth * scale
            image.drawHeight = image.imageHeight * scale
            add(image)

    stage("Generating PDF report...  writing the document")
    out_path = run_dir / REPORT_FILENAME
    _ReportDoc(out_path, run_name).build(flow)
    return out_path
