from __future__ import annotations

import html
import json
from pathlib import Path

from tests.test_helpers import report_builder as rb


# =============================================================================
# Markdown  (the assistant copy, and a decent fallback for humans)
# =============================================================================

def render_markdown(report: rb.Report, *, failures_only: bool = True) -> str:
    out: list[str] = []
    add = out.append

    add(f"# Backend test report\n")
    add(f"Generated {report.generated_at}. "
        f"{len(report.passes)} passed, {len(report.failures)} failed, "
        f"{len(report.contexts)} total.\n")

    # ---- environment --------------------------------------------------
    add("## Environment\n")
    add("| | |")
    add("|---|---|")
    for key, value in report.environment.items():
        add(f"| {key} | {value} |")
    add("")

    # ---- clusters first: this is the part that saves time --------------
    clusters = rb.cluster_failures(report)
    if clusters:
        add(f"## Failure clusters ({len(clusters)} distinct symptoms, "
            f"{len(report.failures)} failures)\n")
        add("| count | symptom | exception | tests |")
        add("|---|---|---|---|")
        for cluster in clusters:
            add(f"| {cluster['count']} | {cluster['symptom']} | "
                f"{cluster['exception'] or '-'} | "
                f"{', '.join(cluster['tests'])} |")
        add("")

    # ---- full list ----------------------------------------------------
    add("## All tests\n")
    for kind, contexts in report.by_kind().items():
        add(f"### {kind.capitalize()} ({len(contexts)} configs)\n")
        add("| result | test | outcome | expected | time |")
        add("|---|---|---|---|---|")
        for ctx in contexts:
            verdict = "PASS" if rb.passed(ctx) else "**FAIL**"
            add(f"| {verdict} | {ctx.name} | {ctx.outcome} | "
                f"{ctx.expected} | {ctx.elapsed_s:.1f}s |")
        add("")

    outliers = rb.timing_outliers(report)
    if outliers:
        add("## Timing outliers\n")
        add("| test | elapsed | median for kind |")
        add("|---|---|---|")
        for row in outliers:
            add(f"| {row['test']} | {row['elapsed']} | {row['median']} |")
        add("")

    # ---- one section per failure --------------------------------------
    targets = report.failures if failures_only else report.contexts
    if targets:
        add("---\n")
        add(f"# Failures ({len(targets)})\n")
    for ctx in targets:
        out.extend(_markdown_failure(ctx))

    return "\n".join(out) + "\n"


def _markdown_failure(ctx) -> list[str]:
    out: list[str] = []
    add = out.append

    add(f"\n## {ctx.name}  ({ctx.kind})\n")
    add(f"- Config: `{ctx.config_path}`")
    add(f"- Expected `{ctx.expected}`, got `{ctx.outcome}`, "
        f"in {ctx.elapsed_s:.1f}s")
    description = (ctx.metadata or {}).get("simulation_description")
    if description:
        add(f"- Intent: {description}")
    add("")

    failed = [(n, m) for n, ok, m in ctx.check_results if not ok]
    if failed:
        add("### Failed checks\n")
        for name, message in failed:
            add(f"- **{name}**: {message}")
        add("")

    detail = rb.check_detail(ctx)
    if detail:
        add("### Check values\n")
        add("| check | path | expected | actual | delta | off by |")
        add("|---|---|---|---|---|---|")
        for row in detail:
            add(f"| {row['check']} | `{row['path']}` | {row['expected']} | "
                f"{row['actual']} | {row['delta']} | {row['percent']} |")
        add("")

    if ctx.exception is not None:
        add("### Exception\n")
        add(f"`{type(ctx.exception).__name__}: {ctx.exception}`\n")
        if ctx.traceback_text:
            add("```")
            add(rb.tail(ctx.traceback_text, rb.MAX_TRACEBACK_LINES))
            add("```\n")

    diff = rb.config_diff(ctx)
    if diff:
        add("### Config diff from baseline\n")
        add("| key | baseline | this test |")
        add("|---|---|---|")
        for row in diff:
            add(f"| `{row['key']}` | {row['baseline']} | {row['this']} |")
        add("")

    physics = rb.physics_view(ctx)
    if physics:
        add("### As the physics received it (SI, radii not diameters)\n")
        add("| key | as written | as converted |")
        add("|---|---|---|")
        for row in physics:
            add(f"| `{row['key']}` | {row['written']} | {row['si']} |")
        add("")

    headline = rb.headline_outputs(ctx)
    if headline:
        add("### Key outputs\n")
        add("| key | value |")
        add("|---|---|")
        for row in headline:
            add(f"| {row['key']} | {row['value']} |")
        add("")

    trace = rb.convergence_trace(ctx)
    if trace:
        add("### Convergence trace\n")
        add("| loop | apogee | change |")
        add("|---|---|---|")
        for row in trace:
            add(f"| {row['loop']} | {row['apogee']:.6g} | {row['change']} |")
        add("")

    phases = rb.phase_timeline(ctx)
    if phases:
        add(f"### Phases reached\n\n{' -> '.join(phases)}\n")

    warnings = rb.warnings_summary(ctx)
    if warnings:
        add("### Warnings\n")
        add("| severity | id | message |")
        add("|---|---|---|")
        for row in warnings:
            add(f"| {row['severity']} | `{row['id']}` | {row['message']} |")
        add("")

    nonfinite = rb.non_finite_scan(ctx)
    if nonfinite:
        add("### Non-finite values\n")
        add("| series | first index | value | length |")
        add("|---|---|---|---|")
        for row in nonfinite:
            add(f"| `{row['series']}` | {row['index']} | {row['value']} | "
                f"{row['length']} |")
        add("")

    if ctx.stdout:
        add("### Terminal output\n")
        add("```")
        add(rb.tail(ctx.stdout, rb.MAX_STDOUT_LINES))
        add("```\n")

    rows = rb.config_rows(ctx)
    if rows:
        add("### Full config\n")
        add("| key | value | unit |")
        add("|---|---|---|")
        for row in rows:
            add(f"| `{row['key']}` | {row['value']} | {row['unit']} |")
        add("")

    return out


