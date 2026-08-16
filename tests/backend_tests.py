"""
Runs all backend tests in steady_configs and unsteady_configs

Each config under tests/steady_configs and tests/unsteady_configs is one test. Its metadata carries 'expected_output' (what should happen) and an optional
'checks' block (assertions on the output).  A test passes when both agree with reality. See backend_tests_helpers.py for how to add a new kind of check.

Results are written to tests/test_outputs and deleted afterwards unless keep_results=True
"""
# don't change plt import
import matplotlib
matplotlib.use("Agg")

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.backend.steady.steady_main import run_steady
from src.backend.unsteady.engine.phase_runner import run_unsteady

from tests.backend_tests_helpers import (
    cleanup_output, discover_configs, execute_test, make_console,
    print_failure_detail, print_section, print_summary, print_test_result,
    write_reports,
)


_TESTS_DIR = Path(__file__).resolve().parent
STEADY_CONFIGS_DIR = _TESTS_DIR / "steady_configs"
UNSTEADY_CONFIGS_DIR = _TESTS_DIR / "unsteady_configs"
TEST_OUTPUTS_DIR = _TESTS_DIR / "test_outputs"


def run_backend_tests(all_steady_tests=True, all_unsteady_tests=True,
                      only=None, keep_results=False, timeout=100,
                      reports=True):
    """
    Run the backend test suite and print the results

    all_steady_tests / all_unsteady_tests: whether to run each family at all
    only: none for everything, or a string / list of strings
    keep_results: false deletes each test's output once its checks have run, leaving test_outputs empty
    timeout: per-test wall-clock budget in seconds, can be none for no timeout
    reports: write tests/reports/report_<stamp>.{html,md,json} at the end.
             The html prints to a PDF with one page per failure; the md is the
             one to hand to an assistant. Set false to skip.

    returns the list of TestContext objects, so a caller can inspect results beyond what gets printed
    """
    console = make_console()
    contexts = []

    if all_steady_tests:
        contexts += _run_steady_tests(console, only, keep_results, timeout)
    if all_unsteady_tests:
        contexts += _run_unsteady_tests(console, only, keep_results, timeout)

    if not contexts:
        console.print("\n[yellow]No configs matched.[/yellow]")
        return contexts

    for ctx in contexts:
        if not ctx.passed:
            print_failure_detail(console, ctx)

    print_summary(console, contexts)

    if reports:
        try:
            written = write_reports(contexts)
            console.print()
            console.print("[bold]Reports[/bold]")
            for label, path in written.items():
                console.print(f"  {label:5s} {path}")
            console.print("[dim]  open the .html and print to PDF; "
                          "hand the .md to an assistant[/dim]")
        except Exception as exc:                # noqa: BLE001
            # A reporting failure must never mask the test results, which are
            # already on screen at this point.
            console.print(f"\n[yellow]Could not write reports: "
                          f"{type(exc).__name__}: {exc}[/yellow]")

    return contexts


def _run_steady_tests(console, only, keep_results, timeout):
    """run every steady config"""
    configs = discover_configs(STEADY_CONFIGS_DIR, only)
    print_section(console, "Steady", len(configs))
    return _run_all(console, configs, "steady", run_steady,
                    TEST_OUTPUTS_DIR / "steady", keep_results, timeout)


def _run_unsteady_tests(console, only, keep_results, timeout):
    """run every unsteady config"""
    configs = discover_configs(UNSTEADY_CONFIGS_DIR, only)
    print_section(console, "Unsteady", len(configs))
    return _run_all(console, configs, "unsteady", run_unsteady,
                    TEST_OUTPUTS_DIR / "unsteady", keep_results, timeout)


def _run_all(console, configs, kind, runner, output_dir, keep_results, timeout):
    contexts = []
    for config_path in configs:
        # A transient spinner, so a long unsteady run doesn't look like a hang.
        # It clears itself once the test finishes and the result line prints.
        with console.status(f"[dim]running {config_path.stem}...[/dim]"):
            ctx = execute_test(config_path, kind, runner, output_dir, timeout)
        print_test_result(console, ctx)
        if not keep_results:
            cleanup_output(ctx)
        contexts.append(ctx)
    return contexts


if __name__ == "__main__":
    run_backend_tests(only="11_stress_long_burn.jsonc")
