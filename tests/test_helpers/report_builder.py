from __future__ import annotations

import html
import json
import math
import platform
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

# tests/test_helpers/report_builder.py -> repo root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Keep the assistant copy inside a single-shot context window. Failures-only
# with these caps lands well under it for a dozen failures.
MAX_STDOUT_LINES = 200
MAX_TRACEBACK_LINES = 60
MAX_CONFIG_ROWS = 200

# Outputs worth pulling to the top of a failure page, per kind. Everything else
# is still in the result JSON; these are the ones you'd look at first.
_HEADLINE_OUTPUTS = {
    "steady": ("reached_apogee", "target_apogee_reached", "fuel_mass",
               "burntime", "thrust", "Isp", "total_impulse",
               "average_oxidizer_to_fuel_ratio", "initial_internal_fuel_radius"),
    "unsteady": ("apogee_m_asl", "apogee_m_agl", "max_velocity_ms",
                 "burnout_time_s", "total_impulse_Ns", "max_thrust_N"),
}


# =============================================================================
# The report object
# =============================================================================

@dataclass
class Report:
    """Everything the three renderers need, computed once."""

    contexts: list = field(default_factory=list)
    environment: dict = field(default_factory=dict)
    generated_at: str = ""

    @property
    def failures(self) -> list:
        return [c for c in self.contexts if not passed(c)]

    @property
    def passes(self) -> list:
        return [c for c in self.contexts if passed(c)]

    def by_kind(self) -> dict:
        """Contexts grouped by kind, steady before unsteady."""
        grouped = defaultdict(list)
        for ctx in self.contexts:
            grouped[ctx.kind].append(ctx)
        return {k: grouped[k] for k in ("steady", "unsteady") if k in grouped}

    def by_sim_type(self) -> dict:
        """Finer grouping, matching the console summary's rows."""
        grouped = defaultdict(list)
        for ctx in self.contexts:
            grouped[ctx.sim_type].append(ctx)
        return dict(grouped)


def passed(ctx) -> bool:
    """The verdict. TestContext already owns the rule; don't restate it here,
    or the report and the console can end up disagreeing."""
    return bool(ctx.passed)


def build_report(contexts: Iterable) -> Report:
    return Report(
        contexts=list(contexts),
        environment=collect_environment(),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


# =============================================================================
# Environment
# =============================================================================

def collect_environment() -> dict:
    """Versions and commit, once per report.

    Matters most when the report leaves this machine: half of "why does it do
    that" questions are answered by a library version.
    """
    env = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cwd": str(_PROJECT_ROOT),
    }

    for name in ("numpy", "scipy", "matplotlib", "rocketcea", "pypropep",
                 "json5"):
        try:
            module = __import__(name)
            env[name] = getattr(module, "__version__", "installed")
        except Exception:                       # noqa: BLE001
            env[name] = "not installed"

    try:
        env["app_version"] = (_PROJECT_ROOT / "VERSION").read_text(
            encoding="utf-8").strip()
    except OSError:
        env["app_version"] = "unknown"

    env.update(_git_state())
    return env


def _git_state() -> dict:
    """Commit and dirty flag, so a report can be tied to a tree state."""
    def run(*args) -> str:
        try:
            return subprocess.run(
                ["git", *args], cwd=_PROJECT_ROOT, capture_output=True,
                text=True, timeout=5).stdout.strip()
        except Exception:                       # noqa: BLE001
            return ""

    commit = run("rev-parse", "--short", "HEAD")
    if not commit:
        return {"git_commit": "unavailable", "git_dirty": "unknown"}
    return {
        "git_commit": commit,
        "git_branch": run("rev-parse", "--abbrev-ref", "HEAD") or "unknown",
        "git_dirty": "yes" if run("status", "--porcelain") else "no",
    }


# =============================================================================
# Analysis: checks
# =============================================================================

def _resolve(data: Any, dotted: str) -> tuple[bool, Any]:
    """Walk a dotted path. Mirrors the helper the checks use."""
    node = data
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, (list, tuple)) and part.isdigit() \
                and int(part) < len(node):
            node = node[int(part)]
        else:
            return False, None
    return True, node


