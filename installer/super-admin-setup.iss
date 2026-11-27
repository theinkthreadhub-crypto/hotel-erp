; HoReCa One Super Admin - Windows installer (Inno Setup 6). Built by .github/workflows/build-super-admin-exe.yml.
; Vendor tool only (never given to hotels). Per-user install, no admin rights. It opens https://hotel.setupro.in/admin.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{2E41B7BC-D3C9-4C20-9660-C2DA846AFAA3}
AppName=HoReCa One Super Admin
AppVersion={#AppVersion}
AppVerName=HoReCa One Super Admin {#AppVersion}
AppPublisher=Aghanya Devanya Enterprises
VersionInfoCompany=Aghanya Devanya Enterprises
VersionInfoCopyright=Copyright (C) Aghanya Devanya Enterprises
DefaultDirName={localappdata}\Programs\HoReCaOneSuperAdmin
DisableDirPage=yes
DefaultGroupName=HoReCa One Super Admin
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
MinVersion=6.3
OutputDir=..\Output
OutputBaseFilename=HoReCa-One-Super-Admin-Setup
SetupIconFile=..\favicon.ico
UninstallDisplayIcon={app}\HoReCa-One-Super-Admin.exe
UninstallDisplayName=HoReCa One Super Admin
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force

[Tasks]
Name: "desktopicon"; Description: "Create a Super Admin icon on the desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\HoReCa-One-Super-Admin.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\favicon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsWebView2

[Icons]
Name: "{group}\HoReCa One Super Admin"; Filename: "{app}\HoReCa-One-Super-Admin.exe"; WorkingDir: "{app}"; IconFilename: "{app}\favicon.ico"
Name: "{group}\Uninstall HoReCa One Super Admin"; Filename: "{uninstallexe}"
Name: "{userdesktop}\HoReCa One Super Admin"; Filename: "{app}\HoReCa-One-Super-Admin.exe"; WorkingDir: "{app}"; IconFilename: "{app}\favicon.ico"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft WebView2 (requires an internet connection)..."; Check: NeedsWebView2; Flags: waituntilterminated
Filename: "{app}\HoReCa-One-Super-Admin.exe"; Description: "Open Super Admin now"; Flags: nowait postinstall skipifsilent

[Code]
const
  WV2 = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function HasWV2(Root: Integer; Key: String): Boolean;
var
  V: String;
begin
  Result := RegQueryStringValue(Root, Key, 'pv', V) and (V <> '') and (V <> '0.0.0.0');
end;

function NeedsWebView2(): Boolean;
begin
  Result := not (HasWV2(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WV2) or
                 HasWV2(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WV2) or
                 HasWV2(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\' + WV2));
end;