# =============================================================================
# HTML  (print to PDF)
# =============================================================================

_CSS = """
:root { --fg:#1a1a1a; --muted:#666; --line:#ddd; --pass:#137333; --fail:#b00020; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
       color: var(--fg); margin: 0 auto; padding: 32px; max-width: 1000px;
       line-height: 1.45; }
h1 { font-size: 24px; margin: 0 0 4px; }
h2 { font-size: 19px; margin: 28px 0 8px; border-bottom: 2px solid var(--line);
     padding-bottom: 4px; }
h3 { font-size: 15px; margin: 18px 0 6px; color: #333; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 14px;
        font-size: 12px; }
th, td { border: 1px solid var(--line); padding: 4px 7px; text-align: left;
         vertical-align: top; }
th { background: #f4f4f4; font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
code, pre { font-family: Consolas, "SF Mono", monospace; font-size: 11.5px; }
pre { background: #f7f7f7; border: 1px solid var(--line); padding: 9px;
      white-space: pre-wrap; word-break: break-word; }
.pass { color: var(--pass); font-weight: 600; }
.fail { color: var(--fail); font-weight: 700; }
.muted { color: var(--muted); font-size: 12px; }
.summary { font-size: 15px; margin-bottom: 18px; }

/* One failure per page, which is the whole reason this is printable. */
.failure { page-break-before: always; break-before: page; }
@media print {
  body { padding: 0; max-width: none; }
  h2 { page-break-after: avoid; }
  table { page-break-inside: auto; }
  tr { page-break-inside: avoid; }
}
"""


def render_html(report: rb.Report) -> str:
    out: list[str] = []
    add = out.append

    add("<!DOCTYPE html><html><head><meta charset='utf-8'>")
    add("<title>Backend test report</title>")
    add(f"<style>{_CSS}</style></head><body>")

    add("<h1>Backend test report</h1>")
    add(f"<p class='summary'>{report.generated_at} &middot; "
        f"<span class='pass'>{len(report.passes)} passed</span>, "
        f"<span class='fail'>{len(report.failures)} failed</span>, "
        f"{len(report.contexts)} total.</p>")
    add("<p class='muted'>Print this page (Ctrl+P) and save as PDF. "
        "Each failure starts on its own page.</p>")

    add("<h2>Environment</h2>")
    add(_html_table(["", ""],
                    [[k, str(v)] for k, v in report.environment.items()]))

    clusters = rb.cluster_failures(report)
    if clusters:
        add(f"<h2>Failure clusters ({len(clusters)} distinct symptoms)</h2>")
        add(_html_table(
            ["count", "symptom", "exception", "tests"],
            [[str(c["count"]), c["symptom"], c["exception"] or "-",
              ", ".join(c["tests"])] for c in clusters]))

    add("<h2>All tests</h2>")
    for kind, contexts in report.by_kind().items():
        add(f"<h3>{kind.capitalize()} ({len(contexts)} configs)</h3>")
        rows = []
        for ctx in contexts:
            ok = rb.passed(ctx)
            verdict = (f"<span class='{'pass' if ok else 'fail'}'>"
                       f"{'PASS' if ok else 'FAIL'}</span>")
            note = "" if ok else "; ".join(
                m for _n, passed_, m in ctx.check_results if not passed_)
            if not ok and ctx.outcome != ctx.expected:
                note = f"expected {ctx.expected}, got {ctx.outcome}. {note}"
            rows.append([verdict, ctx.name, ctx.outcome,
                         f"{ctx.elapsed_s:.1f}s", note])
        add(_html_table(["", "test", "outcome", "time", "detail"], rows,
                        raw_columns={0}))

    outliers = rb.timing_outliers(report)
    if outliers:
        add("<h2>Timing outliers</h2>")
        add(_html_table(["test", "elapsed", "median for kind"],
                        [[r["test"], r["elapsed"], r["median"]]
                         for r in outliers]))

    for ctx in report.failures:
        out.extend(_html_failure(ctx))

    add("</body></html>")
    return "\n".join(out)


