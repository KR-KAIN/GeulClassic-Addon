; Inno Setup script: 글클메 애드온 Windows installer.
; Build the app first (BUILD-WINDOWS.bat), then BUILD-INSTALLER.bat.
; Installs for the current user (no administrator prompt). The user's settings,
; chat history and price log live in %LOCALAPPDATA%\KAINMapleTranslator and are
; kept on uninstall.

#ifndef AppVersion
  #define AppVersion "0.4.54-R20.3"
#endif
#define AppName "글클메 애드온"
#define AppExe "글클메 애드온.exe"
#define SourceDir "..\dist\글클메 애드온"

[Setup]
AppId={{1859DB3A-97EE-456B-8309-D4B2F137BC75}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=KAIN
AppPublisherURL=https://github.com/KR-KAIN/GeulClassic-Addon
AppSupportURL=https://github.com/KR-KAIN/GeulClassic-Addon/issues
AppUpdatesURL=https://github.com/KR-KAIN/GeulClassic-Addon/releases
DefaultDirName={autopf}\GeulClassic-Addon
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=GeulClassic-Addon-Setup-v{#AppVersion}
; the translation models are already compressed: normal LZMA2 in its own
; process keeps the compiler well inside its memory
Compression=lzma2/normal
SolidCompression=no
LZMAUseSeparateProcess=yes
WizardStyle=modern
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "바로가기:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} 사용법"; Filename: "{app}\_internal\resources\help\how-to-use.png"
Name: "{group}\{#AppName} 제거"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "지금 {#AppName} 실행"; Flags: nowait postinstall skipifsilent
; R20.2: the app's own updater runs this setup with /SILENT /AUTOUPDATE=1;
; start the app again once the new files are in place
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: IsAutoUpdate

[Code]
function IsAutoUpdate: Boolean;
begin
  Result := ExpandConstant('{param:AUTOUPDATE|0}') = '1';
end;
