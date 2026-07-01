# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the MRT Steady-Unsteady Simulator GUI.
#
# Usage  (run from the project root, i.e. the folder containing this src/ tree):
#     pyinstaller src/ui/build.spec
#
# The same command works on Windows, macOS, and Linux. The output goes to
# dist/MRT-Sim<ext> where <ext> is `.exe` on Windows, nothing on Linux,
# `.app` if Apple-bundled.
#
# Cross-OS notes:
#   - PyInstaller does NOT cross-compile. Run this on the OS you want to ship for.
#   - CustomTkinter ships its themes as JSON files that PyInstaller doesn't
#     auto-detect. We collect them explicitly below.
#   - matplotlib + scipy + numpy all need a few hidden imports; we let PyInstaller's
#     own hooks pick those up automatically (they ship a hook for each).

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# ---------------------------------------------------------------------------
# Project layout
# ---------------------------------------------------------------------------

# spec files run with cwd == project root when invoked as
#   `pyinstaller src/ui/build.spec`
project_root = Path.cwd()

entry_script   = project_root / "src" / "ui" / "main.py"
icon_file      = None   # set to a path (.ico on Win, .icns on Mac) when we have one

# ---------------------------------------------------------------------------
# Extra data files to bundle
# ---------------------------------------------------------------------------

# 1.  CustomTkinter's theme + asset files
customtkinter_data = collect_data_files("customtkinter")

# 2.  The simulator's static lookup tables (CEA, N2O, schemas, ...)
backend_static_dirs = [
    project_root / "src" / "backend" / "steady"   / "static_data",
    project_root / "src" / "backend" / "unsteady" / "static_data",
]
static_data_tuples = []
for d in backend_static_dirs:
    if not d.exists():
        continue
    for f in d.rglob("*"):
        if f.is_file():
            # (source on disk, destination inside the bundle relative to the exe)
            dest_rel = f.parent.relative_to(project_root)
            static_data_tuples.append((str(f), str(dest_rel)))

# 3.  UI assets (logo, icons, etc.)
ui_assets_dir = project_root / "src" / "ui" / "assets"
ui_assets_tuples = []
if ui_assets_dir.exists():
    for f in ui_assets_dir.rglob("*"):
        if f.is_file():
            dest_rel = f.parent.relative_to(project_root)
            ui_assets_tuples.append((str(f), str(dest_rel)))

# 4.  Default UI settings (committed baseline used by reset-to-defaults)
ui_default_settings = project_root / "user_data" / "default_ui_settings.json"
ui_default_settings_tuples = []
if ui_default_settings.exists():
    ui_default_settings_tuples.append(
        (str(ui_default_settings), "user_data")
    )

datas = (customtkinter_data + static_data_tuples
         + ui_assets_tuples + ui_default_settings_tuples)

# ---------------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------------
#
# PyInstaller usually detects what we use, but a few packages need a nudge
# because they're imported lazily inside the simulator backend.
hiddenimports = (
    collect_submodules("matplotlib")
    + collect_submodules("customtkinter")
    + [
        "tkinter",
        "PIL._tkinter_finder",
        # add backend modules here if PyInstaller misses them
        "src.backend.unsteady.analysis.unsteady_results",
    ]
)


a = Analysis(
    [str(entry_script)],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # we don't ship the steady PROPEP wrapper from the UI binary yet;
        # drop it if it gets pulled in and bloats the bundle
        # "pypropep",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="MRT-Sim",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # GUI app — no console window on Windows
    icon=str(icon_file) if icon_file else None,
)
