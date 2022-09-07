;NSIS Modern User Interface for ArchOctopus
;Written by Cortt Chan

;--------------------------------
;Include Modern UI

  !include "MUI2.nsh"

;--------------------------------
;Define Info

  !define PRODUCT_NAME "ArchOctopus"
  !define /ifndef PRODUCT_VERSION "v2.0.0"
  !define PRODUCT_PUBLISHER "CorttChan"
  !define PRODUCT_WEB_SITE "http://archoctopus.cortt.me"
  !define PRODUCT_DIR_REGKEY "Software\${PRODUCT_NAME}"
  !define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

;--------------------------------
;General

  ;Name and file
  Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
  OutFile "..\dist\${PRODUCT_VERSION}\${PRODUCT_NAME}_${PRODUCT_VERSION}_Setup.exe"
  Unicode True
  SetCompressor /SOLID lzma

  ;Default installation folder
  InstallDir "$LOCALAPPDATA\ArchOctopus"

  ;Get installation folder from registry if available
  InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""

  ;Request application privileges for Windows Vista: none|user|highest|admin
  RequestExecutionLevel user

  ;Show Details
  ShowInstDetails show
  ShowUnInstDetails show

;--------------------------------
;Interface Settings

  !define MUI_ABORTWARNING
  !define MUI_ICON ".\profile.ico"
  !define MUI_UNICON ".\nsis3-icon.ico"
  !define MUI_WELCOMEFINISHPAGE_BITMAP ".\nsis3-branding.bmp"
  !define MUI_WELCOMEPAGE_TITLE "${PRODUCT_NAME}-${PRODUCT_VERSION} 安装向导"
  !define MUI_WELCOMEPAGE_TEXT "此程序源于作者日常工作上的需要, 旨在帮助建筑师简单,高效的收集设计工作中需要的素材资料.$\r$\n$\r$\n程序基于GPL-3.0开源许可证发行, 任何人均可随意使用或分发，但不得用于任何商业目的.$\r$\n$\r$\n$\r$\n$\r$\nCorttChan | LemonLv$\r$\n$\r$\n$_CLICK"

;--------------------------------
;Pages

  ; Welcome page
  !insertmacro MUI_PAGE_WELCOME

  ; License page
  !insertmacro MUI_PAGE_LICENSE "..\..\LICENSE"

  ; Directory page
  !insertmacro MUI_PAGE_DIRECTORY

  ; Instfiles page
  !insertmacro MUI_PAGE_INSTFILES

  ; Finish page
  !define MUI_FINISHPAGE_RUN "$INSTDIR\ArchOctopus.exe"
  !insertmacro MUI_PAGE_FINISH

  ; Uninstaller pages
  !insertmacro MUI_UNPAGE_WELCOME
  !insertmacro MUI_UNPAGE_CONFIRM
  !insertmacro MUI_UNPAGE_INSTFILES
  !insertmacro MUI_UNPAGE_FINISH

;--------------------------------
;Languages

  !insertmacro MUI_LANGUAGE "SimpChinese"

;--------------------------------
;Installer Sections

Section "Installer Section" SecCore

  SetOverwrite on
  ;ADD INSTALL FILES HERE !DONT REMOVE THIS LINE

  ;Store installation folder
  WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" $INSTDIR

  ;Create shortcuts
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_NAME}.exe"
  CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_NAME}.exe"

SectionEnd

;--------------------------------
;Uninstall Info

Section -Post

  ;Create uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\${PRODUCT_NAME}.exe"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayName" "ArchOctopus - 建筑师收集助手"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\ArchOctopus.exe"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"

SectionEnd

;--------------------------------
;Uninstall Functions

Function un.onUninstSuccess
  HideWindow
  MessageBox MB_ICONINFORMATION|MB_OK "$(^Name) 已成功地从你的计算机移除。"
FunctionEnd

Function un.onInit
  !insertmacro MUI_UNGETLANGUAGE
    MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 "你确实要完全移除 $(^Name) ，其及所有的组件？" IDYES +2
    Abort
FunctionEnd

;--------------------------------
;Uninstaller Section

Section "Uninstaller Section"

  Delete "$INSTDIR\Uninstall.exe"

  ;ADD UNINSTALL FILES HERE !DONT REMOVE THIS LINE

  Delete "$INSTDIR\${PRODUCT_NAME}.log"
  RMDir "$INSTDIR"

  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}.lnk"

  DeleteRegKey HKLM "${PRODUCT_UNINST_KEY}"
  DeleteRegKey /ifempty HKLM "${PRODUCT_DIR_REGKEY}"
  SetAutoClose true

SectionEnd