def _html_failure(ctx) -> list[str]:
    out: list[str] = []
    add = out.append

    add("<div class='failure'>")
    add(f"<h1>{html.escape(ctx.name)}</h1>")
    add(f"<p class='muted'>{html.escape(ctx.kind)} &middot; "
        f"expected <b>{html.escape(ctx.expected)}</b>, got "
        f"<b class='fail'>{html.escape(ctx.outcome)}</b> &middot; "
        f"{ctx.elapsed_s:.1f}s<br>{html.escape(str(ctx.config_path))}</p>")

    description = (ctx.metadata or {}).get("simulation_description")
    if description:
        add(f"<p><i>{html.escape(str(description))}</i></p>")

    failed = [(n, m) for n, ok, m in ctx.check_results if not ok]
    if failed:
        add("<h2>Failed checks</h2>")
        add(_html_table(["check", "message"],
                        [[n, m] for n, m in failed]))

    detail = rb.check_detail(ctx)
    if detail:
        add("<h2>Check values</h2>")
        add(_html_table(
            ["check", "path", "expected", "actual", "delta", "off by"],
            [[r["check"], r["path"], r["expected"], r["actual"],
              r["delta"], r["percent"]] for r in detail]))

    if ctx.exception is not None:
        add("<h2>Exception</h2>")
        add(f"<p><code>{html.escape(type(ctx.exception).__name__)}: "
            f"{html.escape(str(ctx.exception))}</code></p>")
        if ctx.traceback_text:
            add(f"<pre>{html.escape(rb.tail(ctx.traceback_text, rb.MAX_TRACEBACK_LINES))}</pre>")

    diff = rb.config_diff(ctx)
    if diff:
        add("<h2>Config diff from baseline</h2>")
        add(_html_table(["key", "baseline", "this test"],
                        [[r["key"], r["baseline"], r["this"]] for r in diff]))

    physics = rb.physics_view(ctx)
    if physics:
        add("<h2>As the physics received it</h2>")
        add("<p class='muted'>Converted to SI, diameters halved to radii. "
            "Conversion bugs show up here first.</p>")
        add(_html_table(["key", "as written", "as converted"],
                        [[r["key"], r["written"], r["si"]] for r in physics]))

    headline = rb.headline_outputs(ctx)
    if headline:
        add("<h2>Key outputs</h2>")
        add(_html_table(["key", "value"],
                        [[r["key"], r["value"]] for r in headline]))

    trace = rb.convergence_trace(ctx)
    if trace:
        add("<h2>Convergence trace</h2>")
        add(_html_table(["loop", "apogee", "change"],
                        [[str(r["loop"]), f"{r['apogee']:.6g}", r["change"]]
                         for r in trace]))

    phases = rb.phase_timeline(ctx)
    if phases:
        add(f"<h2>Phases reached</h2><p><code>{' &rarr; '.join(phases)}</code></p>")

    warnings = rb.warnings_summary(ctx)
    if warnings:
        add("<h2>Warnings</h2>")
        add(_html_table(["severity", "id", "message"],
                        [[r["severity"], r["id"], r["message"]]
                         for r in warnings]))

    nonfinite = rb.non_finite_scan(ctx)
    if nonfinite:
        add("<h2>Non-finite values</h2>")
        add(_html_table(["series", "first index", "value", "length"],
                        [[r["series"], str(r["index"]), r["value"],
                          str(r["length"])] for r in nonfinite]))

    if ctx.stdout:
        add("<h2>Terminal output</h2>")
        add(f"<pre>{html.escape(rb.tail(ctx.stdout, rb.MAX_STDOUT_LINES))}</pre>")

    rows = rb.config_rows(ctx)
    if rows:
        add("<h2>Full config</h2>")
        add(_html_table(["key", "value", "unit"],
                        [[r["key"], r["value"], r["unit"]] for r in rows]))

    add("</div>")
    return out


