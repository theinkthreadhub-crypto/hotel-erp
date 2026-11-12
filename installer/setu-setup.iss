; Setu POS - Windows installer (Inno Setup 6). Built by .github/workflows/build-exe.yml.
; Installs for the current user (no admin), next to where Install-Aghanya-Devanya-ERP-Setup.bat
; used to put it, so both kinds of install update the same copy. Hotel data lives in
; %LOCALAPPDATA%\AghanyaDevanyaERP\Data and is never touched by install or uninstall.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{7B3C2E51-5A9D-4C1E-9F0B-2D6A8E4F1C73}
AppName=HoReCa One
AppVersion={#AppVersion}
AppVerName=HoReCa One {#AppVersion}
AppPublisher=Aghanya Devanya Enterprises
DefaultDirName={localappdata}\Programs\AghanyaDevanyaERP
DisableDirPage=yes
DefaultGroupName=HoReCa One
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
; Setu is a 64-bit program (Python 3.12): Windows 8.1 / 10 / 11, 64-bit. Older or 32-bit Windows get a clear message instead of a broken install.
ArchitecturesAllowed=x64
MinVersion=6.3
OutputDir=..\Output
OutputBaseFilename=Setu-POS-Setup
SetupIconFile=..\favicon.ico
UninstallDisplayIcon={app}\Aghanya-Devanya-Hotel-ERP.exe
UninstallDisplayName=HoReCa One - Restaurant & Hotel POS
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a HoReCa One icon on the desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\Aghanya-Devanya-Hotel-ERP.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\hotel_erp.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\manifest.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\sw.js"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\icon-192.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\icon-512.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\logo.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\favicon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\whatsapp\*"; DestDir: "{app}\whatsapp"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsWebView2

[Icons]
Name: "{group}\HoReCa One"; Filename: "{app}\Aghanya-Devanya-Hotel-ERP.exe"; WorkingDir: "{app}"; IconFilename: "{app}\favicon.ico"
Name: "{group}\Uninstall HoReCa One"; Filename: "{uninstallexe}"
Name: "{userdesktop}\HoReCa One"; Filename: "{app}\Aghanya-Devanya-Hotel-ERP.exe"; WorkingDir: "{app}"; IconFilename: "{app}\favicon.ico"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft WebView2 (requires an internet connection)..."; Check: NeedsWebView2; Flags: waituntilterminated
Filename: "{app}\Aghanya-Devanya-Hotel-ERP.exe"; Description: "Open HoReCa One now"; Flags: nowait postinstall skipifsilent
; Update from inside Setu (silent install): start Setu again by itself
Filename: "{app}\Aghanya-Devanya-Hotel-ERP.exe"; Flags: nowait; Check: WizardSilent

[Code]
const
  WV2 = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function HasWV2(Root: Integer; Key: String): Boolean;
var
  V: String;
begin
  Result := RegQueryStringValue(Root, Key, 'pv', V) and (V <> '') and (V <> '0.0.0.0');
end;

// The Setu window needs the Edge WebView2 runtime (Windows 11 has it, older PCs may not)
function NeedsWebView2(): Boolean;
begin
  Result := not (HasWV2(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WV2) or
                 HasWV2(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WV2) or
                 HasWV2(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\' + WV2));
end;
