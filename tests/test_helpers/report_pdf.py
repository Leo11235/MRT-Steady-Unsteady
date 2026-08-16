from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)

from tests.test_helpers import report_builder as rb

# Letter portrait with half-inch margins gives ~7.5 in of usable width, which
# is what every column width below is a fraction of.
_PAGE = letter
_MARGIN = 0.5 * inch
_USABLE = _PAGE[0] - 2 * _MARGIN

_FAIL = colors.HexColor("#b00020")
_PASS = colors.HexColor("#137333")
_MUTED = colors.HexColor("#666666")
_LINE = colors.HexColor("#cccccc")
_HEADER_BG = colors.HexColor("#f0f0f0")
_CODE_BG = colors.HexColor("#f7f7f7")

# Monospace blocks are pre-wrapped rather than left to reportlab, which does
# not break long unbroken tokens and silently runs them off the page.
_CODE_COLS = 108
# Lines per code-block row. At 8.5pt leading a row is about 170 points, so it
# always fits a 700 point frame, and a page break wastes at most one row.
_CODE_ROW_LINES = 20
# Cap on a single table cell, for the same reason: a row can't be split.
_MAX_CELL_CHARS = 3000


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=18,
                                spaceAfter=2, alignment=TA_LEFT),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=15,
                             spaceBefore=12, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=11.5,
                             spaceBefore=10, spaceAfter=3),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontSize=9,
                               leading=12, spaceAfter=4),
        "muted": ParagraphStyle("muted", parent=base["BodyText"], fontSize=8.5,
                                leading=11, textColor=_MUTED, spaceAfter=4),
        # wordWrap CJK breaks mid-token, which is what long dotted paths and
        # file paths need or they overflow their column.
        "cell": ParagraphStyle("cell", parent=base["BodyText"], fontSize=7.5,
                               leading=9.5, wordWrap="CJK", spaceAfter=0),
        "cellhead": ParagraphStyle("cellhead", parent=base["BodyText"],
                                   fontSize=7.5, leading=9.5, wordWrap="CJK",
                                   fontName="Helvetica-Bold", spaceAfter=0),
        "code": ParagraphStyle("code", parent=base["BodyText"],
                               fontName="Courier", fontSize=7, leading=8.5,
                               spaceAfter=0),
    }


def _escape(value: Any) -> str:
    """Paragraph parses a small XML dialect, so these three must be escaped."""
    return (str(value).replace("&", "&amp;")
                      .replace("<", "&lt;")
                      .replace(">", "&gt;"))


def _cell_text(value: Any) -> str:
    """Escaped cell text, capped so one cell can never outgrow a page.

    A table row is atomic to reportlab. If a single assertion message wrapped
    to taller than the frame, the whole build would fail the way an oversized
    code block does, and no amount of splitting would save it. Truncating is
    the only option; the full text is in report.md and report.json anyway.
    """
    text = str(value)
    if len(text) > _MAX_CELL_CHARS:
        text = (text[:_MAX_CELL_CHARS]
                + f"  [+{len(text) - _MAX_CELL_CHARS} more chars, see report.md]")
    return _escape(text)


def _table(headers, rows, widths, styles, *, header_colours=None) -> Table:
    """A bordered table whose header repeats across page breaks.

    Every cell is a Paragraph rather than a bare string so long values wrap
    instead of overflowing.
    """
    data = [[Paragraph(_escape(h), styles["cellhead"]) for h in headers]]
    for row in rows:
        data.append([Paragraph(_cell_text(c), styles["cell"]) for c in row])

    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, _LINE),
        ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for row_index, colour in (header_colours or {}).items():
        style.append(("TEXTCOLOR", (0, row_index), (0, row_index), colour))
    table.setStyle(TableStyle(style))
    return table


