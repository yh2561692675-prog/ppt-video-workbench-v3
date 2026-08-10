#define MyAppName "PPT Video Workbench"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "PPT Video Workbench"

#ifdef ReleasePayload
  #define ReleaseRoot ReleasePayload
#else
  #define ReleaseRoot "..\\dist\\release"
#endif

[Setup]
AppId={{F2A6C8DE-4D6B-4D23-9DD5-4B4B9C4D1D72}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\PPTVideoWorkbench\app
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=ppt-video-workbench-setup
OutputDir=..\release
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}

[Files]
Source: "{#ReleaseRoot}\*"; DestDir: "{app}\release"; Flags: recursesubdirs ignoreversion
Source: "..\scripts\launcher.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion

[Dirs]
Name: "{localappdata}\PPTVideoWorkbench\workspace-data"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\launcher.ps1"" -InstallRoot ""{app}\release"""; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\launcher.ps1"" -InstallRoot ""{app}\release"""; WorkingDir: "{app}"

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\launcher.ps1"" -InstallRoot ""{app}\release"""; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