def _html_table(headers, rows, raw_columns=frozenset()) -> str:
    """A table. `raw_columns` holds indices whose cells are already HTML."""
    parts = ["<table><tr>"]
    parts += [f"<th>{html.escape(str(h))}</th>" for h in headers]
    parts.append("</tr>")
    for row in rows:
        parts.append("<tr>")
        for index, cell in enumerate(row):
            text = str(cell) if index in raw_columns else html.escape(str(cell))
            parts.append(f"<td>{text}</td>")
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)


# =============================================================================
# JSON  (machines)
# =============================================================================

def render_json(report: rb.Report) -> str:
    """Everything, unformatted. For diffing runs or wiring to CI later."""
    payload = {
        "generated_at": report.generated_at,
        "environment": report.environment,
        "summary": {
            "total": len(report.contexts),
            "passed": len(report.passes),
            "failed": len(report.failures),
        },
        "clusters": rb.cluster_failures(report),
        "timing_outliers": rb.timing_outliers(report),
        "tests": [_json_test(ctx) for ctx in report.contexts],
    }
    return json.dumps(payload, indent=2, default=str)


def _json_test(ctx) -> dict:
    entry = {
        "name": ctx.name,
        "kind": ctx.kind,
        "config_path": str(ctx.config_path),
        "passed": rb.passed(ctx),
        "expected": ctx.expected,
        "outcome": ctx.outcome,
        "elapsed_s": round(ctx.elapsed_s, 3),
        "checks": [{"name": n, "passed": ok, "message": m}
                   for n, ok, m in ctx.check_results],
    }
    if rb.passed(ctx):
        return entry

    entry.update({
        "check_detail": rb.check_detail(ctx),
        "config_diff": rb.config_diff(ctx),
        "physics_view": rb.physics_view(ctx),
        "headline_outputs": rb.headline_outputs(ctx),
        "convergence_trace": rb.convergence_trace(ctx),
        "phases": rb.phase_timeline(ctx),
        "warnings": rb.warnings_summary(ctx),
        "non_finite": rb.non_finite_scan(ctx),
        "stdout_tail": rb.tail(ctx.stdout, rb.MAX_STDOUT_LINES),
        "traceback": rb.tail(ctx.traceback_text, rb.MAX_TRACEBACK_LINES),
        "exception": (f"{type(ctx.exception).__name__}: {ctx.exception}"
                      if ctx.exception else None),
    })
    return entry


# =============================================================================
# Writing
# =============================================================================

def write_reports(contexts, out_dir: Path, *, stamp: str = "") -> dict:
    """Build one report folder. Returns {format: path}.

    Everything for a run lands in its own timestamped directory:

        reports/2026-08-15---21-56-47/
            report.pdf      for reading and sending
            report.md       for handing to an assistant
            report.json     for machines

    A folder per run rather than a suffix per file, so a run's outputs stay
    together and old ones are one delete away. The extra dashes in the
    timestamp separate the date from the time, which is otherwise a wall of
    digits.

    PDF needs reportlab. Without it you get report.html instead, which prints
    to a PDF from any browser, and a note saying so.

    Markdown and JSON are written FIRST, on purpose. They're plain text dumps
    that can't really fail, whereas the PDF runs a layout engine that can, and
    when it did the exception propagated out of here and took the other two
    formats with it: one bad flowable and you lost the entire run's results.
    Cheap formats first, then the fragile one inside its own guard.
    """
    from datetime import datetime

    report = rb.build_report(contexts)
    stamp = stamp or datetime.now().strftime("%Y-%m-%d---%H-%M-%S")
    folder = Path(out_dir) / stamp
    folder.mkdir(parents=True, exist_ok=True)

    written: dict = {}

    for name, text in (("report.md", render_markdown(report)),
                       ("report.json", render_json(report))):
        path = folder / name
        path.write_text(text, encoding="utf-8")
        written[path.suffix.lstrip(".")] = path

    try:
        from tests.test_helpers.report_pdf import render_pdf
        written["pdf"] = render_pdf(report, folder / "report.pdf")
    except ImportError:
        path = folder / "report.html"
        path.write_text(render_html(report), encoding="utf-8")
        written["html"] = path
        written["_note"] = ("reportlab not installed, wrote HTML instead. "
                            "pip install reportlab for a PDF.")
    except Exception as exc:                                    # noqa: BLE001
        # Layout failures, font problems, a corrupt output path. None of them
        # are worth losing the report over, so fall back to HTML and say what
        # broke instead of raising.
        path = folder / "report.html"
        path.write_text(render_html(report), encoding="utf-8")
        written["html"] = path
        written["_note"] = (f"PDF failed ({type(exc).__name__}: {exc}). "
                            f"Wrote HTML instead; report.md and report.json "
                            f"are complete.")

    return written
