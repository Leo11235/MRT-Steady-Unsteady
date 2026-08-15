@echo off
REM ===========================================================================
REM Build script for the MRT Steady-Unsteady Simulator.
REM
REM Run it from anywhere — it cd's to the project root itself:
REM     build_tools\build.bat
REM
REM What it does, in order:
REM   1. PyInstaller compiles build_tools\build.spec into
REM      build_tools\dist\MRT-Steady-Unsteady\  (the folder of exe + DLLs).
REM   2. Inno Setup wraps that folder into a single installer .exe at
REM      build_tools\output\MRT-Steady-Unsteady-Setup.exe .
REM
REM Everything the build produces stays inside build_tools\, so the project
REM root has no build clutter:
REM     build_tools\build\    PyInstaller scratch
REM     build_tools\dist\     unpacked app folder
REM     build_tools\output\   the installer you distribute
REM
REM Prerequisites (one-time setup on the build machine):
REM   * A Python 3.13 virtualenv at .venv with requirements.txt installed
REM     (see README > Installation).
REM   * Inno Setup 6 at the default install path.
REM ===========================================================================

setlocal enableextensions

REM --- Locate the project root (parent of this script's folder) -------------
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%.." || goto :error
set "ROOT=%CD%"

if not exist "%SCRIPT_DIR%build.spec" (
    echo [!] build.spec not found next to this script.
    goto :error
)
if not exist "%SCRIPT_DIR%installer.iss" (
    echo [!] installer.iss not found next to this script.
    goto :error
)

REM --- Activate the venv if we can find one --------------------------------
if exist ".venv\Scripts\activate.bat" (
    echo [+] Activating .venv ...
    call ".venv\Scripts\activate.bat"
) else (
    echo [!] No .venv found; using whatever python is on PATH.
)

REM --- Step 1: PyInstaller --------------------------------------------------
echo.
echo ==========================================================================
echo   Step 1/2  PyInstaller
echo ==========================================================================
if exist "build_tools\build" rmdir /s /q "build_tools\build"
if exist "build_tools\dist"  rmdir /s /q "build_tools\dist"

python -m PyInstaller --clean --noconfirm ^
    --distpath "build_tools\dist" ^
    --workpath "build_tools\build" ^
    "build_tools\build.spec"
if errorlevel 1 (
    echo [!] PyInstaller failed.
    goto :error
)
if not exist "build_tools\dist\MRT-Steady-Unsteady\MRT-Steady-Unsteady.exe" (
    echo [!] PyInstaller finished but the expected exe is missing.
    goto :error
)

REM --- Step 2: Inno Setup ---------------------------------------------------
echo.
echo ==========================================================================
echo   Step 2/2  Inno Setup
echo ==========================================================================
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    echo [!] Could not find ISCC.exe.  Install Inno Setup 6 from
    echo     https://jrsoftware.org/isdl.php  and retry.
    goto :error
)

%ISCC% "build_tools\installer.iss"
if errorlevel 1 (
    echo [!] Inno Setup failed.
    goto :error
)

REM --- Done -----------------------------------------------------------------
echo.
echo ==========================================================================
echo   BUILD SUCCEEDED
echo ==========================================================================
echo   Installer:  build_tools\output\MRT-Steady-Unsteady-Setup.exe
echo   Unpacked:   build_tools\dist\MRT-Steady-Unsteady\
echo.
popd
goto :eof

:error
echo.
echo ==========================================================================
echo   BUILD FAILED  --  see messages above.
echo ==========================================================================
popd 2>nul
exit /b 1
