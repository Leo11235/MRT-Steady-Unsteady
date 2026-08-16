from __future__ import annotations

import contextlib
import ctypes
import io
import json
import math
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import json5

from rich.console import Console
from rich.table import Table


# tests declare which of these they expect
EXPECTED_OUTPUTS = (
    "success", # ran to completion without raising
    "config_error", # the file is missing, malformed, or has a bad unit
    "validation_error", # parsed fine, but the schema/alternate-field rules rejected it
    "physics_error", # died inside the simulation itself
    "solver_stalled", # SolverStalledError: the operating point isn't integrable
    "timeout", # outlived its time budget (see run_with_timeout)
)

# a KeyError or ValueError coming out of one of these is a validation problem; 
# the same exception type raised anywhere else is a physics problem
_VALIDATION_MODULES = (
    "variable_initialization.py",
    "config.py",
    "input_schema",
)

################################################################################################################
# test context
@dataclass
class TestContext:
    """
    everything known about one test, before and after it runs
    """

    config_path: Path
    kind: str # "steady" or "unsteady"
    config: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    # populated post run
    outcome: str = "" # one of EXPECTED_OUTPUTS
    exception: Optional[BaseException] = None
    traceback_text: str = ""
    stdout: str = ""
    elapsed_s: float = 0.0
    result_path: Optional[Path] = None # the JSON the backend wrote
    result: dict = field(default_factory=dict)
    check_results: list = field(default_factory=list) # (name, passed, message)

    @property
    def name(self) -> str:
        return self.config_path.stem

    @property
    def expected(self) -> str:
        return str(self.metadata.get("expected_output") or "success").strip()

    # output dir path
    @property
    def output_dir(self) -> Optional[Path]:
        """Directory the run's artifacts live in.  Paths in 'files_exist' are
        resolved against this."""
        return self.result_path.parent if self.result_path else None

    # what gets deleted on cleanup
    @property
    def artifact_root(self) -> Optional[Path]:
        if not self.result_path:
            return None
        return self.result_path.parent if self.kind == "unsteady" else self.result_path

    # used to identify different conversion/param/hotfire tests for steady
    @property
    def sim_type(self) -> str:
        if self.kind == "unsteady":
            return "unsteady"
        return str(self.config.get("simulation_settings", {}).get("simulation_type", "unknown"))

    @property
    def passed(self) -> bool:
        if self.outcome != self.expected:
            return False
        return all(ok for _, ok, _ in self.check_results)

    def failure_reason(self) -> str:
        if self.outcome != self.expected:
            return f"expected {self.expected}, got {self.outcome}"
        bad = [f"{n}: {m}" for n, ok, m in self.check_results if not ok]
        return "; ".join(bad) if bad else ""


# discovery and loading

def discover_configs(configs_dir: Path, only: Any = None) -> list[Path]:
    """
    every .jsonc under 'configs_dir', sorted, optionally filtered
    'only' may be None (everything), a string, or a list of strings
    """
    configs_dir = Path(configs_dir)
    if not configs_dir.is_dir():
        return []
    paths = sorted(configs_dir.glob("*.jsonc"))
    if only is None:
        return paths
    patterns = [only] if isinstance(only, str) else list(only)
    patterns = [str(p).lower() for p in patterns]
    return [p for p in paths if any(pat in p.name.lower() for pat in patterns)]


def load_test_config(path: Path) -> tuple[dict, dict]:
    """
    Parse a test config and dig out its metadata
    """
    with open(path, "r", encoding="utf-8") as f:
        cfg = json5.load(f)
    metadata = cfg.get("metadata")
    if metadata is None:
        metadata = cfg.get("config", {}).get("metadata", {})
    return cfg, (metadata or {})


# =============================================================================
# Stdout capture
# =============================================================================