def check_detail(ctx) -> list[dict]:
    """Per-check rows with the numbers spelled out.

    The console message already says "wanted 23716±300"; what it doesn't say is
    that you're 12% low. A 0.5% miss is a tolerance to widen and a 12% miss is
    a bug, and that distinction is the whole point of running these.
    """
    rows: list[dict] = []
    checks = (ctx.metadata or {}).get("checks") or {}

    for path, spec in (checks.get("value_within") or {}).items():
        try:
            target, tolerance = float(spec[0]), float(spec[1])
        except (TypeError, ValueError, IndexError):
            continue
        found, actual = _resolve(ctx.result, path)
        rows.append(_numeric_row("value_within", path, actual, found,
                                 expected=f"{target} ± {tolerance}",
                                 reference=target))

    for path, spec in (checks.get("value_between") or {}).items():
        try:
            low, high = float(spec[0]), float(spec[1])
        except (TypeError, ValueError, IndexError):
            continue
        found, actual = _resolve(ctx.result, path)
        midpoint = (low + high) / 2.0
        rows.append(_numeric_row("value_between", path, actual, found,
                                 expected=f"{low} .. {high}",
                                 reference=midpoint))

    for path in (checks.get("json_path_exists") or []):
        found, actual = _resolve(ctx.result, path)
        rows.append({
            "check": "json_path_exists", "path": path,
            "expected": "present", "actual": "present" if found else "MISSING",
            "delta": "", "percent": "", "ok": found,
        })

    return rows


def _numeric_row(check: str, path: str, actual, found: bool,
                 *, expected: str, reference: float) -> dict:
    if not found:
        return {"check": check, "path": path, "expected": expected,
                "actual": "MISSING (path not in result)", "delta": "",
                "percent": "", "ok": False}
    try:
        value = float(actual)
    except (TypeError, ValueError):
        return {"check": check, "path": path, "expected": expected,
                "actual": repr(actual), "delta": "", "percent": "",
                "ok": False}

    delta = value - reference
    percent = (delta / reference * 100.0) if reference else float("nan")
    return {
        "check": check, "path": path, "expected": expected,
        "actual": f"{value:.6g}",
        "delta": f"{delta:+.6g}",
        "percent": "" if math.isnan(percent) else f"{percent:+.2f}%",
        "ok": None,        # the real verdict lives in ctx.check_results
    }


# =============================================================================
# Analysis: the config
# =============================================================================

def flatten(data: Any, prefix: str = "") -> dict:
    """Nested dict to {dotted.key: value}, leaving [value, unit] pairs whole."""
    flat: dict = {}
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                flat.update(flatten(value, path))
            else:
                flat[path] = value
    else:
        flat[prefix] = data
    return flat


def config_rows(ctx) -> list[dict]:
    """The config as a table: key, value, unit.

    A pair renders as two columns so the unit is scannable down the page,
    which is where unit bugs become visible.
    """
    rows = []
    for path, value in flatten(ctx.config).items():
        if isinstance(value, (list, tuple)) and len(value) == 2 \
                and isinstance(value[1], str):
            rows.append({"key": path, "value": _short(value[0]),
                         "unit": value[1]})
        else:
            rows.append({"key": path, "value": _short(value), "unit": ""})
    return rows[:MAX_CONFIG_ROWS]


def baseline_for(ctx) -> Optional[Path]:
    """The baseline config this one is presumably a variation of.

    Everything in these directories is numbered, and 00_* is the baseline by
    convention. Finding it lets the report lead with a three-row diff instead
    of a sixty-row table.
    """
    directory = ctx.config_path.parent
    candidates = sorted(directory.glob("00_*.jsonc"))
    for candidate in candidates:
        if candidate != ctx.config_path:
            return candidate
    return None


