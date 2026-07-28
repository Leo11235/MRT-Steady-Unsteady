; ---------------------------------------------------------------------------
; Inno Setup script for the MRT Steady-Unsteady Simulator.
;
; Prerequisites:
;   1. PyInstaller has already built  dist\MRT-Steady-Unsteady\
;      (run  pyinstaller src\ui\build.spec  from the project root).
;   2. Inno Setup 6 is installed on the build machine
;      (https://jrsoftware.org/isdl.php).
;
; Compile:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
;
; Output:
;   Output\MRT-Steady-Unsteady-Setup.exe   <-- the file you distribute.
;
; Behaviour:
;   * Per-user install (no admin prompt).  Defaults to
;     %LOCALAPPDATA%\Programs\MRT-Steady-Unsteady\ .
;   * Optional desktop shortcut on the "Additional tasks" wizard page.
;   * Single flat Start Menu entry (no folder), so Win-key -> type
;     "MRT" finds it instantly.
;   * Standard uninstaller shows up in Settings > Apps > Installed apps.
;   * Upgrade detection: if a previous version is installed, the newer
;     installer uninstalls it first, then installs cleanly.  The user's
;     %APPDATA%\MRT-Steady-Unsteady\ (presets + results + settings)
;     is preserved across upgrades AND uninstalls — see [UninstallDelete].
; ---------------------------------------------------------------------------

#define AppName             "MRT-Steady-Unsteady"
#define AppDisplayName      "MRT Steady-Unsteady Simulator"
#define AppVersion          "1.1.0"
#define AppPublisher        "McGill Rocket Team"
#define AppURL              "https://github.com/Leo11235/MRT-Steady-Unsteady"
#define AppExeName          "MRT-Steady-Unsteady.exe"
#define BuildOutputDir      "dist\MRT-Steady-Unsteady"
#define SetupIcon           "src\ui\assets\MRT_logo.ico"

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

; Per-user install (no admin prompt).  {autopf} would be Program Files
; for admin installs; for lowest-privilege installs we use {userpf}.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline

DefaultDirName={autopf}\{#AppName}

; Don't ask the user to pick a Start Menu folder — we're using a
; single flat entry via {autoprograms}.
DisableProgramGroupPage=yes

; Icon on the setup .exe itself.
SetupIconFile={#SetupIcon}

; Where the compiled setup .exe lands.
OutputDir=Output
OutputBaseFilename={#AppName}-Setup

; Solid LZMA compression — smaller file at the cost of a few seconds
; compile time.  Standard for GUI apps this size.
Compression=lzma2/max
SolidCompression=yes

; Modern-flat wizard style.
WizardStyle=modern

; Show install progress but not the classic "Ready to install" review
; page (it just lists everything and adds a click).
DisableReadyPage=no

; ---------------------------------------------------------------------------

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french";  MessagesFile: "compiler:Languages\French.isl"

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
;   NOTE: we intentionally DO NOT delete %APPDATA%\MRT-Steady-Unsteady\
;   because that contains the user's saved presets, run results, and
;   preferences.  Users can nuke it manually if they want to.
; ---------------------------------------------------------------------------
[UninstallDelete]
Type: filesandordirs; Name: "{app}"

; ---------------------------------------------------------------------------
; Upgrade detection: if the app is already installed, silently uninstall
; the old copy first so we get a clean install of the new version.
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