def _code_block(text: str, styles) -> Table:
    """A monospace block on a tinted background.

    Wrapped in a Table because a plain Paragraph can't carry a background, and
    Preformatted doesn't wrap long lines.

    The lines are split across MANY ROWS rather than sitting in one big cell.
    reportlab can only break a table between rows: a single cell is atomic, so
    if it doesn't fit the remaining frame it doesn't fit anywhere, and the
    build dies with LayoutError instead of flowing onto the next page. A 200
    line traceback is roughly 1700 points against a 700 point frame, so one
    cell was never going to survive. Chunking caps each row's height at about
    a quarter page and lets the block flow across as many pages as it needs.
    """
    wrapped = []
    for line in (text or "").splitlines():
        wrapped.extend(textwrap.wrap(line, _CODE_COLS,
                                     subsequent_indent="    ",
                                     replace_whitespace=False,
                                     drop_whitespace=False) or [""])
    if not wrapped:
        wrapped = [""]

    rows = [wrapped[i:i + _CODE_ROW_LINES]
            for i in range(0, len(wrapped), _CODE_ROW_LINES)]
    data = [[Paragraph("<br/>".join(_escape(l) for l in chunk), styles["code"])]
            for chunk in rows]

    table = Table(data, colWidths=[_USABLE], hAlign="LEFT", splitByRow=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, -1), _CODE_BG),
        ("BOX", (0, 0), (-1, -1), 0.4, _LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        # Breathing room at the two ends only. Padding on every row would open
        # visible gaps at the chunk seams and give away where they are.
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, len(data) - 1), (-1, len(data) - 1), 4),
    ]
    table.setStyle(TableStyle(style))
    return table


# =============================================================================
# Front matter
# =============================================================================

def _front_matter(report: rb.Report, styles) -> list:
    flow: list = []
    add = flow.append

    add(Paragraph("Backend test report", styles["title"]))
    add(Paragraph(
        f'{report.generated_at} &middot; '
        f'<font color="#137333"><b>{len(report.passes)} passed</b></font>, '
        f'<font color="#b00020"><b>{len(report.failures)} failed</b></font>, '
        f'{len(report.contexts)} total',
        styles["body"]))

    add(Paragraph("Environment", styles["h1"]))
    add(_table(["", ""],
               [[k, v] for k, v in report.environment.items()],
               [0.22 * _USABLE, 0.78 * _USABLE], styles))

    clusters = rb.cluster_failures(report)
    if clusters:
        add(Paragraph(
            f"Failure clusters ({len(clusters)} distinct symptoms, "
            f"{len(report.failures)} failures)", styles["h1"]))
        add(Paragraph(
            "A dozen failures usually come from three causes. Start here.",
            styles["muted"]))
        add(_table(
            ["n", "symptom", "exception", "tests"],
            [[str(c["count"]), c["symptom"], c["exception"] or "-",
              ", ".join(c["tests"])] for c in clusters],
            [0.05 * _USABLE, 0.30 * _USABLE, 0.17 * _USABLE, 0.48 * _USABLE],
            styles))

    add(Paragraph("All tests", styles["h1"]))
    for kind, contexts in report.by_kind().items():
        add(Paragraph(f"{kind.capitalize()} ({len(contexts)} configs)",
                      styles["h2"]))
        rows, colours = [], {}
        for index, ctx in enumerate(contexts, start=1):
            ok = rb.passed(ctx)
            note = "" if ok else ctx.failure_reason()
            rows.append(["PASS" if ok else "FAIL", ctx.name, ctx.outcome,
                         f"{ctx.elapsed_s:.1f}s", note])
            colours[index] = _PASS if ok else _FAIL
        add(_table(["", "test", "outcome", "time", "detail"], rows,
                   [0.06 * _USABLE, 0.28 * _USABLE, 0.13 * _USABLE,
                    0.07 * _USABLE, 0.46 * _USABLE],
                   styles, header_colours=colours))

    outliers = rb.timing_outliers(report)
    if outliers:
        add(Paragraph("Timing outliers", styles["h1"]))
        add(Paragraph(
            "Far slower than the median for their kind. Worth a look even "
            "when they pass: a validation test that takes ten seconds to not "
            "reject something never ran its validator.", styles["muted"]))
        add(_table(["test", "elapsed", "median for kind"],
                   [[r["test"], r["elapsed"], r["median"]] for r in outliers],
                   [0.5 * _USABLE, 0.25 * _USABLE, 0.25 * _USABLE], styles))

    return flow


