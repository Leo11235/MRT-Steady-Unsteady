# MRT Steady-Unsteady Flight Simulator Program Reference

Written for whoever picks this up next. It describes the program as it stands at v1.5, after the units-and-UI refactor.

---

## Table of contents

1. [Overview](#1-overview)
2. [Repository layout](#2-repository-layout)
3. [The unit system](#3-the-unit-system)
4. [Backend: Steady](#4-backend--steady)
5. [Backend: Unsteady](#5-backend--unsteady)
6. [Backend: Common](#6-backend--common)
7. [Plotting](#7-plotting)
8. [UI: Shell and infrastructure](#8-ui--shell-and-infrastructure)
9. [UI: Pages](#9-ui--pages)
10. [UI: Widgets and services](#10-ui--widgets-and-services)
11. [End-to-end pipelines](#11-end-to-end-pipelines)
12. [Testing](#12-testing)
13. [Build and release](#13-build-and-release)
14. [Conventions and gotchas](#14-conventions-and-gotchas)
15. [Appendix: file inventory](#15-appendix--file-inventory)

---

## 1. Overview

**Steady** answers "at a fixed operating point, what does the rocket do?" It
does algebraic hotfire performance, iterative fuel-mass sizing to hit a target
apogee, and parametric sweeps over any combination of seven inputs. Runs in
seconds. No time dimension inside the engine model.

**Unsteady** answers "how does this evolve over time?" A six-control-volume ODE
integration from ignition through burnout, coast, apogee, drogue, main chute and
landing. Tens of seconds to minutes. Phase-switched.

The UI is a customtkinter desktop app wrapping both. It handles presets,
validation, preflight warnings, run monitoring, results browsing, graphing,
export, settings and bug reporting. It never calls physics directly. Everything goes through `src/ui/app/backend_bridge.py`.

Three trees matter at runtime:

- `src/` — code. Read-only.
- `user_data/` — everything belonging to the user: input presets under
  `simulation_configs/`, finished runs under `simulation_results/`, and
  `ui_settings.json`.
- `static_data/` folders — read-only lookup tables: N₂O saturation properties,
  CEA combustion tables, US-1976 atmosphere, the PROPEP table, input schemas
  and default simulation settings.

In a frozen build `user_data/` moves to `%APPDATA%\MRT-Steady-Unsteady\` and is
seeded on first launch from copies bundled inside the exe. `src/` stays
read-only inside the bundle. `backend_bridge.project_root()` and
`backend_bridge.bundled_root()` are the two functions that know the difference;
nothing else should care.

---

## 2. Repository layout

```
build_tools/
├── build.bat                  # the whole build, start to finish
├── build.spec                 # PyInstaller
├── installer.iss              # Inno Setup
├── build/  dist/  output/     # produced, all gitignored
src/
├── backend/
│   ├── common/
│   │   └── preflight.py               # pre-run range checks, UI-facing
│   ├── steady/
│   │   ├── steady_main.py             # run_steady() entry point
│   │   ├── variable_initialization.py # constants + config unpacking
│   │   ├── simulation_engine.py       # hotfire + fuel-mass convergence
│   │   ├── parametric_study.py        # sweep orchestrator
│   │   ├── prop_calculations.py       # thrust, Isp, chamber pressure
│   │   ├── kinematics.py              # 2-DOF flight
│   │   ├── PROPEP/                    # combustion property interpolation
│   │   └── static_data/
│   └── unsteady/
│       ├── engine/
│       │   ├── phase_runner.py        # run_unsteady() entry point + solver
│       │   ├── config.py              # load_unsteady_config()
│       │   ├── objects.py             # StateVector, History, export()
│       │   ├── rhs.py                 # composes the active RHS per phase
│       │   ├── transitions.py         # phase-change events
│       │   ├── registry.py            # phase -> CV function lookup
│       │   ├── variable_initialization.py
│       │   └── warnings.py            # init + runtime warnings
│       ├── physics/
│       │   ├── CVs/                   # CV1_tank .. CV6_trajectory
│       │   ├── N2O_properties/
│       │   ├── CEA/
│       │   └── atmosphere/
│       └── static_data/
├── common/                            # shared by backend AND UI
│   ├── variable_conversions.py        # the unit registry
│   ├── default_inputs.py              # loader for the file below
│   ├── static_data/
│   │   └── default_inputs.jsonc       # physical defaults, with sources
│   └── plotting/
│       ├── unsteady_plots.py          # 28-figure registry + PDF/PNG export
│       ├── steady_plots.py            # 3-figure registry
│       └── parametric_plots.py        # 2D/3D sweep figures
└── ui/
    ├── main.py                        # entry point
    ├── assets/                        # MRT logo (PNG + ICO)
    └── app/
        ├── shell.py                   # top bar, page stack, shortcuts
        ├── theme.py                   # colours, sizes, padding
        ├── settings.py                # user settings load/save
        ├── version.py                 # reads the VERSION file
        ├── backend_bridge.py          # ONLY module allowed to touch backend
        ├── field_registry.py          # label/help/unit/default per input key
        ├── pages/                     # one file per page
        ├── widgets/                   # reusable components
        └── services/                  # shortcuts, presets, OS, bug transport
user_data/
├── default_ui_settings.json           # tracked; the reset-to-defaults source
├── ui_settings.json                   # gitignored; the live settings
├── simulation_configs/{steady,unsteady}/
└── simulation_results/{steady,unsteady}/
tests/
├── backend_tests.py                   # run_backend_tests()
├── backend_tests_helpers.py           # the check registry
├── steady_configs/  unsteady_configs/ # automated
├── ui_configs/                        # manual, drives UI failure paths
└── UI bug checklist.txt
VERSION                                # one line, e.g. "1.5"
```

Two rules about this layout:

- `src/common/` is the only place backend and UI are both allowed to import
  from. Backend never imports from `src/ui/`; UI never imports from
  `src/backend/` except through `backend_bridge`.
- Anything shared that isn't obviously backend or UI (units, plots, physical
  defaults) belongs in `src/common/`.

---

## 3. The unit system

### 3.1 The rule

**Every physical value in a config file is a `[value, unit]` pair.**

```jsonc
"chamber_pressure": [3447000, "Pa"],
"launch_angle":     [6, "deg"],
"drag_coefficient": [0.641606, "."],
```

The unit travels with the value from the config file, through the UI form, into the bridge, and is stripped to SI on the way into the physics.

Dimensionless quantities use `"."`. Unused alternates (the "one or the other" fields) use `null` for the value and keep their unit:
`"tank_internal_length": [null, "m"]`. Model selectors and type strings
(`"model"`, `"liquid_oxidizer_type"`) are plain strings, not pairs.

### 3.2 `src/common/variable_conversions.py`

The single source of truth. 16 categories, 72 units, 103 aliases.

Categories: length, area, volume, mass, density, pressure, temperature, time,
angle, velocity, acceleration, force, impulse, mass flow, molar mass,
dimensionless.

Public API:

| Function | Does |
|---|---|
| `to_SI(value, unit)` / `from_SI(value, unit)` | scalar conversion |
| `convert(value, from_unit, to_unit)` | between any two same-category units |
| `pair_to_SI(pair)` | `[6, "deg"] -> 0.1047` |
| `pair_from_SI(value, unit)` | the inverse, returns a pair |
| `block_to_SI(block, skip=("model",))` | whole dict of pairs at once |
| `category_of(unit)`, `units_in_category(cat)`, `is_known_unit(unit)` | registry queries |
| `unit_for_system(category, system)` | display unit for SI / IMP / MRT |

Temperature has its own pair of functions because it's affine, not
multiplicative.

`UNIT_SYSTEMS` (the display systems) sets `"angle": "deg"` in **all three**
systems, SI included. `SI_UNITS` still says `rad`, because that's what the
physics wants. Nobody reads a launch angle in radians.

### 3.3 Hardware lengths vs mission distances

`length` and `distance` are separate DISPLAY categories over the same unit
table. A fuel grain is 15 cm / 6 in; an apogee is 13716 m / 45000 ft. Showing
a grain diameter in feet or an apogee in centimetres is useless both ways, and
no unit string can tell them apart — "m" is "m". So the distinction lives on
`FieldSpec.category`, and `kv_row.category_of_key()` is how results-page code
asks for it rather than inferring from the unit. Conversions are identical;
only the default display unit differs.

For INPUTS the split comes from `FieldSpec.category`: `distance` covers
`target_apogee`, both launch-site altitudes and the main-deploy altitude.

For OUTPUTS there's no registry entry, so `kv_row.category_of_key()` decides
from the name: a length-dimensioned key mentioning apogee, altitude,
downrange, range, distance, asl or agl is a `distance`; anything else
length-dimensioned is hardware. Matched rather than enumerated because
unsteady emits dozens of these (`apogee_m_asl`, `apogee_m_agl`,
`max_altitude_m`, …) and a fixed list would go stale the first time someone
adds an output.

### 3.4 Ambiguities, resolved once

- `"g"` is grams. Gravitational acceleration is `"g0"`.
- `"kn"` is knots. Kilonewtons are `"kN"`. Case matters.
- `"ms"` is milliseconds. Velocity is `"m/s"`.

### 3.4b Results files are not always SI

`steady_main` rewrites every dict in the export — inputs, parameters, flight
data, settings — into MRT units when `simulation_settings.output_units` is
`"MRT"`. So an MRT run's file holds feet, inches and psi, and a 45000 ft
target apogee is stored as the number `45000`.

Anything reading a results file therefore needs two systems, not one: the one
the numbers are IN and the one to show them in.
`kv_row.native_system_of(results)` gives the first (only `"MRT"` triggers the
rewrite; `"IMP"` falls through and stays SI), and `ResultsPage.native_system`
carries it to every row.

`vc.storage_unit(category, system)` is the file-side lookup and
`vc.unit_for_system(category, system)` the display-side one. **They differ for
SI**: a file holds metres, while the SI display shows hardware lengths in
centimetres. Confusing the two makes a 0.6096 m fuel grain read as 0.6096 cm.

### 3.5 Where the conversion happens

Exactly once, at the boundary:

- **Into the physics:** `preflight._to_physics_values()` and the backend's own
  config loaders call `block_to_SI()`, then convert diameters to radii.
- **Out of the physics:** results are written in SI, and the results pages
  convert for display only.

The single biggest class of bug in this program's history is converting twice.
If you find yourself writing `np.radians(...)` on a value that came out of
`to_SI`, stop.

### 3.6 Diameters in, radii inside

The user always types a diameter. Physics always uses a radius. The halving
happens in the same place as the SI conversion and nowhere else.
`field_registry.steady_schema_keys()` does the corresponding key translation so
the UI can show `fuel_external_diameter` for a schema that says
`fuel_external_radius`.

### 3.7 `src/common/static_data/default_inputs.jsonc`

Physical defaults with a documented source for each, loaded by
`src/common/default_inputs.py`. Fuel grain density 900 kg/m³, regression
`a = 0.000132`, `n = 0.555`, N₂O and paraffin. The UI reads defaults from here
rather than hard-coding them in a page, so changing a default is a one-line
edit in a file a non-programmer can read.

---

## 4. Backend — Steady

### 4.1 Three simulation types

Set by `simulation_settings.simulation_type`:

- `hotfire` — one operating point, straight through the algebra.
- `fuel_mass_convergence` — iterate fuel mass until the predicted apogee lands
  within tolerance of `target_apogee`.
- `parametric_study` — sweep combinations of inputs and record the outputs.

### 4.2 Config shape

Top level: `metadata`, `simulation_settings`, `rocket_inputs`, and for sweeps
`parametric_study_inputs`.

`rocket_inputs` splits three ways:

- **base** — needed by everything: oxidizer mass flow, chamber pressure, fuel
  geometry, grain density, regression coefficients, propellant types.
- **kinematics** — needed by convergence and sweeps: target apogee, launch site
  altitude, dry mass, rocket diameter, drag coefficient, launch angle.
- **hotfire** — exactly one of `fuel_mass` or
  `initial_internal_fuel_diameter`. The other is `[null, unit]`.

`output_units` in `simulation_settings` picks the unit system the written JSON
uses. Test configs use `"SI"` so the checks can compare against fixed numbers.

### 4.3 Flow

`steady_main.run_steady()` -> `variable_initialization` unpacks and converts ->
`simulation_engine` runs the chosen loop -> `prop_calculations` supplies thrust,
Isp and chamber conditions (via PROPEP interpolation) -> `kinematics` flies the
2-DOF trajectory -> results written to
`user_data/simulation_results/steady/<name>.json`.

Sweeps go through `parametric_study.py`, which drives the same engine once per
combination and collects the results into a grid.

---

## 5. Backend — Unsteady

### 5.1 The six control volumes

| CV | Models available |
|---|---|
| CV1 tank | `saturated_equilibrium` |
| CV2 valve | `instant`, `linear`, `sigmoid` |
| CV3 injector | `SPI` |
| CV4 chamber | `0D_quasi_steady` |
| CV5 nozzle | `1D_frozen` |
| CV6 trajectory | `2dof` |

Each CV block in the config carries a `"model"` string plus that model's
inputs. The UI shows only the fields the selected model actually uses:
`instant` shows none, `linear` shows the time constant, `sigmoid` shows the
half-time and steepness.

The NHNE injector model was removed in 1.5. It was listed but never
implemented, and the "two-phase multiplier" input went with it.

### 5.2 Phase state machine

`phase_runner.py` steps the solver phase by phase. `transitions.py` holds the
event functions that end each phase; `registry.py` maps a phase to the set of
CV functions active during it; `rhs.py` composes those into the derivative
function scipy integrates.

Phases run 1 through 6, with 4a/4b/4c sub-phases. The backend prints
`--- PHASE_2 ---` style headings, which the loading screen parses to show
progress — note the uppercase, the UI's regex is case-insensitive for exactly
this reason.

### 5.3 Solver and stalls

scipy's LSODA. When the step size collapses without the phase ending, the
runner raises `SolverStalledError` rather than spinning forever. The UI turns
that into a readable hint.

LSODA holds non-reentrant module state, which is why cancelling a run has to
kill the thread outright (see §8.4) rather than politely asking it to stop.

### 5.4 Warnings

`engine/warnings.py` has two halves. `warn_initialization_limits()` checks the
inputs before anything integrates: ullage fraction bounds, fuel grain length,
port radius, geometric possibility, regression coefficients. Runtime warnings
accumulate during the integration. Each entry has a severity of `critical`,
`warning` or `advisory` and a message.

The same function backs the UI's preflight modal, which is the whole point: the
user sees the identical text before spending two minutes on a run that was
never going to work.

### 5.5 Output

`objects.export()` writes `user_data/simulation_results/unsteady/<name>/
sim_data.json`, optionally with `graphs.pdf` and a `graphs/` folder of PNGs.
The JSON carries `static` (inputs as the physics saw them), `performance`
(overall and per-phase), `event_log`, `warnings` and the full time series.

---

## 6. Backend — Common

### `src/backend/common/preflight.py`

160 lines, and the only backend module the UI calls for something other than
running a simulation.

`preflight_unsteady(rocket_inputs)` and `preflight_steady(rocket_inputs)` deep
-copy the inputs, run `_to_physics_values()` (pairs to SI, diameters to radii),
and hand the result to `warn_initialization_limits`. A `KeyError` becomes a
`preflight_missing_field` critical rather than a traceback, because a missing
field at this stage means the validator let something through and the user
still deserves a sentence they can act on.

There is no steady equivalent of the unsteady limit checks yet;
`preflight_steady` exists so the UI has one shape to code against.

---

## 7. Plotting

All three registries live in `src/common/plotting/` and follow the same
pattern:

```python
PlotSpec(name, label, group, builder)     # builder: (results) -> Figure | None
plot_specs(group=None) -> list[PlotSpec]
plot_groups() -> list[str]
build_figure(name, results) -> Figure | None
```

A builder returns `None` when the run doesn't contain the series it needs. One
broken plot costs only itself; the caller reports it as skipped and carries on.

Every registry also exposes `label_of(name)`, which the UI uses as a graph
window's title.

- **`unsteady_plots.py`** — 28 figures in six groups (Summary 2, Time series 5,
  Burn 12, Relations 3, Diagnostics 4, Geometry 2). Also holds
  `unsteady_results()`, which writes the PDF and PNGs. Its signature dropped
  from 30 keyword arguments to 8 in 1.5.
- **`steady_plots.py`** — `kinematics`, `thrust`, `forces`.
  `DEFAULT_SELECTION = ("kinematics", "thrust")`.
- **`parametric_plots.py`** — `plot_parametric_2d()` and
  `plot_parametric_3d()`, plus `swept_variables()` and
  `available_output_variables()` so the dialog can populate itself. Both
  plotters accept `holds` (fix the sweep variables not on an axis), axis labels
  and transforms.

The same builders draw the graph windows and the figures in `graphs.pdf`.
That's deliberate: they cannot drift.

**Matplotlib is pinned to `Agg`, in `src/common/plotting/__init__.py`.** A
package's `__init__` runs before any of its submodules, so the pin is
guaranteed to land before the first `import matplotlib.pyplot`. Without it
matplotlib picks TkAgg whenever tkinter is importable, and TkAgg creates Tk
objects — which, on the worker thread, gives you a console full of
`RuntimeError: main thread is not in main loop` from `__del__`.

Display still works: `widgets/figure_window.py` drives `FigureCanvasTkAgg`
itself, on the main thread, and that path never consults the global backend
setting. The registries build Figures and do not show them; the caller owns
display.

---

## 8. UI — Shell and infrastructure

### 8.1 Entry point

```
python -m src.ui.main          # from the project root
python src/ui/main.py          # also works; main.py fixes sys.path itself
```

### 8.2 `shell.py` — `AppShell`

A `CTk` window with a persistent top bar and a stack of lazily built pages.

`PAGES` maps a key to a `PageRef(module, class_name)`. Adding a page is one row
in that dict. `_ensure_page(name)` imports and builds on first use;
`go(name)` navigates.

Use `_ensure_page`, not `pages.get`, anywhere you need a page that may not have
been visited yet. `pages.get` returns `None` for an unbuilt page, which is how
the "results page comes up blank after a run" bug happened.

`_NO_HOME = ("main", "loading", "settings")` — those three suppress the Home
button. Loading has Cancel and Halt & report instead; settings owns its own
Save/Cancel.

Public surface other modules rely on: `go`, `_ensure_page`,
`start_loading_run`, `refresh_shortcuts`, `refresh_appearance`.

### 8.3 `backend_bridge.py`

The only module allowed to import from `src/backend/`. 493 lines.

- **Roots:** `project_root()` (writable), `bundled_root()` (read-only),
  and the per-kind `*_presets_dir()` / `*_results_dir()` helpers.
- **Files:** `load_jsonc`, `save_jsonc`, `list_presets`.
- **Seeding:** `_seed_writable_root`, gated on `SEED_STAMP`. The shipped
  examples are templates, not user documents; seeding them only when absent
  meant an upgraded install kept examples from whatever version first ran, and
  a config written against an old schema outlived the build that understood
  it. Bump `SEED_STAMP` whenever the example configs change shape. Anything
  overwritten is kept as `.jsonc.bak`.
- **Validation:** `validate_steady_config`, `validate_unsteady_config`,
  `check_alternate_fields`, `_is_filled`.
- **Preflight:** `preflight_steady`, `preflight_unsteady`, `worst_severity`.
- **Running:** `run_steady(config)`, `run_unsteady(config)`. Each writes the
  config to a scratch directory, runs from there, and deletes it afterwards.
  **Neither ever receives the loaded preset's path.** An earlier version passed
  it through, which meant the backend read the FILE rather than the form —
  switching a loaded preset to hotfire and clicking Run gave you a convergence
  — and running a preset silently rewrote it. Saving is a deliberate act;
  running is not one.
- **Runs:** `list_runs`, `run_json_path`, `run_display_name`, `run_timestamp`,
  `load_run`.

`UNSTEADY_ALTERNATES` declares the "one or the other" pairs:
`CV1_tank` has `(tank_ullage_fraction, tank_internal_length)`, `CV4_chamber`
has `(chamber_fuel_mass, chamber_fuel_internal_diameter)`.

`_is_filled()` exists because with `[null, "m"]` always present in the file,
checking for key presence always picked the first alternate. Filled means the
value is not `None`. Zero counts as filled.

The old `_reconcile_backend_output` is gone. Both runners now take
`output_dir_filepath` and return where they wrote, so there is nothing to
reconcile.

### 8.4 Threading

Runs happen on a worker thread. The worker never touches Tk and never calls
`self.after()`; it pushes onto a queue that the main thread drains. Figures are
built on the main thread because matplotlib requires it.

Cancellation raises `SystemExit` in the worker via
`ctypes.pythonapi.PyThreadState_SetAsyncExc`. Blunt, but LSODA's module state
isn't reentrant and there's no clean cooperative exit point inside a scipy
integration.

### 8.5 `field_registry.py`

56 `FieldSpec` entries, one per input key:

```python
FieldSpec(key, label, category, help, value_type, choices)
```

with `unit_for(system)`, `default` (read from `default_inputs.jsonc`),
`unit_options` (every unit in the field's category) and `is_numeric`.

Also holds `MODEL_LABELS`, `MODEL_DESCRIPTIONS` and the `model_label()` /
`model_wire()` translation, so the UI shows "Sigmoid" and the config gets
`"sigmoid"`.

**The division of labour:** the backend's `input_schema.jsonc` decides *which*
fields a config needs. The field registry decides *how* each one is shown.
`check_registry_covers_schema()` fails loudly if the two drift apart, and
`unsteady_schema_keys()` / `steady_schema_keys()` are how a page asks the
schema what to build.

`_read_jsonc()` strips comments and trailing commas, because hand-edited JSONC
grows trailing commas.

### 8.6 `settings.py` and `theme.py`

`settings.py` reads `user_data/ui_settings.json`, falling back to
`default_ui_settings.json`. Keys starting with `_` are comments and are
stripped on load, which is how the defaults file documents itself. Three
settings: `default_program_units`, `default_auto_save_inputs`, `shortcuts`.

`_RENAMED` handles keys that changed name between versions — the user's value
is migrated before the defaults are merged in, otherwise the renamed value
would lose to the default rather than replacing it.

**Pages are built once and cached, so a preference change has to be pulled in
on `on_show`.** `input_page._sync_from_settings()` resets auto-save every time
and moves the units only when the preference actually changed, so a preset's
own units survive ordinary navigation. `results_page` does the same against
its toolbar buttons.

`theme.py` is the whole visual vocabulary: `PAD_XS` through `PAD_XL`,
`SIZE_SMALL` through `SIZE_HERO`, the MRT reds, the slate accent, the
severity colours. Never hard-code a colour or a pixel gap in a page.

---

## 9. UI — Pages

### 9.1 `main_menu.py`

Logo, Steady and Unsteady as the two large buttons, then Browse saved results,
Report a bug and Settings, then a version chip that opens the patch notes.

### 9.2 `input_page.py` — the shared base

590 lines, subclassed by `steady_page` and `unsteady_page`. Layout: a
`CTkTabview` on the left, a fixed action sidebar on the right (Load preset…,
Save preset…, Run simulation, and the auto-save toggle), a status line along
the bottom.

This layout was designed around how the team actually uses the tool. Don't
replace the tabs with collapsible sections.

Subclass contract:

| Method | For |
|---|---|
| `_build_tabs()` | create tabs and fields |
| `_after_build()` | anything that needs the build order captured first |
| `to_config()` / `from_config()` | form <-> config dict |
| `_validate()` / `_preflight()` | delegate to the bridge |
| `_presets_dir()` / `_default_run_name()` | where presets live |

Helpers a subclass uses: `add_tab`, `add_field`, `add_note`,
`add_section_title`, `add_divider`, `add_advanced_header` (the 🔒/🔓 padlock
section), `add_advanced_field`, `set_packed`.

**Order-preserving visibility.** Tk's `pack()` appends to the end, so calling
`pack_forget()` then `pack()` moves a widget to the bottom of its parent.
`_capture_build_order()` records the creation order once, and `set_packed()`
re-inserts a widget where it belongs. Which is why `_after_build()` exists:
`_refresh_all_models()` used to run inside `_build_tabs`, before the order was
captured, and hiding silently did nothing.

`_highlight_errors()` matches on word boundaries and scopes by section prefix.
Three different CVs have a field whose label ends in "drag coefficient"; a
naive substring match rings all three.

`_on_run_complete` uses `shell._ensure_page(target)`.

### 9.3 `steady_page.py`

Three tabs: Sim Settings, Oxidizer & Fuel, Rocket Body. The parametric study
sub-panel lives on Sim Settings and appears when the simulation type is
`parametric_study`.

It also overrides `_review_result()`, the base class's seam between a finished
run and the results page. A convergence run that never reached its target
still *succeeds* — it returns a complete result — so nothing else flags it and
the results page looks converged until you read the apogee.
`widgets/apogee_dialog.show_apogee_shortfall()` says so first and offers Back
to inputs or See results anyway. The run is saved either way.

### 9.4 `unsteady_page.py`

Seven tabs: Sim settings plus one per control volume.

### 9.5 `loading_screen.py`

Terminal mirror, phase-aware progress bar, Cancel and Halt & report — both
two-click, both reverting if the second click doesn't land within three
seconds.

`_StreamToQueue` tees the worker's stdout into the terminal box.
`_friendly_hint()` turns a `KeyError` or a `SolverStalledError` into a sentence
about what to change. `_kill_thread()` does the `PyThreadState_SetAsyncExc`
work from §8.4.

Cancel returns to `_last_input_page`, which is never cleared. The earlier
version cleared `_pre_loading_page` after use and fell back to `"main"`, which
triggered `reset_to_defaults()` and wiped the form.

### 9.6 `results_page.py` — the shared base

Tabs on the left, a sidebar with the SI / IMP / MRT toggle, search, copy,
export CSV and show-in-folder.

**Graphs are not a tab.** The sidebar button opens each selected figure in its
own resizable window with the standard matplotlib toolbar, so you can put a
graph beside the numbers it came from or drag it to a second monitor. See
`widgets/figure_window.py`; leaving a results page closes the windows.

The three unit buttons together occupy exactly the width of the buttons above
them: `gaps = theme.PAD_XS * 2; cell_w = (_ACTION_W - gaps) // 3`, inside a
frame with `pack_propagate(False)`.

Helpers: `add_row` (a `KVRow`, which knows its own unit and re-renders on a
system change), `add_dynamic_label(widget, build_text)` for labels that need
conversion but aren't key/value rows, `add_dict`, `add_heading`, `add_empty`,
`clear_graphs`, `embed_figures`, `report_render`.

### 9.7 `steady_results.py`

Four tabs, but only the applicable ones are shown: a parametric study hides
Performance and Trajectory (it produces one of each per point, not one
overall), everything else hides Parametric sweep. `ResultsPage.set_tab_visible`
does this by adding and removing the SEGMENTED BUTTON entry, not the tab —
`CTkTabview.delete` destroys the frame and everything rendered into it.

Sweep points carry a red header and "Did not reach target apogee" when the
engine's `target_apogee_reached` flag is False, readable with the point still
collapsed. That flag is separate from `reached_apogee`, which is the altitude
actually achieved in metres and is what the test configs check numerically. `_sync_graphs_button()` picks the button's
behaviour from the run type: a parametric study gives "Parametric graphs…", a
convergence run gives "Show graphs…", and a hotfire gives a *disabled* "Show
graphs…" with a tooltip explaining that one operating point has no time series
to plot. Greyed rather than hidden, so it reads as a gap rather than a feature
you failed to find.

### 9.8 `unsteady_results.py`

Five tabs: Overall, Per phase, Inputs, Events, Warnings. Warnings sort
critical, then warning, then advisory. Graphs are chosen from the searchable
picker and open as windows.

### 9.9 `results_browser.py`

Every saved run, newest first, old-layout (`<name>.json`) and new-layout
(`<name>/sim_data.json`) interleaved. Open, Rename, Delete, Show in folder.
Delete removes the whole run directory including PDFs and PNGs. Rename uses
`ask_text` from `widgets/text_prompt.py`.

### 9.10 `settings_page.py`

Unit system, run behaviour, keyboard shortcuts. Edits are held in the form
until Save, so Cancel discards. Save calls the shell's `refresh_shortcuts()`.
Rebinding onto a combination another action already owns is refused with a
message naming that action.

No language section (French was dropped in 1.5) and no appearance section: the
app is dark-only, and every colour in `theme.py` is tuned against that
background. `shell.refresh_appearance()` survives as the one call site to
change if that ever comes back.

### 9.11 `bug_report.py`

Name, email, title, description, an auto-collected environment block, and a
read-only diagnostics box that only appears when there's something in it.
`prefill(title, diagnostics, config_json)` is what the shell's Halt & report
and the error popup call. On send, diagnostics and config are capped by
`cap_field` (last 1000 lines / 20 KB, trimmed from the front — the tail of a
log is where the failure is).

**Every report is written to `user_data/bug_reports/` before it's sent.**
Web3Forms answering `success` means it accepted the submission, not that mail
reached the inbox; their spam filtering sits in between, and a desktop app
posting with no Origin header is exactly what that filter is built to catch.
The page shows the server's own message verbatim rather than claiming
delivery, and offers the reports folder alongside the clipboard fallback.

### 9.12 `patchnotes.py`

One card per release, newest first. `PATCHNOTES` is a plain list of dicts at
the top of the file; prepend to it when you cut a release, and keep the top
entry's version equal to the `VERSION` file.

---

## 10. UI — Widgets and services

### Widgets (`src/ui/app/widgets/`)

| File | What it is |
|---|---|
| `form_field.py` | `LabeledField` — label, entry, unit dropdown, help icon. `to_pair()`, `from_pair()`, `get_si()`, `mark_invalid()`, `set_locked()` |
| `kv_row.py` | one key/value row on a results page; re-renders on a unit-system change |
| `section.py` | titled group box |
| `parametric_list.py` | the sweep editor: one card per parameter, "+ Add parameter" glued under the last card |
| `parametric_graph_dialog.py` | axis pickers, hold pickers, 2D/3D |
| `graph_picker.py` | multi-select over a plot registry; clamps itself to the screen |
| `figure_window.py` | one figure per window, with the matplotlib toolbar |
| `filter_combo.py` | entry plus a focusless suggestion list; prefix matching |
| `preflight_dialog.py` | the warnings modal, worst first, Cancel or Run anyway |
| `apogee_dialog.py` | convergence fell short: back to inputs, or see results |
| `error_popup.py` | scrollable exception text with Back and Report a bug always visible |
| `text_prompt.py` | `ask_text(...)`, replaces `simpledialog` |
| `key_capture.py` | `capture_key(...)` for the shortcut rebind |
| `confirm_button.py` | the two-click Cancel / Halt pattern |
| `loading_bar.py` | phase-aware progress |
| `tooltip.py` | hover text that stays inside the window and beside its widget |
| `search_entry.py`, `help_icon.py`, `recent_preset_menu.py`, `placeholder.py` | small shared pieces |

`LabeledField` keeps `_si_cache`, the exact SI value behind the displayed
number. Without it, switching mm -> in -> mm turns 32 into 31.9999 and then
keeps drifting.

### Services (`src/ui/app/services/`)

| File | What it is |
|---|---|
| `shortcuts.py` | `ACTIONS`, `DEFAULT_BINDINGS`, `ACTION_LABELS`, `load_bindings`, `save_bindings`, `humanize`, `parse_event`, `ShortcutRouter` |
| `recent_presets.py` | MRU list behind the preset menu |
| `os_utils.py` | reveal-in-file-manager, per platform |
| `bug_report_client.py` | Web3Forms transport. `submit_bug_report`, `cap_field`, `collect_environment`, `friendly_network_error_hint`, `is_configured` |

Default bindings: Run `Ctrl+R`, Save preset `Ctrl+S`, Load preset `Ctrl+O`,
Cancel `Esc` (double-press). Cancel is handled centrally by the shell; the
other three are dispatched to whichever page implements `handle_shortcut`.

---

## 11. End-to-end pipelines

### 11.1 Run

1. User clicks Run (or presses Ctrl+R).
2. `input_page._on_run()` calls `to_config()` — every `LabeledField` becomes a
   `[value, unit]` pair. Still in the user's units.
3. `_validate()` -> `backend_bridge.validate_*_config()`. Missing fields, bad
   types, and the alternate-pair rules. Failures raise a popup and
   `_highlight_errors()` rings the offending fields.
4. `_preflight()` -> `backend_bridge.preflight_*` -> `backend/common/preflight`
   -> `warn_initialization_limits`. Anything returned opens the preflight
   modal. Cancel goes back to the form with everything intact; Run anyway
   continues.
5. Auto-save, if enabled, writes the config to a preset.
6. `shell.start_loading_run()` switches to the loading screen and starts the
   worker thread.
7. The worker calls `backend_bridge.run_steady/run_unsteady`, which converts to
   SI, halves diameters and calls into the physics. Its stdout is teed into the
   terminal box.
8. On success the bridge returns the written path. `_on_run_complete` first
   calls `_review_result()`, the hook that lets a page refuse to navigate —
   steady uses it to warn about a convergence run that fell short. If that
   passes, it does `shell._ensure_page(target)`, hands the results over and
   navigates.
9. On failure `_on_run_error` opens the error popup, which can prefill the bug
   page with the traceback, terminal output and config.

### 11.2 Load preset

`list_presets(kind)` -> file dialog or recent menu -> `load_jsonc` ->
`from_config()`, which walks the form and calls `from_pair()` on each field.
A pair whose unit isn't in the registry fails here with a message naming the
unit, not with a `KeyError`.

### 11.3 Save preset

`to_config()` -> name prompt (`ask_text`) or the auto-save name ->
`save_jsonc` into the right presets directory -> the MRU list updates.

### 11.4 Open a saved run

`list_runs(kind)` walks the results directory and handles both layouts.
`run_json_path` resolves to the JSON either way, `run_display_name` and
`run_timestamp` feed the browser rows, `load_run` reads it, and the results
page renders in whatever unit system Settings starts it in.

---

## 12. Testing

### 12.1 Backend tests

```python
from tests.backend_tests import run_backend_tests
run_backend_tests(all_steady_tests=True, all_unsteady_tests=True)
```

Also accepts `only=`, `keep_results=` and `timeout=`. The runner is
deliberately thin; everything real lives in `backend_tests_helpers.py`.

A test config is an ordinary config with a `metadata.expected_output` and a
`metadata.checks` block. Nine check types:

`files_exist`, `json_path_exists`, `value_within`, `value_between`,
`list_length`, `warnings_equal`, `reaches_phases`, `no_nans_in`, `custom`.

Supporting machinery: `run_with_timeout` (kills a hung run the same way the UI
cancels one), `TestContext`, `classify_exception`, and rich console output.

Configs live in `tests/steady_configs/` and `tests/unsteady_configs/` and use
`output_units: "SI"` so checks can compare against fixed numbers.

### 12.2 UI tests

Not automated. `tests/ui_configs/` holds nine configs that each drive one
failure path — missing field, both alternates filled, neither filled, unknown
unit, preflight warnings, preflight criticals, instant valve. Each file starts
with a comment saying what should happen when you load it and hit Run.

`tests/UI bug checklist.txt` is the manual walkthrough, including a section for
the frozen build that source-mode testing can't cover.

---

## 13. Build and release

Everything lives in `build_tools/` and everything it produces stays there.

```
build_tools\build.bat
```

Step 1 runs PyInstaller with `--distpath build_tools\dist` and
`--workpath build_tools\build` over `build_tools\build.spec`. Step 2 runs Inno
Setup over `build_tools\installer.iss`, producing
`build_tools\output\MRT-Steady-Unsteady-Setup.exe`.

`build.spec` resolves the project root from `SPECPATH`, not from the working
directory, so it doesn't matter where you invoke it from. It bundles:

- CustomTkinter themes, and CoolProp / rocketcea / pypropep via `collect_all`
  (each ships binary data PyInstaller's analysis misses).
- All three `static_data` trees, **including `src/common/static_data`** — that
  one is new in 1.5 and holds `default_inputs.jsonc`. Forget it and the
  Advanced propellant fields come up blank in the exe.
- The PROPEP data directory, the UI assets, the three example configs and
  `default_ui_settings.json` (the first-launch seed), and the `VERSION` file at
  the bundle root.
- **Every module under `src/`, listed explicitly in `hiddenimports`.** The
  shell imports pages by string name, which PyInstaller's static analysis can't
  follow, so without this the exe opens on the "Not built yet" placeholder and
  nothing else works.

To cut a release: edit `VERSION`, add a `PATCHNOTES` entry with the same
version string, walk the UI bug checklist, then run `build.bat`. The installer,
the Python UI and the Windows Add/Remove entry all read `VERSION`, so they
can't drift.

The installer is a per-user install with no admin prompt, detects and removes
an older version before installing, and deliberately leaves
`%APPDATA%\MRT-Steady-Unsteady\` alone on uninstall so presets and past runs
survive.

---

## 14. Conventions and gotchas

**Units.** Convert once, at the boundary. If a value came out of `to_SI`, it is
already SI.

**Diameters in, radii inside.** The halving lives with the SI conversion.

**`_is_filled`, not key presence.** `[null, "m"]` is always in the file.

**Tk pack order.** `pack_forget()` + `pack()` moves a widget to the end. Use
`set_packed`.

**`_ensure_page`, not `pages.get`.** Pages are built lazily.

**A results file's numbers may not be SI.** Read
`simulation_settings.output_units` before converting anything out of one, and
use `vc.storage_unit()` for the source unit rather than `unit_for_system()`.

**A run never writes to a preset.** The bridge always uses a scratch file.
Auto-save creates a new timestamped preset; it does not overwrite the one you
opened.

**Never call `self.after()` from a worker thread.** Push to the queue.

**Don't mix `winfo_screenwidth()` with `winfo_rootx()`.** Under Windows
display scaling they aren't in the same coordinate space, so "clamp to the
screen" arithmetic lands somewhere unrelated. `tooltip._bounds()` measures the
app window through the widget tree instead, so both numbers agree.

**A Tk menu grabs the keyboard when it posts.** That's why `filter_combo`
builds its own borderless Toplevel instead of using CTkComboBox: refreshing a
posted menu on each keystroke stole focus from the entry and ate the next
character.

**CTkToplevel schedules its own lift a few hundred ms after construction.**
Opening several at once means the last one's callback lands after yours, so a
plain `lift()` loses. `figure_window._raise_all` pulses `-topmost` instead.

**Build figures on the main thread where you can, and never let matplotlib
pick its own backend.** `src/common/plotting/__init__.py` pins Agg for exactly
this reason.

**Tk objects freed on a worker thread print `main thread is not in main loop`
from `__del__`.** It's noise, not a crash, but it looks alarming.
`shell.start_loading_run` calls `gc.collect()` on the main thread before
starting the worker so there's nothing left to trip over.

**`importlib.import_module` is invisible to PyInstaller.** `shell.PAGES` names
its modules as strings, so `build.spec` walks `src/` and lists every module in
`hiddenimports`. Miss that and every page in the exe is the "Not built yet"
placeholder.

**Backend prints uppercase phase headings.** `--- PHASE_2 ---`. The parsing
regex is case-insensitive on purpose.

**Construction order in dialogs.** In `parametric_graph_dialog`, the
`_label_to_wire` map must exist before `_HoldPicker` is constructed, because
the picker refreshes on construction and calls `axis_wires()`.

**Three CVs have a "drag coefficient".** Scope your label matching.

**PEP 701 f-strings.** Three backend files use nested same-type quotes inside
f-strings, which needs Python 3.12+. The project targets 3.13. If a tool
reports a syntax error in `warnings.py`, check the tool's Python version before
believing it.

**`theme.py` for every colour and gap.** No literals in pages.

**Pages are cached, so anything read from settings at build time goes stale.**
Read it in `on_show` instead.

**A bug that only appears in the exe is usually about bundled files or
`%APPDATA%` seeding.** Source mode reads the checkout directly, so it can't
reproduce a stale seeded copy.

---

## 15. Appendix — file inventory

Line counts as of v1.5, data tables excluded.

### Backend

| File | Lines |
|---|---|
| `backend/common/preflight.py` | 160 |
| `backend/steady/steady_main.py` | 157 |
| `backend/steady/variable_initialization.py` | 165 |
| `backend/steady/simulation_engine.py` | 76 |
| `backend/steady/parametric_study.py` | 62 |
| `backend/steady/prop_calculations.py` | 248 |
| `backend/steady/kinematics.py` | 74 |
| `backend/steady/PROPEP/` (3 files) | 298 |
| `backend/unsteady/engine/phase_runner.py` | 264 |
| `backend/unsteady/engine/objects.py` | 325 |
| `backend/unsteady/engine/transitions.py` | 277 |
| `backend/unsteady/engine/rhs.py` | 231 |
| `backend/unsteady/engine/warnings.py` | 230 |
| `backend/unsteady/engine/config.py` | 167 |
| `backend/unsteady/engine/variable_initialization.py` | 138 |
| `backend/unsteady/engine/registry.py` | 97 |
| `backend/unsteady/physics/CVs/` (6 files) | 809 |
| `backend/unsteady/physics/CEA/` (3 files) | 431 |
| `backend/unsteady/physics/N2O_properties/` | 198 |
| `backend/unsteady/physics/atmosphere/` | 40 |

### Common

| File | Lines |
|---|---|
| `common/variable_conversions.py` | 630 |
| `common/default_inputs.py` | 48 |
| `common/plotting/unsteady_plots.py` | 1941 |
| `common/plotting/parametric_plots.py` | 333 |
| `common/plotting/steady_plots.py` | 150 |

### UI

| File | Lines |
|---|---|
| `ui/main.py` | 37 |
| `ui/app/shell.py` | 381 |
| `ui/app/backend_bridge.py` | 493 |
| `ui/app/field_registry.py` | 515 |
| `ui/app/settings.py` | 142 |
| `ui/app/theme.py` | 94 |
| `ui/app/version.py` | 35 |
| `ui/app/pages/input_page.py` | 590 |
| `ui/app/pages/bug_report.py` | 511 |
| `ui/app/pages/loading_screen.py` | 461 |
| `ui/app/pages/results_page.py` | 451 |
| `ui/app/pages/steady_results.py` | 443 |
| `ui/app/pages/unsteady_page.py` | 319 |
| `ui/app/pages/steady_page.py` | 318 |
| `ui/app/pages/results_browser.py` | 298 |
| `ui/app/pages/settings_page.py` | 279 |
| `ui/app/pages/patchnotes.py` | 240 |
| `ui/app/pages/unsteady_results.py` | 235 |
| `ui/app/pages/main_menu.py` | 117 |
| `ui/app/pages/placeholder.py` | 63 |
| `ui/app/widgets/` (16 files) | 2731 |
| `ui/app/services/` (4 files) | 509 |

### Tests

| File | Lines |
|---|---|
| `tests/backend_tests_helpers.py` | 650 |
| `tests/backend_tests.py` | 98 |
| `tests/steady_configs/` (3) | 173 |
| `tests/unsteady_configs/` (3) | 270 |
| `tests/ui_configs/` (9) | 660 |