def config_diff(ctx) -> list[dict]:
    """Rows where this config differs from its baseline."""
    baseline_path = baseline_for(ctx)
    if baseline_path is None:
        return []
    try:
        from tests.test_helpers.backend_tests_helpers import load_test_config
        base_config, _meta = load_test_config(baseline_path)
    except Exception:                           # noqa: BLE001
        return []

    mine, theirs = flatten(ctx.config), flatten(base_config)
    diff = []
    for key in sorted(set(mine) | set(theirs)):
        # metadata.checks differs on every test by construction — that's what
        # makes them different tests. Listing it drowns the two or three input
        # changes that actually explain the failure.
        if key.startswith("metadata.checks") or key.startswith("metadata.simulation"):
            continue
        a, b = theirs.get(key, "<absent>"), mine.get(key, "<absent>")
        if a != b:
            diff.append({"key": key, "baseline": _short(a), "this": _short(b)})
    return diff


def physics_view(ctx) -> list[dict]:
    """The config as the engine received it: SI, and radii not diameters.

    The single most useful table in this report. Nearly every real bug this
    project has had was a conversion mistake — a launch angle converted twice,
    a parachute area computed from the wrong diameter — and all of them are
    obvious the moment you can see "as written" beside "as the physics saw it".
    """
    try:
        from src.backend.common.preflight import _to_physics_values
    except Exception:                           # noqa: BLE001
        return []

    inputs = ctx.config.get("rocket_inputs")
    if not isinstance(inputs, dict):
        return []

    # Unsteady nests per control volume; steady is flat.
    blocks = ({k: v for k, v in inputs.items() if isinstance(v, dict)}
              or {"": inputs})

    rows = []
    for block_name, block in blocks.items():
        try:
            converted = _to_physics_values(block)
        except Exception as exc:                # noqa: BLE001
            rows.append({"key": block_name or "rocket_inputs",
                         "written": "", "si": f"conversion failed: {exc}"})
            continue
        written = flatten(block)
        for key, value in flatten(converted).items():
            label = f"{block_name}.{key}" if block_name else key
            rows.append({
                "key": label,
                "written": _short(_written_for(written, key)),
                "si": _short(value),
            })
    return rows


def _written_for(written: dict, key: str):
    """The as-written value for a converted key.

    The conversion renames diameters to radii, so a straight lookup leaves the
    most conversion-prone rows blank — exactly the ones worth reading. Fall
    back to the diameter the radius came from, and say so.
    """
    if key in written:
        return written[key]
    if key.endswith("_radius"):
        diameter = key[: -len("_radius")] + "_diameter"
        if diameter in written:
            return f"{written[diameter]}  (as {diameter})"
    return ""


# =============================================================================
# Analysis: the run
# =============================================================================

_LOOP_RE = re.compile(
    r"loop\s+(\d+).*?apogee\s+(?:achieved|reached)?[:\s]+([-\d.eE+]+)",
    re.IGNORECASE)


def convergence_trace(ctx) -> list[dict]:
    """Each convergence iteration and the apogee it produced.

    Straight out of stdout, which already prints it. Reading the sequence tells
    you whether the search converged, oscillated, or ran into the minimum port
    radius — three different bugs that all look like "wrong apogee".
    """
    trace = []
    for match in _LOOP_RE.finditer(ctx.stdout or ""):
        try:
            trace.append({"loop": int(match.group(1)),
                          "apogee": float(match.group(2))})
        except ValueError:
            continue
    for index, row in enumerate(trace):
        previous = trace[index - 1]["apogee"] if index else None
        row["change"] = ("" if previous is None
                         else f"{row['apogee'] - previous:+.6g}")
    return trace


_PHASE_RE = re.compile(r"\bphase[_\s]*([0-9]+[a-c]?)\b", re.IGNORECASE)


def phase_timeline(ctx) -> list[str]:
    """Phases the unsteady run announced, in order, deduplicated.

    If it never left phase 2, every number downstream is noise and shouldn't be
    read as evidence of anything.
    """
    seen, ordered = set(), []
    for match in _PHASE_RE.finditer(ctx.stdout or ""):
        phase = match.group(1).lower()
        if phase not in seen:
            seen.add(phase)
            ordered.append(f"phase_{phase}")
    return ordered