# =============================================================================
# One page per failure
# =============================================================================

def _failure(ctx, styles) -> list:
    flow: list = [PageBreak()]
    add = flow.append

    add(Paragraph(_escape(ctx.name), styles["title"]))
    add(Paragraph(
        f'{_escape(ctx.kind)} &middot; expected <b>{_escape(ctx.expected)}</b>, '
        f'got <font color="#b00020"><b>{_escape(ctx.outcome)}</b></font> '
        f'&middot; {ctx.elapsed_s:.1f}s<br/>{_escape(ctx.config_path)}',
        styles["muted"]))

    description = (ctx.metadata or {}).get("simulation_description")
    if description:
        add(Paragraph(f"<i>{_escape(description)}</i>", styles["muted"]))

    failed = [(n, m) for n, ok, m in ctx.check_results if not ok]
    if failed:
        add(Paragraph("Failed checks", styles["h1"]))
        add(_table(["check", "message"], [[n, m] for n, m in failed],
                   [0.2 * _USABLE, 0.8 * _USABLE], styles))

    detail = rb.check_detail(ctx)
    if detail:
        add(Paragraph("Check values", styles["h1"]))
        add(_table(
            ["check", "path", "expected", "actual", "delta", "off by"],
            [[r["check"], r["path"], r["expected"], r["actual"],
              r["delta"], r["percent"]] for r in detail],
            [0.14 * _USABLE, 0.28 * _USABLE, 0.16 * _USABLE,
             0.16 * _USABLE, 0.13 * _USABLE, 0.13 * _USABLE], styles))

    if ctx.exception is not None:
        add(Paragraph("Exception", styles["h1"]))
        add(Paragraph(
            f'<font face="Courier">{_escape(type(ctx.exception).__name__)}: '
            f'{_escape(ctx.exception)}</font>', styles["body"]))
        if ctx.traceback_text:
            add(_code_block(rb.tail(ctx.traceback_text,
                                    rb.MAX_TRACEBACK_LINES), styles))

    diff = rb.config_diff(ctx)
    if diff:
        add(Paragraph("Config diff from baseline", styles["h1"]))
        add(_table(["key", "baseline", "this test"],
                   [[r["key"], r["baseline"], r["this"]] for r in diff],
                   [0.4 * _USABLE, 0.3 * _USABLE, 0.3 * _USABLE], styles))

    physics = rb.physics_view(ctx)
    if physics:
        add(Paragraph("As the physics received it", styles["h1"]))
        add(Paragraph(
            "Converted to SI, diameters halved to radii. Conversion bugs show "
            "up here first: a launch angle reading [6, 'deg'] -> 0.10472 is "
            "right, and -> 0.001827 is a double conversion.", styles["muted"]))
        add(_table(["key", "as written", "as converted"],
                   [[r["key"], r["written"], r["si"]] for r in physics],
                   [0.4 * _USABLE, 0.35 * _USABLE, 0.25 * _USABLE], styles))

    headline = rb.headline_outputs(ctx)
    if headline:
        add(Paragraph("Key outputs", styles["h1"]))
        add(_table(["key", "value"],
                   [[r["key"], r["value"]] for r in headline],
                   [0.5 * _USABLE, 0.5 * _USABLE], styles))

    trace = rb.convergence_trace(ctx)
    if trace:
        add(Paragraph("Convergence trace", styles["h1"]))
        add(_table(["loop", "apogee", "change"],
                   [[str(r["loop"]), f"{r['apogee']:.6g}", r["change"]]
                    for r in trace],
                   [0.2 * _USABLE, 0.4 * _USABLE, 0.4 * _USABLE], styles))

    phases = rb.phase_timeline(ctx)
    if phases:
        add(Paragraph("Phases reached", styles["h1"]))
        add(Paragraph(f'<font face="Courier">{" -&gt; ".join(phases)}</font>',
                      styles["body"]))

    warnings = rb.warnings_summary(ctx)
    if warnings:
        add(Paragraph("Warnings", styles["h1"]))
        add(_table(["severity", "id", "message"],
                   [[r["severity"], r["id"], r["message"]] for r in warnings],
                   [0.12 * _USABLE, 0.28 * _USABLE, 0.60 * _USABLE], styles))

    nonfinite = rb.non_finite_scan(ctx)
    if nonfinite:
        add(Paragraph("Non-finite values", styles["h1"]))
        add(_table(["series", "first index", "value", "length"],
                   [[r["series"], str(r["index"]), r["value"], str(r["length"])]
                    for r in nonfinite],
                   [0.5 * _USABLE, 0.2 * _USABLE, 0.15 * _USABLE,
                    0.15 * _USABLE], styles))

    if ctx.stdout:
        add(Paragraph("Terminal output", styles["h1"]))
        add(_code_block(rb.tail(ctx.stdout, rb.MAX_STDOUT_LINES), styles))

    rows = rb.config_rows(ctx)
    if rows:
        add(Paragraph("Full config", styles["h1"]))
        add(_table(["key", "value", "unit"],
                   [[r["key"], r["value"], r["unit"]] for r in rows],
                   [0.55 * _USABLE, 0.30 * _USABLE, 0.15 * _USABLE], styles))

    return flow


