"""
Preflight sanity check for a simulation config.

Runs the same normalizer + input-range warnings that the backend uses
at load time, but exposed as a pure function that the UI can call
BEFORE handing the config off — giving the user a chance to change
their mind if the inputs look suspect.

Both functions here:
  - Deep-copy their input so nothing mutates the caller's dict.
  - Return a dict of warning entries keyed by warning ID (empty dict
    if the inputs look clean).  Callers show a modal when non-empty.
"""

from __future__ import annotations

from copy import deepcopy

from src.backend.common.input_normalizer import (
    normalize_steady_inputs,
    normalize_unsteady_inputs,
)


def preflight_unsteady(rocket_inputs: dict) -> dict:
    """Run the unsteady input-range checks.

    `rocket_inputs` is the FULL nested unsteady block, i.e. what the UI
    puts in `cfg["rocket_inputs"]` — it has `metadata` + `CV_inputs`
    keys.  The CV_inputs get normalized (diameter → radius / area) and
    then flattened into a single dict, which is what warnings.py
    expects.
    """
    # Import here so importing preflight itself doesn't pay the cost
    # of importing warnings.py (which pulls in the unsteady physics
    # tree indirectly).
    from src.backend.unsteady.engine.warnings import warn_initialization_limits

    ri = deepcopy(rocket_inputs or {})
    cv_inputs = ri.get("CV_inputs") or {}
    normalize_unsteady_inputs(cv_inputs)

    # Flatten CV_inputs into a single dict (skip the "model" marker key).
    # warn_initialization_limits expects flat rocket_inputs the same way
    # the backend engine builds it after _validate_and_unpack_CVs.
    flat: dict = {}
    for block in cv_inputs.values():
        if not isinstance(block, dict):
            continue
        for k, v in block.items():
            if k != "model":
                flat[k] = v

    warnings: dict = {}
    try:
        warn_initialization_limits(flat, warnings)
    except KeyError as e:
        # A missing required field means the run would crash anyway —
        # surface it as a critical preflight warning so the user sees
        # a modal and can fix inputs before the backend dies with a
        # bare traceback.  `e` stringifies to the missing key name
        # (already quoted by Python).
        warnings["preflight_missing_field"] = {
            "severity": "critical",
            "message": (
                f"Preflight could not complete: required input "
                f"{e} is missing.  The simulation would crash on "
                f"this input — fix it before running."
            ),
            "missing_field": str(e).strip("'\""),
        }
    except Exception as e:
        # Any OTHER unexpected error in the warning code is a bug in
        # warnings.py, not in the user's input.  Report it as an
        # advisory so the user knows preflight didn't fully run, but
        # don't hard-block — they may still want to try.
        warnings["preflight_error"] = {
            "severity": "warning",
            "message": (
                f"Input-range preflight crashed with "
                f"{type(e).__name__}: {e}.  Simulation may still run, "
                f"but inputs were not fully validated."
            ),
        }
    return warnings


def preflight_steady(rocket_inputs: dict) -> dict:
    """Run the steady input-range checks.

    Currently a no-op placeholder: there's no `warn_initialization_limits`
    equivalent on the steady side yet.  Kept as a stub so the UI can
    call it symmetrically with `preflight_unsteady`; when the steady
    warnings module lands, it slots in here.
    """
    ri = deepcopy(rocket_inputs or {})
    normalize_steady_inputs(ri)
    # No steady range checks yet — return empty.
    return {}
