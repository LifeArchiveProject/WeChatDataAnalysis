; This file is included for both installer and uninstaller builds.
; Guard installer-only pages/functions to avoid "function not referenced" warnings
; when electron-builder compiles the standalone uninstaller.
!ifndef BUILD_UNINSTALLER
!include nsDialogs.nsh
!include LogicLib.nsh

; Directory page is a "parent folder" picker. When users browse to a new folder,
; NSIS will set $INSTDIR to exactly what they pick (without app sub-folder),
; and electron-builder later appends "\${APP_FILENAME}" before installation.
; Make this explicit on the directory page to reduce confusion.
!define /ifndef MUI_DIRECTORYPAGE_TEXT_TOP "请选择安装位置（将自动创建并使用“${APP_FILENAME}”子文件夹）。"
!define /ifndef MUI_DIRECTORYPAGE_TEXT_DESTINATION "安装位置："

Var WDA_InstallDirPage

!macro customPageAfterChangeDir
  ; Add a confirmation page after the directory picker so users clearly see
  ; the final install location (includes the app sub-folder).
  !ifdef allowToChangeInstallationDirectory
    Page custom WDA_InstallDirPageCreate WDA_InstallDirPageLeave
  !endif
!macroend

Function WDA_EnsureAppSubDir
  ; Normalize $INSTDIR to always end with "\${APP_FILENAME}" (avoid cluttering a parent folder).
  StrCpy $0 "$INSTDIR"

  ; Trim trailing "\" (except for drive root like "C:\").
  StrLen $1 "$0"
  ${If} $1 > 3
    StrCpy $2 "$0" 1 -1
    ${If} $2 == "\"
      IntOp $1 $1 - 1
      StrCpy $0 "$0" $1
    ${EndIf}
  ${EndIf}

  ; If already ends with APP_FILENAME, keep it.
  StrLen $3 "$0"
  StrLen $4 "${APP_FILENAME}"
  ${If} $3 >= $4
    IntOp $5 $3 - $4
    StrCpy $6 "$0" $4 $5
    ${If} $6 == "${APP_FILENAME}"
      StrCpy $INSTDIR "$0"
      Return
    ${EndIf}
  ${EndIf}

  ; Otherwise append the app folder name.
  StrCpy $INSTDIR "$0\${APP_FILENAME}"
FunctionEnd

Function WDA_InstallDirPageCreate
  Call WDA_EnsureAppSubDir

  nsDialogs::Create 1018
  Pop $WDA_InstallDirPage

  ${If} $WDA_InstallDirPage == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0u 0u 100% 24u "程序将安装到："
  Pop $0

  ${NSD_CreateLabel} 0u 22u 100% 24u "$INSTDIR"
  Pop $0

  ${NSD_CreateLabel} 0u 50u 100% 36u "为避免把文件直接安装到父目录，安装程序会自动创建“${APP_FILENAME}”子文件夹。"
  Pop $0

  nsDialogs::Show
FunctionEnd

Function WDA_InstallDirPageLeave
FunctionEnd

!endif

!ifdef BUILD_UNINSTALLER
!include nsDialogs.nsh
!include LogicLib.nsh

Var WDA_UninstallOptionsPage
Var WDA_UninstallDeleteDataCheckbox
Var /GLOBAL WDA_DeleteUserData

!macro customUnInit
  ; Default: keep user data (also applies to silent uninstall / update uninstall).
  StrCpy $WDA_DeleteUserData "0"
!macroend

!macro customUnWelcomePage
  !insertmacro MUI_UNPAGE_WELCOME
  ; Optional page: allow user to choose whether to delete app data.
  UninstPage custom un.WDA_UninstallOptionsCreate un.WDA_UninstallOptionsLeave
!macroend

Function un.WDA_UninstallOptionsCreate
  nsDialogs::Create 1018
  Pop $WDA_UninstallOptionsPage

  ${If} $WDA_UninstallOptionsPage == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0u 0u 100% 24u "卸载选项："
  Pop $0

  ${NSD_CreateCheckbox} 0u 24u 100% 12u "同时删除用户数据（导出的聊天记录、日志、配置等）"
  Pop $WDA_UninstallDeleteDataCheckbox
  ; Safer default: do not delete.
  ${NSD_Uncheck} $WDA_UninstallDeleteDataCheckbox

  nsDialogs::Show
FunctionEnd

Function un.WDA_UninstallOptionsLeave
  ${NSD_GetState} $WDA_UninstallDeleteDataCheckbox $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $WDA_DeleteUserData "1"
  ${Else}
    StrCpy $WDA_DeleteUserData "0"
  ${EndIf}
FunctionEnd

!macro customUnInstall
  ; If this is an update uninstall, never delete user data.
  ${ifNot} ${isUpdated}
    ${if} $WDA_DeleteUserData == "1"
      ; Electron always stores user data per-user. If the app was installed for all users,
      ; switch to current user context to remove the correct AppData directory.
      ${if} $installMode == "all"
        SetShellVarContext current
      ${endif}

      RMDir /r "$APPDATA\${APP_FILENAME}"
      !ifdef APP_PRODUCT_FILENAME
        RMDir /r "$APPDATA\${APP_PRODUCT_FILENAME}"
      !endif
      ; Electron may use package.json "name" for some storage (cache, indexeddb, etc.).
      !ifdef APP_PACKAGE_NAME
        RMDir /r "$APPDATA\${APP_PACKAGE_NAME}"
      !endif

      ${if} $installMode == "all"
        SetShellVarContext all
      ${endif}
    ${endif}
  ${endif}
!macroend

!endif