# =============================================================================
# Page furniture
# =============================================================================

class _SectionDocTemplate(SimpleDocTemplate):
    """Records which page each section title landed on.

    A failure runs over two or three pages, and the continuation pages open
    with a repeated table header and nothing else, so page 7 of 10 gives no
    clue which test it belongs to. The footer fixes that, but it needs to know
    the section, and reportlab's page callbacks fire at page START, before any
    flowable on that page has been placed. Tracking the section live therefore
    lags a page: every failure's first page would name the previous one.

    So the document is built twice. The first pass only collects the map; the
    second uses it. Builds are milliseconds, and the alternative is guessing.
    """

    def __init__(self, *args, section_pages=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.section_pages: dict[int, str] = {}
        self.known_sections = section_pages or {}

    def afterFlowable(self, flowable) -> None:
        if isinstance(flowable, Paragraph) and flowable.style.name == "title":
            self.section_pages[self.page] = flowable.getPlainText()

    def section_for(self, page: int) -> str:
        """The most recent title at or before `page`."""
        started = [p for p in self.known_sections if p <= page]
        return self.known_sections[max(started)] if started else ""


def _decorate(canvas, doc) -> None:
    """Footer: current section on the left, page number on the right."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(_MUTED)
    label = doc.section_for(doc.page) or "MRT backend test report"
    canvas.drawString(_MARGIN, 0.32 * inch, label[:90])
    canvas.drawRightString(_PAGE[0] - _MARGIN, 0.32 * inch,
                           f"page {doc.page}")
    canvas.restoreState()


def _build_flow(report: rb.Report, styles) -> list:
    flow = _front_matter(report, styles)
    for ctx in report.failures:
        flow.extend(_failure(ctx, styles))
    return flow


def render_pdf(report: rb.Report, path: Path) -> Path:
    """Write the report to `path`. Returns the path."""
    import io

    styles = _styles()

    def make(target, section_pages) -> _SectionDocTemplate:
        return _SectionDocTemplate(
            target, pagesize=_PAGE,
            leftMargin=_MARGIN, rightMargin=_MARGIN,
            topMargin=_MARGIN, bottomMargin=0.6 * inch,
            title="MRT backend test report", author="backend_tests",
            section_pages=section_pages,
        )

    # Pass one, thrown away, purely to learn which page each section starts on.
    scratch = make(io.BytesIO(), None)
    scratch.build(_build_flow(report, styles))

    # Pass two, the real one, with a footer that can name its section.
    document = make(str(path), scratch.section_pages)
    document.build(_build_flow(report, styles),
                   onFirstPage=_decorate, onLaterPages=_decorate)
    return path
