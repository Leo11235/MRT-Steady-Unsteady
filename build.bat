@echo off
REM ===========================================================================
REM Build script for the MRT Steady-Unsteady Simulator.
REM
REM What this does, in order:
REM   1. PyInstaller compiles src\ui\build.spec into dist\MRT-Steady-Unsteady\
REM      (the folder of exe + DLLs).
REM   2. Inno Setup wraps that folder into a single installer .exe at
REM      Output\MRT-Steady-Unsteady-Setup.exe .
REM
REM Prerequisites (one-time setup on the build machine):
REM   * A Python 3.13 virtualenv at .venv with the requirements installed
REM     (see README > Installation).
REM   * Inno Setup 6 installed at the default path
REM     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" .
REM
REM Run from the project root:
REM     build.bat
REM ===========================================================================

setlocal enableextensions

REM --- Sanity check: are we running from the project root? ------------------
if not exist "src\ui\build.spec" (
    echo [!] build.spec not found.  Run this script from the project root.
    goto :error
)
if not exist "installer.iss" (
    echo [!] installer.iss not found.  Run this script from the project root.
    goto :error
)

REM --- Activate the venv if we can find one --------------------------------
if exist ".venv\Scripts\activate.bat" (
    echo [+] Activating .venv ...
    call .venv\Scripts\activate.bat
) else (
    echo [!] No .venv found; using whatever python is on PATH.
)

REM --- Step 1: PyInstaller --------------------------------------------------
echo.
echo ==========================================================================
echo   Step 1/2  PyInstaller
echo ==========================================================================
if exist "build"  rmdir /s /q "build"
if exist "dist"   rmdir /s /q "dist"

python -m PyInstaller --clean --noconfirm src\ui\build.spec
if errorlevel 1 (
    echo [!] PyInstaller failed.
    goto :error
)
if not exist "dist\MRT-Steady-Unsteady\MRT-Steady-Unsteady.exe" (
    echo [!] PyInstaller finished but the expected exe is missing.
    goto :error
)

REM --- Step 2: Inno Setup ---------------------------------------------------
echo.
echo ==========================================================================
echo   Step 2/2  Inno Setup
echo ==========================================================================
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
)
if not exist %ISCC% (
    echo [!] Could not find ISCC.exe.  Install Inno Setup 6 from
    echo     https://jrsoftware.org/isdl.php  and retry.
    goto :error
)

%ISCC% installer.iss
if errorlevel 1 (
    echo [!] Inno Setup failed.
    goto :error
)

REM --- Done -----------------------------------------------------------------
echo.
echo ==========================================================================
echo   BUILD SUCCEEDED
echo ==========================================================================
echo   Installer: Output\MRT-Steady-Unsteady-Setup.exe
echo   Folder build (unpacked): dist\MRT-Steady-Unsteady\
echo.
goto :eof

:error
echo.
echo ==========================================================================
echo   BUILD FAILED  --  see messages above.
echo ==========================================================================
exit /b 1
