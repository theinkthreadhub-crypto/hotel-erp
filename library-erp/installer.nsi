; Library ERP — Windows Setup (makensis installer.nsi)
; Ek baar install: C:\LibraryERP mein exe, Desktop + Start Menu shortcut, Uninstall.
; Data (LibraryData) uninstall par bhi nahi hatta, jab tak aap khud na kahein.

Unicode true
Target amd64-unicode ; ERP 64-bit hai, installer bhi 64-bit
!include "MUI2.nsh"

!define APP "Library ERP"
!define EXE "LibraryERP.exe"
!define UNKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\LibraryERP"
!ifndef VERSION
  !define VERSION "1.0.0"
!endif

Name "${APP}"
OutFile "dist\LibraryERP-Setup.exe"
InstallDir "C:\LibraryERP"
InstallDirRegKey HKCU "Software\LibraryERP" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "${APP} ${VERSION}"

!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Library ERP Setup"
!define MUI_WELCOMEPAGE_TEXT "This will install Library ERP on this computer.$\r$\n$\r$\nA desktop shortcut will be created. Your data is kept in the LibraryData folder inside the install folder.$\r$\n$\r$\nClick Next to continue."
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Open Library ERP now"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install"
  ; Purana ERP chal raha ho to band karo, taaki exe badal sake
  nsExec::Exec 'taskkill /F /IM ${EXE}'
  Sleep 800
  SetOutPath "$INSTDIR"
  File "dist\${EXE}"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateShortCut "$DESKTOP\${APP}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0
  CreateDirectory "$SMPROGRAMS\${APP}"
  CreateShortCut "$SMPROGRAMS\${APP}\${APP}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0
  CreateShortCut "$SMPROGRAMS\${APP}\Data folder.lnk" "$INSTDIR\LibraryData"
  CreateShortCut "$SMPROGRAMS\${APP}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "Software\LibraryERP" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNKEY}" "DisplayName" "${APP}"
  WriteRegStr HKCU "${UNKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNKEY}" "Publisher" "SETU"
  WriteRegStr HKCU "${UNKEY}" "DisplayIcon" "$INSTDIR\${EXE}"
  WriteRegStr HKCU "${UNKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "${UNKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNKEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  nsExec::Exec 'taskkill /F /IM ${EXE}'
  Sleep 800
  Delete "$INSTDIR\${EXE}"
  Delete "$INSTDIR\Uninstall.exe"
  Delete "$DESKTOP\${APP}.lnk"
  RMDir /r "$SMPROGRAMS\${APP}"
  DeleteRegKey HKCU "${UNKEY}"
  DeleteRegKey HKCU "Software\LibraryERP"
  MessageBox MB_YESNO|MB_ICONEXCLAMATION|MB_DEFBUTTON2 "Also delete ALL library DATA (students, fees, receipts, backups)?$\r$\n$\r$\nChoose No to keep the data safe in $INSTDIR\LibraryData." /SD IDNO IDYES deldata IDNO keep
  deldata:
    RMDir /r "$INSTDIR\LibraryData"
    Delete "$INSTDIR\LibraryERP-log.txt"
  keep:
  RMDir "$INSTDIR"
SectionEnd
