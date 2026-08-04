# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the MRT Steady-Unsteady Simulator GUI.
#
# Usage  (run from the PROJECT ROOT — the folder containing this src/ tree):
#     pyinstaller src/ui/build.spec
#
# Output: dist/MRT-Steady-Unsteady/     (one-folder mode)
#
# Cross-OS notes:
#   - PyInstaller does NOT cross-compile.  Build on the OS you want to
#     ship for (Windows in our case).
#   - CoolProp ships fluid-property binary data that PyInstaller misses;
#     we `collect_all` it below.
#   - CustomTkinter ships its theme JSONs; its bundled hook usually
#     handles them, but we also `collect_data_files` explicitly.
#   - The UI resolves writable user_data/ to %APPDATA%\MRT-Steady-Unsteady\
#     when frozen (see backend_bridge._per_user_data_dir()).  We bundle
#     the read-only *templates* and *default settings* inside the exe so
#     the first-launch seed step has something to copy.

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_all


# ---------------------------------------------------------------------------
# Project layout
# ---------------------------------------------------------------------------

# `pyinstaller` sets CWD to the folder it's invoked from — we require
# the project root, which is the folder containing user_data/.
project_root = Path.cwd()
entry_script = project_root / "src" / "ui" / "main.py"

icon_file = project_root / "src" / "ui" / "assets" / "MRT_logo.ico"
if not icon_file.exists():
    icon_file = None


# ---------------------------------------------------------------------------
# Extra data files to bundle
# ---------------------------------------------------------------------------

# 1. CustomTkinter theme + asset files
customtkinter_data = collect_data_files("customtkinter")

# 2. CoolProp's fluid data + shared library
coolprop_datas, coolprop_binaries, coolprop_hiddenimports = collect_all("CoolProp")

# 2b. rocketcea — its __init__ reads _version.py relative to itself, and
#     the CEA thermo/trans libraries live inside the package.  Missing
#     these causes "FileNotFoundError: rocketcea\\_version.py" at import.
rocketcea_datas, rocketcea_binaries, rocketcea_hiddenimports = collect_all("rocketcea")

# 2c. pypropep — computes steady chamber temperature.  Ships the
#     propellant tables + PROPEP data files that PyInstaller misses.
try:
    pypropep_datas, pypropep_binaries, pypropep_hiddenimports = collect_all("pypropep")
except Exception:
    # pypropep isn't installed on non-frozen dev machines; skip silently.
    pypropep_datas, pypropep_binaries, pypropep_hiddenimports = [], [], []

# 3. Simulator backend static-data folders (CEA tables, N2O lookups, etc.)
static_data_tuples = []
for d in (
    project_root / "src" / "backend" / "steady"   / "static_data",
    project_root / "src" / "backend" / "unsteady" / "static_data",
):
    if not d.exists():
        continue
    for f in d.rglob("*"):
        if f.is_file():
            dest_rel = f.parent.relative_to(project_root)
            static_data_tuples.append((str(f), str(dest_rel)))

# 4. UI assets (logo PNG + ICO, any future icons)
ui_assets_tuples = []
ui_assets_dir = project_root / "src" / "ui" / "assets"
if ui_assets_dir.exists():
    for f in ui_assets_dir.rglob("*"):
        if f.is_file():
            dest_rel = f.parent.relative_to(project_root)
            ui_assets_tuples.append((str(f), str(dest_rel)))

# 5. Read-only user_data resources — copied by the seed step on first
#    launch into %APPDATA%\MRT-Steady-Unsteady\.  Ship the defaults +
#    the two template configs.
seed_files = [
    project_root / "user_data" / "default_ui_settings.json",
    project_root / "user_data" / "simulation_configs" / "steady"   / "steady_example.jsonc",
    project_root / "user_data" / "simulation_configs" / "steady"   / "steady_parametric_example.jsonc",
    project_root / "user_data" / "simulation_configs" / "unsteady" / "unsteady_example.jsonc",
]
seed_tuples = [
    (str(f), str(f.parent.relative_to(project_root)))
    for f in seed_files if f.exists()
]

# Ship the top-level VERSION file at the root of the bundle so
# version.py can read it in a frozen build (falls back to unknown
# if it isn't present).
version_file_tuples = []
_version_file = project_root / "VERSION"
if _version_file.exists():
    version_file_tuples.append((str(_version_file), "."))

datas = (
    customtkinter_data
    + coolprop_datas
    + rocketcea_datas
    + pypropep_datas
    + static_data_tuples
    + ui_assets_tuples
    + seed_tuples
    + version_file_tuples
)


# ---------------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------------

hiddenimports = (
    collect_submodules("matplotlib")
    + collect_submodules("customtkinter")
    + collect_submodules("scipy")          # scipy.integrate.LSODA loads lazily
    + coolprop_hiddenimports
    + rocketcea_hiddenimports
    + pypropep_hiddenimports
    + [
        "tkinter",
        "PIL._tkinter_finder",             # Pillow's Tk-image bridge
        "src.backend.unsteady.analysis.unsteady_results",
    ]
)


# ---------------------------------------------------------------------------
# Analysis -> PYZ -> EXE -> COLLECT  (one-folder distribution)
# ---------------------------------------------------------------------------

a = Analysis(
    [str(entry_script)],
    pathex=[str(project_root)],
    binaries=coolprop_binaries + rocketcea_binaries + pypropep_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
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

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MRT-Steady-Unsteady",
)
