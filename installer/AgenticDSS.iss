#define MyAppName "Agentic AI DSS for Retail Investors"
#define MyAppShortName "AgenticDSS"
#define MyAppVersion "0.1.1"
#define MyAppPublisher "Agentic AI DSS Research"
#define MyAppExeName "AgenticDSS.exe"

[Setup]
AppId={{0C9D9536-0961-4F06-97E5-86B17833E2C8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppShortName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
DisableDirPage=yes
DisableProgramGroupPage=yes
OutputDir=installer\output
OutputBaseFilename={#MyAppShortName}-Setup
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SourceDir=..
CloseApplications=no
RestartApplications=no

[Files]
; Install the complete PyInstaller onedir output. User data is stored separately
; under paths.user_data_dir() and is intentionally not installed or uninstalled.
Source: "dist-fixed\AgenticDSS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent

[Code]
// The [Files] entry above only adds/overwrites files; it never removes files
// that existed in a previous install but are absent from the current build
// (e.g. PyInstaller binaries dropped by a packaging fix). Leftover files in
// {app} can shadow the new build's modules at import time, so wipe {app}
// before laying down the new copy on every install, including upgrades.
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    if DirExists(ExpandConstant('{app}')) then
      DelTree(ExpandConstant('{app}'), True, True, True);
  end;
end;