def non_finite_scan(ctx) -> list[dict]:
    """First index where each result series goes NaN or infinite.

    Localises a blow-up to one series, and therefore usually to one control
    volume, instead of leaving you with "the run failed".
    """
    findings = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else str(key))
        elif isinstance(node, (list, tuple)):
            for index, value in enumerate(node):
                if isinstance(value, float) and not math.isfinite(value):
                    findings.append({"series": path, "index": index,
                                     "value": repr(value),
                                     "length": len(node)})
                    return              # first one is the informative one
        elif isinstance(node, float) and not math.isfinite(node):
            findings.append({"series": path, "index": "-", "value": repr(node),
                             "length": "-"})

    walk(ctx.result, "")
    return findings


def headline_outputs(ctx) -> list[dict]:
    """The handful of numbers you'd look at first, so you needn't open the JSON."""
    rows = []
    for key in _HEADLINE_OUTPUTS.get(ctx.kind, ()):
        for container in ("rocket_parameters", "performance.overall",
                          "performance", ""):
            path = f"{container}.{key}" if container else key
            found, value = _resolve(ctx.result, path)
            if found:
                rows.append({"key": key, "value": _short(value)})
                break
    return rows


def warnings_summary(ctx) -> list[dict]:
    """Unsteady warnings grouped by severity. A failing run with an unheeded
    critical is usually explaining itself."""
    warnings = ctx.result.get("warnings")
    if not isinstance(warnings, dict):
        return []
    entries = warnings.get("triggered_warnings")
    entries = entries if isinstance(entries, dict) else warnings

    rows = []
    for warning_id, entry in entries.items():
        if not isinstance(entry, dict) or "message" not in entry:
            continue
        rows.append({"severity": entry.get("severity", "advisory"),
                     "id": warning_id, "message": str(entry["message"])})
    order = {"critical": 0, "warning": 1, "advisory": 2}
    rows.sort(key=lambda r: order.get(r["severity"], 3))
    return rows


# =============================================================================
# Analysis: clustering
# =============================================================================

def cluster_failures(report: Report) -> list[dict]:
    """Group failures by symptom.

    A dozen failures usually come from three causes. Saying so at the top is
    the biggest single time-saver in the report, because it stops you from
    debugging the same bug four times.
    """
    buckets: dict[tuple, list] = defaultdict(list)
    for ctx in report.failures:
        # Cluster on the SHAPE of the failure, not its numbers: two tests
        # missing the same check by different amounts share a cause.
        if ctx.outcome != ctx.expected:
            symptom = f"expected {ctx.expected}, got {ctx.outcome}"
        else:
            first_failed = next(
                (name for name, ok, _msg in ctx.check_results if not ok), "")
            symptom = f"check failed: {first_failed}"
        signature = (symptom,
                     type(ctx.exception).__name__ if ctx.exception else "")
        buckets[signature].append(ctx)

    clusters = [
        {"symptom": signature[0],
         "exception": signature[1],
         "count": len(members),
         "tests": [c.name for c in members]}
        for signature, members in buckets.items()
    ]
    clusters.sort(key=lambda c: -c["count"])
    return clusters


def timing_outliers(report: Report, factor: float = 8.0) -> list[dict]:
    """Tests far slower than the median for their kind.

    Worth surfacing even when they pass: a validation test that takes ten
    seconds to not reject something is telling you the validator never ran.
    """
    outliers = []
    for kind, contexts in report.by_kind().items():
        times = sorted(c.elapsed_s for c in contexts)
        if len(times) < 3:
            continue
        median = times[len(times) // 2]
        if median <= 0:
            continue
        for ctx in contexts:
            if ctx.elapsed_s > median * factor:
                outliers.append({
                    "test": ctx.name, "kind": kind,
                    "elapsed": f"{ctx.elapsed_s:.1f}s",
                    "median": f"{median:.1f}s",
                })
    return outliers


# =============================================================================
# Trimming
# =============================================================================

def tail(text: str, max_lines: int) -> str:
    """Keep the END of a log. That's where the failure is."""
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    dropped = len(lines) - max_lines
    return f"[... {dropped} earlier lines trimmed ...]\n" + \
        "\n".join(lines[-max_lines:])


def _short(value: Any, limit: int = 90) -> str:
    if isinstance(value, float):
        text = f"{value:.6g}"
    elif isinstance(value, (list, tuple)) and len(value) > 6:
        text = f"[{len(value)} items] {value[:3]} …"
    else:
        text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"
