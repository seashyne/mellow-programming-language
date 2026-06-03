; MellowLang v2.3.4 — Inno Setup: onefile build
; Wraps dist\mellow_onefile.exe into a lightweight installer.
; Build: ISCC.exe packaging\windows\mellowlang_onefile.iss

#define MyAppName      "MellowLang"
#define MyAppVersion   "2.3.4"
#define MyAppPublisher "Seashyne"
#define MyAppExeName   "mellow.exe"
#define MyAppURL       "https://mellowlang.org"

[Setup]
AppId={{A9B6F6F1-8C9E-4F9C-9E51-MELLOWLANG234OF}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={userpf}\MellowLang
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=MellowLang_Setup_{#MyAppVersion}_portable
SetupIconFile=
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "addtopath";   Description: "Add {#MyAppName} to PATH (recommended)"; Flags: checked
Name: "associate";   Description: "Associate .mellow files with {#MyAppName}"; Flags: checked
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
; Single portable executable from PyInstaller onefile build
Source: "..\..\dist\mellow_onefile.exe"; DestDir: "{app}"; DestName: "mellow.exe"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";            Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}";  Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}";      Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--version"; Description: "Verify installation"; \
    Flags: nowait postinstall skipifsilent runascurrentuser

[Registry]
Root: HKCU; Subkey: "Environment"; \
    ValueType: expandsz; ValueName: "Path"; \
    ValueData: "{olddata};{app}"; \
    Flags: preservestringtype; Tasks: addtopath

Root: HKCU; Subkey: "Software\Classes\.mellow"; \
    ValueType: string; ValueData: "MellowLang.Script"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\MellowLang.Script"; \
    ValueType: string; ValueData: "MellowLang Script"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\MellowLang.Script\DefaultIcon"; \
    ValueType: string; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\MellowLang.Script\shell\open\command"; \
    ValueType: string; \
    ValueData: """{app}\{#MyAppExeName}"" run ""%1"""; Tasks: associate

Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; \
    ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var OldPath, NewPath, AppDir: string; P: Integer;
begin
  if CurUninstallStep = usPostUninstall then begin
    AppDir := ExpandConstant('{app}');
    if RegQueryStringValue(HKCU, 'Environment', 'Path', OldPath) then begin
      P := Pos(';' + AppDir, OldPath);
      if P > 0 then begin
        NewPath := Copy(OldPath, 1, P-1) + Copy(OldPath, P+Length(AppDir)+1, MaxInt);
        RegWriteStringValue(HKCU, 'Environment', 'Path', NewPath);
      end;
    end;
  end;
end;