@contextlib.contextmanager
def capture_stdout():
    """
    Swallow everything the backend prints and hand it back as a string

    the simulators are chatty (phase banners, convergence iterations); keep it and print only when a test fails
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        yield buffer

############################################################################################################
# Timeout
# python normally gives no way to stop a function that's already running
# uses worker thread + an asynchronously injected exception to expose PyThreadState_SetAsyncExc
class TestTimeout(Exception):
    """raised inside a worker thread that outlived its time budget"""


def _raise_in_thread(thread_ident: int, exc_type: type) -> bool:
    """
    schedule 'exc_type' to be raised inside the thread with this id
    returns True if exactly one thread was targeted
    """
    affected = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread_ident), ctypes.py_object(exc_type)
    )
    if affected > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread_ident), None)
        return False
    return affected == 1


def run_with_timeout(fn: Callable[[], Any], timeout_s: Optional[float],
                     grace_s: float = 5.0) -> tuple[Any, Optional[BaseException]]:
    """
    run 'fn()' with a wall-clock budget, returns (result, exception)

    'timeout_s=None' disables the budget and simply runs fn() in a thread.
    """
    box: dict[str, Any] = {"result": None, "exc": None}

    def _worker():
        try:
            box["result"] = fn()
        except BaseException as exc:      # noqa: BLE001 - we report, not handle
            box["exc"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout_s)

    if thread.is_alive():
        _raise_in_thread(thread.ident, TestTimeout)
        thread.join(grace_s)
        if box["exc"] is None:
            box["exc"] = TestTimeout(
                f"exceeded the {timeout_s}s budget"
                + ("" if not thread.is_alive() else
                   " and did not stop when asked (likely parked inside compiled code)")
            )

    return box["result"], box["exc"]


###################################################################################
# Outcome classification

def classify_exception(exc: Optional[BaseException]) -> str:
    """
    map whatever the backend raised onto one entry in EXPECTED_OUTPUTS
    """
    if exc is None:
        return "success"
    if isinstance(exc, TestTimeout):
        return "timeout"
    if type(exc).__name__ == "SolverStalledError":
        return "solver_stalled"
    if isinstance(exc, (FileNotFoundError, json.JSONDecodeError)):
        return "config_error"

    # which file raised? go to the deepest frame, then back out
    frames = []
    tb = exc.__traceback__
    while tb is not None:
        frames.append(Path(tb.tb_frame.f_code.co_filename).name)
        tb = tb.tb_next
    deepest = frames[-1] if frames else ""

    # an unknown unit or an unparseable pair comes out of the conversion layer, which is a problem with the config file rather than with the physics
    if deepest == "variable_conversions.py":
        return "config_error"
    if any(m in f for f in frames[-3:] for m in _VALIDATION_MODULES):
        return "validation_error"
    if isinstance(exc, (KeyError, ValueError, TypeError)):
        return "physics_error"
    return "physics_error"

#################################################################################
# Checks

def _resolve(data: Any, dotted: str) -> tuple[bool, Any]:
    """
    walk a dotted path into nested dicts/lists
    "performance.overall.apogee_m_agl" or "data.time.0"
    returns (found, value)
    """
    current = data
    for part in dotted.split("."):
        if isinstance(current, dict):
            if part not in current:
                return False, None
            current = current[part]
        elif isinstance(current, (list, tuple)):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return False, None
        else:
            return False, None
    return True, current


def check_files_exist(ctx: TestContext, rel_paths: Iterable[str]) -> tuple[bool, str]:
    """
    every named path exists under the run's output directory
    """
    if ctx.output_dir is None:
        return False, "the run produced no output directory"
    missing = []
    for rel in rel_paths:
        wants_dir = str(rel).endswith("/")
        target = ctx.output_dir / str(rel).rstrip("/")
        if wants_dir:
            if not target.is_dir():
                missing.append(f"{rel} (not a directory)")
            elif not any(target.iterdir()):
                missing.append(f"{rel} (empty)")
        elif not target.exists():
            missing.append(str(rel))
    if missing:
        return False, "missing: " + ", ".join(missing)
    return True, f"all {len(list(rel_paths))} present"


def check_json_path_exists(ctx: TestContext, paths: Iterable[str]) -> tuple[bool, str]:
    """
    every dotted path resolves to something in the result JSON
    """
    missing = [p for p in paths if not _resolve(ctx.result, p)[0]]
    if missing:
        return False, "absent: " + ", ".join(missing)
    return True, "all present"


def check_value_within(ctx: TestContext, spec: dict) -> tuple[bool, str]:
    """
    {"path.to.value": [expected, tolerance]} <-- absolute tolerance
    """
    problems = []
    for dotted, (expected, tolerance) in spec.items():
        found, value = _resolve(ctx.result, dotted)
        if not found:
            problems.append(f"{dotted} absent")
        elif not isinstance(value, (int, float)):
            problems.append(f"{dotted} is {type(value).__name__}, not a number")
        elif math.isnan(value) or abs(value - expected) > tolerance:
            problems.append(f"{dotted}={value:.4g}, wanted {expected}±{tolerance}")
    return (not problems), "; ".join(problems) or "all within tolerance"


def check_value_equals(ctx: TestContext, spec: dict) -> tuple[bool, str]:
    """
    {"path.to.value": expected} <-- exact match

    For booleans and strings, where value_within makes no sense. Compares with
    == rather than `is`, so JSON true/false and Python True/False agree, but
    guards the bool/number case: in Python False == 0 is true, and a test
    asserting a flag is false shouldn't silently accept a zero.
    """
    problems = []
    for dotted, expected in spec.items():
        found, value = _resolve(ctx.result, dotted)
        if not found:
            problems.append(f"{dotted} absent")
        elif isinstance(expected, bool) != isinstance(value, bool):
            problems.append(f"{dotted} is {type(value).__name__} "
                            f"({value!r}), wanted {type(expected).__name__} "
                            f"{expected!r}")
        elif value != expected:
            problems.append(f"{dotted}={value!r}, wanted {expected!r}")
    return (not problems), "; ".join(problems) or "all equal"


def check_value_between(ctx: TestContext, spec: dict) -> tuple[bool, str]:
    """
    {"path.to.value": [low, high]} <-- inclusive band
    """
    problems = []
    for dotted, (low, high) in spec.items():
        found, value = _resolve(ctx.result, dotted)
        if not found:
            problems.append(f"{dotted} absent")
        elif not isinstance(value, (int, float)):
            problems.append(f"{dotted} is {type(value).__name__}, not a number")
        elif math.isnan(value) or not (low <= value <= high):
            problems.append(f"{dotted}={value:.4g}, wanted {low}..{high}")
    return (not problems), "; ".join(problems) or "all in range"


def check_list_length(ctx: TestContext, spec: dict) -> tuple[bool, str]:
    """
    {"path.to.list": n} <-- the list has exactly n entries
    """
    problems = []
    for dotted, expected in spec.items():
        found, value = _resolve(ctx.result, dotted)
        if not found:
            problems.append(f"{dotted} absent")
        elif not hasattr(value, "__len__"):
            problems.append(f"{dotted} has no length")
        elif len(value) != expected:
            problems.append(f"{dotted} has {len(value)}, wanted {expected}")
    return (not problems), "; ".join(problems) or "lengths match"


def check_warnings_equal(ctx: TestContext, expected: Any) -> tuple[bool, str]:
    """
    the warnings block equals 'expected'
    mostly used with "disabled" to prove metadata.warnings=false took effect
    """
    actual = ctx.result.get("warnings")
    if actual == expected:
        return True, "matches"
    shown = list(actual)[:4] if isinstance(actual, dict) else actual
    return False, f"warnings is {shown!r}, wanted {expected!r}"


def check_reaches_phases(ctx: TestContext, phases: Iterable[str]) -> tuple[bool, str]:
    """
    every named phase appears in the phase series
    this is how you assert the sim got all the way to landing rather than stopping early at a phase cap
    """
    found, series = _resolve(ctx.result, "data.phase")
    if not found:
        return False, "data.phase absent"
    visited = set(series)
    missing = [p for p in phases if p not in visited]
    if missing:
        return False, f"never reached {', '.join(missing)} (visited {sorted(visited)})"
    return True, "all reached"


def check_no_nans_in(ctx: TestContext, series_names: Iterable[str]) -> tuple[bool, str]:
    """
    named time series contain no NaN or null entries
    export() writes NaN out as null, so we check for both
    """
    problems = []
    for name in series_names:
        found, series = _resolve(ctx.result, f"data.{name}")
        if not found:
            problems.append(f"{name} absent")
            continue
        bad = sum(1 for v in series
                  if v is None or (isinstance(v, float) and math.isnan(v)))
        if bad:
            problems.append(f"{name} has {bad}/{len(series)} null-or-NaN")
    return (not problems), "; ".join(problems) or "clean"


def check_custom(ctx: TestContext, func_name: str) -> tuple[bool, str]:
    """
    escape hatch: run a named function in this module

    for assertions that can't be expressed as data
    the function takes a TestContext and returns (passed, message)
    """
    fn = globals().get(func_name)
    if not callable(fn):
        return False, f"no function named {func_name!r} in backend_tests_helpers"
    try:
        return fn(ctx)
    except Exception as exc:                        # noqa: BLE001
        return False, f"{func_name} raised {type(exc).__name__}: {exc}"


######################################################################
# Custom checks
#
# named from a config as {"custom_check": "check_whatever"}
# write one whenever an assertion is too specific to express as data

_PDF_MAGIC = b"%PDF-"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_MIN_PLOT_BYTES = 2000 # a real plot is tens of KB; anything this small is a stub


def check_graph_files_are_real(ctx: TestContext) -> tuple[bool, str]:
    """
    graphs.pdf and graphs/*.png are rendered, not empty stubs
    """
    if ctx.output_dir is None:
        return False, "the run produced no output directory"

    problems = []

    pdf = ctx.output_dir / "graphs.pdf"
    if not pdf.exists():
        problems.append("graphs.pdf missing")
    else:
        size = pdf.stat().st_size
        header = pdf.read_bytes()[:len(_PDF_MAGIC)]
        if header != _PDF_MAGIC:
            problems.append(f"graphs.pdf does not start with {_PDF_MAGIC!r}")
        elif size < _MIN_PLOT_BYTES:
            problems.append(f"graphs.pdf is only {size} bytes")

    png_dir = ctx.output_dir / "graphs"
    if not png_dir.is_dir():
        problems.append("graphs/ missing")
    else:
        pngs = sorted(png_dir.glob("*.png"))
        if not pngs:
            problems.append("graphs/ contains no .png files")
        else:
            bad = [p.name for p in pngs
                   if p.stat().st_size < _MIN_PLOT_BYTES
                   or p.read_bytes()[:len(_PNG_MAGIC)] != _PNG_MAGIC]
            if bad:
                problems.append(f"{len(bad)}/{len(pngs)} PNGs empty or malformed: "
                                + ", ".join(bad[:4]))

    if problems:
        return False, "; ".join(problems)
    return True, "PDF and PNGs render with real content"


CHECKS: dict[str, Callable[..., tuple[bool, str]]] = {
    "files_exist":      check_files_exist,
    "json_path_exists": check_json_path_exists,
    "value_within":     check_value_within,
    "value_equals":     check_value_equals,
    "value_between":    check_value_between,
    "list_length":      check_list_length,
    "warnings_equal":   check_warnings_equal,
    "reaches_phases":   check_reaches_phases,
    "no_nans_in":       check_no_nans_in,
    "custom_check":     check_custom,
}


def run_checks(ctx: TestContext) -> list[tuple[str, bool, str]]:
    """
    run every check the config declares
    """
    checks = ctx.metadata.get("checks") or {}
    if not checks or ctx.outcome != "success":
        return []
    results = []
    for name, argument in checks.items():
        fn = CHECKS.get(name)
        if fn is None:
            results.append((name, False, f"unknown check {name!r}"))
            continue
        try:
            passed, message = fn(ctx, argument)
        except Exception as exc:                    # noqa: BLE001
            passed, message = False, f"check raised {type(exc).__name__}: {exc}"
        results.append((name, passed, message))
    return results


# running one test
def execute_test(config_path: Path, kind: str, runner: Callable,
                 output_dir: Path, timeout: Optional[float]) -> TestContext:
    """
    run one config end to end and return a fully-populated TestContext
    """
    ctx = TestContext(config_path=Path(config_path), kind=kind)
    try:
        ctx.config, ctx.metadata = load_test_config(ctx.config_path)
    except Exception as exc:                        # noqa: BLE001
        ctx.exception, ctx.outcome = exc, "config_error"
        return ctx

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    with capture_stdout() as buffer:
        result, exc = run_with_timeout(
            lambda: runner(ctx.config_path.name, ctx.config_path.parent, output_dir),
            timeout,
        )
    ctx.elapsed_s = time.perf_counter() - started
    ctx.stdout = buffer.getvalue()
    ctx.exception = exc
    ctx.outcome = classify_exception(exc)

    if exc is not None:
        import traceback
        ctx.traceback_text = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__))
    elif result is not None:
        ctx.result_path = Path(result)
        try:
            with open(ctx.result_path, "r", encoding="utf-8") as f:
                ctx.result = json.load(f)
        except Exception as read_exc: # noqa: BLE001
            # run claimed success but reading results impossible
            ctx.outcome = "physics_error"
            ctx.exception = read_exc

    ctx.check_results = run_checks(ctx)
    return ctx


def cleanup_output(ctx: TestContext) -> None:
    """
    delete what this test wrote
    """
    root = ctx.artifact_root
    if root is None or not root.exists():
        return
    try:
        shutil.rmtree(root) if root.is_dir() else root.unlink()
    except OSError:
        pass # a locked file shouldn't fail the suite


# reporting
_STATUS_STYLES = {True: ("PASS", "bold green"), False: ("FAIL", "bold red")}

_GROUP_LABELS = {
    "hotfire":               "steady / hotfire",
    "fuel_mass_convergence": "steady / convergence",
    "parametric_study":      "steady / parametric",
    "unsteady":              "unsteady",
}


def make_console() -> Console:
    return Console(highlight=False)


def print_section(console: Console, title: str, count: int) -> None:
    console.print()
    console.rule(f"[bold]{title}[/bold]  ({count} config{'s' if count != 1 else ''})")


def print_test_result(console: Console, ctx: TestContext) -> None:
    label, style = _STATUS_STYLES[ctx.passed]
    reason = ctx.failure_reason()
    console.print(
        f"  [{style}]{label:<4}[/{style}]  "
        f"{ctx.name:<44} "
        f"[dim]{ctx.outcome:<16}[/dim] "
        f"[dim]{ctx.elapsed_s:6.1f}s[/dim]"
        + (f"  [red]{reason}[/red]" if reason else "")
    )


def print_failure_detail(console: Console, ctx: TestContext) -> None:
    console.print()
    console.rule(f"[red]{ctx.name}[/red]", style="red")
    if ctx.metadata.get("simulation_description"):
        console.print(f"[dim]{ctx.metadata['simulation_description']}[/dim]")
    console.print(f"[red]{ctx.failure_reason()}[/red]")
    if ctx.traceback_text:
        console.print(ctx.traceback_text.rstrip(), style="dim")
    if ctx.stdout.strip():
        tail = ctx.stdout.strip().splitlines()[-25:]
        console.print("[dim]--- last 25 lines of backend output ---[/dim]")
        for line in tail:
            console.print(f"  [dim]{line}[/dim]")


def print_summary(console: Console, contexts: list[TestContext]) -> None:
    """
    passed/failed per group, then the overall tally
    """
    table = Table(title="Backend test summary", title_style="bold",
                  header_style="bold", show_edge=True)
    table.add_column("Group")
    table.add_column("Passed", justify="right")
    table.add_column("Failed", justify="right")
    table.add_column("Time", justify="right")

    for sim_type, label in _GROUP_LABELS.items():
        group = [c for c in contexts if c.sim_type == sim_type]
        if not group:
            continue
        passed = sum(1 for c in group if c.passed)
        failed = len(group) - passed
        table.add_row(label, str(passed),
                      f"[red]{failed}[/red]" if failed else "0",
                      f"{sum(c.elapsed_s for c in group):.1f}s")

    other = [c for c in contexts if c.sim_type not in _GROUP_LABELS]
    if other:
        passed = sum(1 for c in other if c.passed)
        table.add_row("other", str(passed),
                      f"[red]{len(other) - passed}[/red]" if len(other) - passed else "0",
                      f"{sum(c.elapsed_s for c in other):.1f}s")

    total_passed = sum(1 for c in contexts if c.passed)
    total_failed = len(contexts) - total_passed
    table.add_section()
    table.add_row("[bold]total[/bold]", f"[bold]{total_passed}[/bold]",
                  f"[bold red]{total_failed}[/bold red]" if total_failed else "[bold]0[/bold]",
                  f"[bold]{sum(c.elapsed_s for c in contexts):.1f}s[/bold]")

    console.print()
    console.print(table)


# =============================================================================
# Reports
# =============================================================================
#
# The console output above is for watching a run. This is for reading one
# afterwards, and for handing to someone else.
#
# The rendering lives in tests/report_builder.py and tests/report_renderers.py
# rather than here, because it's a few hundred lines of analysis and formatting
# that has nothing to do with deciding pass or fail. This is the entry point.

def write_reports(contexts, out_dir=None, *, stamp: str = "") -> dict:
    """Write html / md / json reports for a finished batch.

    Everything lands in tests/reports/<YYYY-MM-DD---HH-MM-SS>/, one folder per
    run. Returns {"pdf": Path, "md": Path, "json": Path}.

      pdf    for reading and sending. One page per failure.
      md     for handing to an assistant, and a fine fallback for a person.
             Markdown rather than JSON: fewer tokens for the same content and
             the structure survives.
      json   for machines. Run-over-run diffing, CI, that sort of thing.

    The PDF needs reportlab. Without it you get report.html instead, which
    prints to a PDF from any browser.
    """
    from pathlib import Path as _Path
    from tests.test_helpers.report_renderers import write_reports as _write

    if out_dir is None:
        # tests/test_helpers/ -> tests/reports/. Reports are output, not
        # helper code, so they stay beside the configs rather than in here.
        out_dir = _Path(__file__).resolve().parents[1] / "reports"
    return _write(contexts, out_dir, stamp=stamp)
