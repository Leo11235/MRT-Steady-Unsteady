"""
Runs NASA-CEA program through a python interface in order to generate a lookup table. Nothing imports this file. 
Documentation:
https://rocketcea.readthedocs.io/

Run it directly to rebuild the table:
python src/backend/unsteady/physics/CEA/NASA_CEA.py
"""

from __future__ import annotations
import json
import time
from pathlib import Path
import numpy as np
from rocketcea.cea_obj import CEA_Obj, add_new_fuel

_STATIC = Path(__file__).resolve().parents[2] / "static_data"
_CEA_FILE = _STATIC / "CEA_table.json"

PA_PER_PSI = 6894.757293168 # conversion value

# define our very own fuel
_EICOSANE_CARD = """
fuel C20H42  C 20 H 42  wt%=100.
h,cal=-249660.0  t(k)=298.15
"""
add_new_fuel("EICOSANE", _EICOSANE_CARD)

DEFAULT_FUEL = "EICOSANE"
DEFAULT_OXIDIZER = "N2O"


class CEAError(RuntimeError):
    """
    CEA could not produce a usable answer for this operating point.
    """


_OBJECTS: dict[tuple[str, str], CEA_Obj] = {}


def _cea_object(oxidizer: str, fuel: str) -> CEA_Obj:
    key = (oxidizer, fuel)
    if key not in _OBJECTS:
        try:
            _OBJECTS[key] = CEA_Obj(oxName=oxidizer, fuelName=fuel)
        except Exception as e:
            raise CEAError(f"Could not initialise CEA for {oxidizer}/{fuel}: {e}") from e
    return _OBJECTS[key]


def run_cea(OF: float, p_C: float,
            fuel: str = DEFAULT_FUEL,
            oxidizer: str = DEFAULT_OXIDIZER
            ) -> tuple[float, float, float, float]:
    """
    returns chamber properties at one operating point (OF, p_C)

    OF   mixture ratio, dimensionless
    p_C  chamber pressure in Pa

    returns (T_c [K], W_c [kg/mol], gamma [-], cstar [m/s])
    raises CEAError if CEA fails or returns something unphysical
    """
    
    OF = float(OF)
    p_psia = float(p_C) / PA_PER_PSI

    cea = _cea_object(oxidizer, fuel)
    try:
        T_rankine = cea.get_Tcomb(Pc=p_psia, MR=OF)
        W_gmol, gamma = cea.get_Chamber_MolWt_gamma(Pc=p_psia, MR=OF)
        cstar_fts = cea.get_Cstar(Pc=p_psia, MR=OF)
    except Exception as e:
        raise CEAError(f"CEA failed at O/F={OF:g}, p_C={p_C:g} Pa ({p_psia:g} psia): {e}") from e

    # convert everything to SI
    T_c = T_rankine / 1.8 # Rankine -> Kelvin
    W_c = W_gmol / 1000.0 # g/mol -> kg/mol
    cstar = cstar_fts * 0.3048 # ft/s -> m/s

    # raise error if CEA returns 0 (indicating that it cannot solve for a certain input)
    # in general, CEA returns 0s rather than raising when it runs into issues
    if not all(np.isfinite(v) for v in (T_c, W_c, gamma, cstar)):
        raise CEAError(f"CEA returned a non-finite value at O/F={OF:g}, p_C={p_C:g} Pa")
    if T_c <= 0.0 or W_c <= 0.0 or gamma <= 0.0 or cstar <= 0.0:
        raise CEAError(f"CEA returned a non-physical result at O/F={OF:g}, p_C={p_C:g} Pa: T_c={T_c:g} K, W_c={W_c:g} kg/mol, gamma={gamma:g}, cstar={cstar:g} m/s. This point is outside what CEA can solve.")

    return (float(T_c), float(W_c), float(gamma), float(cstar))

###########################################################################
# table generation


# currently set as the widest CEA can compute, with reasonably small step intervals
OF_MIN, OF_MAX, OF_STEP = 0.5, 40.0, 0.25
P_MIN_PSIA, P_MAX_PSIA, P_STEP_PSIA = 20.0, 2500.0, 40.0

# inclusive axis, epsilon here to keep endpoints from falling off
def _axis(start: float, stop: float, step: float) -> np.ndarray:
    return np.arange(start, stop + step * 0.5, step)

# build the lookup table and write it as JSON
def generate_CEA_table(output_filepath: Path = _CEA_FILE,
                       fuel: str = DEFAULT_FUEL,
                       oxidizer: str = DEFAULT_OXIDIZER) -> Path:
    
    of_axis = _axis(OF_MIN, OF_MAX, OF_STEP)
    p_axis_psia = _axis(P_MIN_PSIA, P_MAX_PSIA, P_STEP_PSIA)
    p_axis_pa = p_axis_psia * PA_PER_PSI

    total = len(of_axis) * len(p_axis_pa)
    print(f"Generating CEA table")
    print(f"  O/F  {OF_MIN} to {OF_MAX} step {OF_STEP} ({len(of_axis)} points)")
    print(f"  p_C  {P_MIN_PSIA} to {P_MAX_PSIA} psia step {P_STEP_PSIA} ({len(p_axis_psia)} points)")
    print(f"  {total} CEA calls\n")

    grids = {name: np.zeros((len(of_axis), len(p_axis_pa))) for name in ("T_C", "W_C", "gamma", "cstar")}

    started = time.perf_counter()
    failures: list[str] = []

    for i, OF in enumerate(of_axis):
        for j, p_pa in enumerate(p_axis_pa):
            try:
                T_c, W_c, gamma, cstar = run_cea(OF, p_pa, fuel, oxidizer)
            except CEAError as exc:
                # try to carry on
                failures.append(str(exc))
                if i > 0:
                    for name in grids:
                        grids[name][i][j] = grids[name][i - 1][j]
                continue

            grids["T_C"][i][j] = T_c
            grids["W_C"][i][j] = W_c
            grids["gamma"][i][j] = gamma
            grids["cstar"][i][j] = cstar

        done = (i + 1) * len(p_axis_pa)
        elapsed = time.perf_counter() - started
        print(f"{done}/{total}  O/F={OF:.2f} {elapsed:.0f}s elapsed, ~{elapsed / done * (total - done):.0f}s left")

    table = {
        "meta": {
            "oxidizer": oxidizer,
            "fuel": fuel,
            "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "note": ("Grids are indexed [OF][p_C]. Pressures are in PASCALS."),
        },
        "OF_axis": [round(float(v), 6) for v in of_axis],
        "p_C_axis": [round(float(v), 3) for v in p_axis_pa],
        "T_C": [[round(float(v), 4) for v in row] for row in grids["T_C"]],
        "W_C": [[round(float(v), 9) for v in row] for row in grids["W_C"]],
        "gamma": [[round(float(v), 6) for v in row] for row in grids["gamma"]],
        "cstar": [[round(float(v), 4) for v in row] for row in grids["cstar"]],
    }

    output_filepath = Path(output_filepath)
    output_filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(output_filepath, "w", encoding="utf-8") as f:
        json.dump(table, f)

    size_mb = output_filepath.stat().st_size / 1e6
    print(f"\nWrote {output_filepath}  ({size_mb:.2f} MB, {time.perf_counter() - started:.0f}s)")
    if failures:
        print(f"\n{len(failures)} points failed and were filled from the previous O/F row:")
        for message in failures[:10]:
            print(f"  {message}")
        if len(failures) > 10:
            print(f"  ... and {len(failures) - 10} more")
    return output_filepath


if __name__ == "__main__":
    generate_CEA_table()
