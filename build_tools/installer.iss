; ---------------------------------------------------------------------------
; Inno Setup script for the MRT Steady-Unsteady Simulator.
;
; This file lives in build_tools/, so every relative path below is relative to
; build_tools/ — that's what SourcePath resolves to. ".." is the project root.
;
; Prerequisites:
;   1. PyInstaller has already built  build_tools\dist\MRT-Steady-Unsteady\
;      (build.bat does this for you).
;   2. Inno Setup 6 is installed on the build machine
;      (https://jrsoftware.org/isdl.php).
;
; Compile:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build_tools\installer.iss
;
; Output:
;   build_tools\output\MRT-Steady-Unsteady-Setup.exe   <-- the file you ship.
;
; Behaviour:
;   * Per-user install (no admin prompt).
;   * Optional desktop shortcut on the "Additional tasks" wizard page.
;   * Single flat Start Menu entry (no folder), so Win-key -> type "MRT"
;     finds it instantly.
;   * Standard uninstaller in Settings > Apps > Installed apps.
;   * Upgrade detection: a newer installer uninstalls the old copy first,
;     then installs cleanly. The user's %APPDATA%\MRT-Steady-Unsteady\
;     (presets, results, settings) survives both upgrades and uninstalls —
;     see the note above [UninstallDelete].
; ---------------------------------------------------------------------------

#define AppName             "MRT-Steady-Unsteady"
#define AppDisplayName      "MRT Steady-Unsteady Simulator"
; Version is read from the top-level VERSION file so the installer, the Python
; UI and the Windows Add/Remove entry can never drift apart. Bump the version
; by editing that one file (single line, e.g. "1.5").
#define AppVersion          Trim(FileRead(FileOpen(SourcePath + "..\VERSION")))
#define AppPublisher        "McGill Rocket Team"
#define AppURL              "https://github.com/Leo11235/MRT-Steady-Unsteady"
#define AppExeName          "MRT-Steady-Unsteady.exe"
#define BuildOutputDir      "dist\MRT-Steady-Unsteady"
#define SetupIcon           "..\src\ui\assets\MRT_logo.ico"

[Setup]
; Unique upgrade GUID — never change this string once shipped.
AppId={{9F4A7C11-6E0B-4B4D-9F7A-8CE3D2E0D1B7}
AppName={#AppDisplayName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
VersionInfoVersion={#AppVersion}

; Per-user install, no admin prompt.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline

DefaultDirName={autopf}\{#AppName}

; Don't ask which Start Menu folder to use — we use one flat entry.
DisableProgramGroupPage=yes

; Icon on the setup .exe itself.
SetupIconFile={#SetupIcon}

; Where the compiled setup .exe lands, relative to this file.
OutputDir=output
OutputBaseFilename={#AppName}-Setup

; Solid LZMA compression: smaller file, a few more seconds to compile.
Compression=lzma2/max
SolidCompression=yes

WizardStyle=modern
DisableReadyPage=no

; ---------------------------------------------------------------------------

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ---------------------------------------------------------------------------
; Additional tasks — one checkbox for the desktop shortcut.
; ---------------------------------------------------------------------------
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"

; ---------------------------------------------------------------------------
; Files to install — the entire PyInstaller output folder.
; ---------------------------------------------------------------------------
[Files]
Source: "{#BuildOutputDir}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

; ---------------------------------------------------------------------------
; Shortcuts.
;   {autoprograms} = per-user Start Menu Programs folder (no subfolder).
;   {autodesktop}  = per-user Desktop.
; ---------------------------------------------------------------------------
[Icons]
Name: "{autoprograms}\{#AppDisplayName}"; Filename: "{app}\{#AppExeName}"; \
    IconFilename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppDisplayName}";  Filename: "{app}\{#AppExeName}"; \
    IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon

; ---------------------------------------------------------------------------
; Post-install: optional launch checkbox on the Finish page.
; ---------------------------------------------------------------------------
[Run]
Filename: "{app}\{#AppExeName}"; \
    Description: "{cm:LaunchProgram,{#StringChange(AppDisplayName, '&', '&&')}}"; \
    Flags: nowait postinstall skipifsilent

; ---------------------------------------------------------------------------
; Uninstall: remove everything we installed.
;   We deliberately DO NOT delete %APPDATA%\MRT-Steady-Unsteady\ — that holds
;   the user's saved presets, run results and preferences. They can delete it
;   by hand if they want it gone.
; ---------------------------------------------------------------------------
[UninstallDelete]
Type: filesandordirs; Name: "{app}"

; ---------------------------------------------------------------------------
; Upgrade detection: if the app is already installed, silently uninstall the
; old copy first so we get a clean install of the new version.
; ---------------------------------------------------------------------------
[Code]
function GetUninstallString(): String;
var
  sUnInstPath: String;
  sUnInstallString: String;
begin
  sUnInstPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\'
                  + '{#emit SetupSetting("AppId")}_is1';
  sUnInstallString := '';
  if not RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString) then
    RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString', sUnInstallString);
  Result := sUnInstallString;
end;

function IsUpgrade(): Boolean;
begin
  Result := (GetUninstallString() <> '');
end;

function UnInstallOldVersion(): Integer;
var
  sUnInstallString: String;
  iResultCode: Integer;
begin
  Result := 0;
  sUnInstallString := GetUninstallString();
  if sUnInstallString <> '' then begin
    sUnInstallString := RemoveQuotes(sUnInstallString);
    if Exec(sUnInstallString, '/SILENT /NORESTART /SUPPRESSMSGBOXES',
            '', SW_HIDE, ewWaitUntilTerminated, iResultCode) then
      Result := 3   // success
    else
      Result := 2;  // failed
  end else
    Result := 1;    // nothing to uninstall
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssInstall) then begin
    if IsUpgrade() then
      UnInstallOldVersion();
  end;
end;
