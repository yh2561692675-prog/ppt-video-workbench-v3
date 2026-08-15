#define MyAppName "PPT Video Workbench"
#define MyAppVersion "0.1.1"
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
; Keep the uninstaller binary, but do not write the per-user Add/Remove
; Programs registration. Some managed Windows profiles deny HKCU uninstall
; key creation even though the user's app directory is writable.
CreateUninstallRegKey=no
OutputBaseFilename=ppt-video-workbench-setup
OutputDir=..\release
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}

[Files]
Source: "{#ReleaseRoot}\*"; DestDir: "{app}\releases\{#MyAppVersion}\release"; Excludes: "launcher\*"; Flags: recursesubdirs ignoreversion
Source: "{#ReleaseRoot}\launcher\workbench-launcher.exe"; DestDir: "{app}\launcher"; Flags: ignoreversion

[Dirs]
Name: "{localappdata}\PPTVideoWorkbench\workspace-data"

[Tasks]
Name: "shortcuts"; Description: "创建开始菜单和桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\launcher\workbench-launcher.exe"; Parameters: "--app-root ""{app}"" start"; WorkingDir: "{app}"; Tasks: shortcuts
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\launcher\workbench-launcher.exe"; Parameters: "--app-root ""{app}"" start"; WorkingDir: "{app}"; Tasks: shortcuts

[Run]
Filename: "{app}\launcher\workbench-launcher.exe"; Parameters: "--app-root ""{app}"" activate --version ""{#MyAppVersion}"" --release-root ""{app}\releases\{#MyAppVersion}\release"""; WorkingDir: "{app}"; Flags: runhidden waituntilterminated
Filename: "{app}\launcher\workbench-launcher.exe"; Parameters: "--app-root ""{app}"" start"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\launcher\workbench-launcher.exe"; Parameters: "--app-root ""{app}"" shutdown"; WorkingDir: "{app}"; Flags: runhidden waituntilterminated skipifdoesntexist

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
