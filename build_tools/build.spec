# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the MRT Steady-Unsteady Simulator.
#
# Usage — normally you don't call this by hand, build.bat does it for you:
#
#     pyinstaller --distpath build_tools/dist --workpath build_tools/build \
#                 build_tools/build.spec
#
# Output: build_tools/dist/MRT-Steady-Unsteady/     (one-folder mode)
#
# The spec resolves the project root from SPECPATH (the folder holding this
# file), NOT from the working directory. That way it doesn't matter where
# pyinstaller was invoked from.
#
# Cross-OS notes:
#   - PyInstaller does NOT cross-compile. Build on the OS you ship for.
#   - rocketcea and pypropep both ship binary data that PyInstaller's static
#     analysis misses, so each gets a collect_all(). CoolProp is deliberately
#     NOT bundled: nothing imports it any more, the N2O properties come from
#     the lookup table in unsteady/static_data.
#   - The UI resolves writable user_data/ to %APPDATA%\MRT-Steady-Unsteady\
#     when frozen (backend_bridge._per_user_data_dir()). The read-only
#     templates and default settings are bundled inside the exe so the
#     first-launch seed step has something to copy.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# ---------------------------------------------------------------------------
# Project layout
# ---------------------------------------------------------------------------

# SPECPATH is injected by PyInstaller and points at build_tools/.
project_root = Path(SPECPATH).resolve().parent      # noqa: F821 - PyInstaller global

# collect_submodules("src") below has to be able to import the package, and
# pyinstaller may have been launched from anywhere.
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
entry_script = project_root / "src" / "ui" / "main.py"

if not entry_script.exists():
    raise SystemExit(
        f"build.spec: can't find {entry_script}. This spec expects to live in "
        f"build_tools/ directly under the project root."
    )

icon_file = project_root / "src" / "ui" / "assets" / "MRT_logo.ico"
if not icon_file.exists():
    icon_file = None


def _tree(directory: Path) -> list[tuple[str, str]]:
    """Every file under `directory`, mapped to the same relative path in the
    bundle. Modules locate their data by walking up from __file__, so the
    layout inside the bundle has to mirror the checkout exactly."""
    if not directory.exists():
        return []
    return [
        (str(f), str(f.parent.relative_to(project_root)))
        for f in directory.rglob("*") if f.is_file()
    ]


# ---------------------------------------------------------------------------
# Third-party data
# ---------------------------------------------------------------------------

customtkinter_data = collect_data_files("customtkinter")

# rocketcea's __init__ reads _version.py relative to itself, and the CEA
# thermo/trans libraries live inside the package. Missing these shows up as
# "FileNotFoundError: rocketcea\_version.py" at import time.
rocketcea_datas, rocketcea_binaries, rocketcea_hidden = collect_all("rocketcea")

# pypropep computes the steady chamber temperature. Not installed on every dev
# machine, so a miss here is not fatal.
try:
    pypropep_datas, pypropep_binaries, pypropep_hidden = collect_all("pypropep")
except Exception:                                   # noqa: BLE001
    pypropep_datas, pypropep_binaries, pypropep_hidden = [], [], []


# ---------------------------------------------------------------------------
# Our own data
# ---------------------------------------------------------------------------

# Backend static data: CEA tables, N2O lookups, input schemas, natural
# constants, default simulation settings.
static_data = (
    _tree(project_root / "src" / "backend" / "steady" / "static_data")
    + _tree(project_root / "src" / "backend" / "unsteady" / "static_data")
    # src/common/static_data holds default_inputs.jsonc, which the field
    # registry reads to pre-fill the propellant chemistry inputs. New since
    # the 1.5 refactor; forgetting it leaves those fields blank in the exe.
    + _tree(project_root / "src" / "common" / "static_data")
)

# PROPEP's own data directory sits beside the steady backend rather than under
# static_data, so it needs its own line.
propep_data = _tree(project_root / "src" / "backend" / "steady" / "PROPEP")

# Logo PNG (home screen) and ICO (window + exe icon).
ui_assets = _tree(project_root / "src" / "ui" / "assets")

# Read-only user_data resources, copied into %APPDATA% by the seed step on
# first launch. Ship the defaults plus the three template configs.
seed_files = [
    project_root / "user_data" / "default_ui_settings.json",
    project_root / "user_data" / "simulation_configs" / "steady" / "steady_example.jsonc",
    project_root / "user_data" / "simulation_configs" / "steady" / "steady_parametric_example.jsonc",
    project_root / "user_data" / "simulation_configs" / "unsteady" / "unsteady_example.jsonc",
]
seed_data = [
    (str(f), str(f.parent.relative_to(project_root)))
    for f in seed_files if f.exists()
]

# VERSION goes at the bundle root; version.py looks for it in sys._MEIPASS.
version_data = []
if (project_root / "VERSION").exists():
    version_data.append((str(project_root / "VERSION"), "."))

datas = (
    customtkinter_data
    + rocketcea_datas
    + pypropep_datas
    + static_data
    + propep_data
    + ui_assets
    + seed_data
    + version_data
)


# ---------------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------------

# THE ONE THAT BITES. shell.py imports pages with
# importlib.import_module(<string>), which PyInstaller's static analysis cannot
# see. Without this, none of the page modules get bundled and every page in the
# exe falls back to the "Not built yet" placeholder.
#
# We walk the tree ourselves rather than using collect_submodules("src"):
# nothing under src/ has an __init__.py (they're namespace packages), and
# collect_submodules is unreliable on those. A filesystem walk is exact and
# needs no import.
def _project_modules() -> list[str]:
    names = []
    for f in (project_root / "src").rglob("*.py"):
        if "__pycache__" in f.parts:
            continue
        rel = f.relative_to(project_root).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts.pop()
        names.append(".".join(parts))
    return sorted(set(names))


project_modules = _project_modules()
print(f"[build.spec] bundling {len(project_modules)} project modules")

hiddenimports = (
    project_modules
    + collect_submodules("matplotlib")
    + collect_submodules("customtkinter")
    + collect_submodules("scipy")          # scipy.integrate.LSODA loads lazily
    + rocketcea_hidden
    + pypropep_hidden
    + [
        "tkinter",
        "PIL._tkinter_finder",             # Pillow's Tk-image bridge
    ]
)


# ---------------------------------------------------------------------------
# Analysis -> PYZ -> EXE -> COLLECT  (one-folder distribution)
# ---------------------------------------------------------------------------

a = Analysis(                                       # noqa: F821
    [str(entry_script)],
    pathex=[str(project_root)],
    binaries=rocketcea_binaries + pypropep_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)                    # noqa: F821

exe = EXE(                                          # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MRT-Steady-Unsteady",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon_file) if icon_file else None,
)

coll = COLLECT(                                     # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MRT-Steady-Unsteady",
)
