; This file is included for both installer and uninstaller builds.
; Guard installer-only pages/functions to avoid "function not referenced" warnings
; when electron-builder compiles the standalone uninstaller.
; Electron derives `userData` from package.json `name` in this app. Keep the
; installer's canonical settings/output paths aligned with that runtime path.
!ifdef APP_PACKAGE_NAME
!define /ifndef WDA_RUNTIME_APPDATA_NAME "${APP_PACKAGE_NAME}"
!else
!define /ifndef WDA_RUNTIME_APPDATA_NAME "${APP_FILENAME}"
!endif
!define /ifndef WDA_DEFAULT_SETTINGS_PATH "$APPDATA\${WDA_RUNTIME_APPDATA_NAME}\desktop-settings.json"
!define /ifndef WDA_DEFAULT_OUTPUT_DIR "$APPDATA\${WDA_RUNTIME_APPDATA_NAME}\output"
!define /ifndef WDA_FILENAME_SETTINGS_PATH "$APPDATA\${APP_FILENAME}\desktop-settings.json"
!define /ifndef WDA_FILENAME_OUTPUT_DIR "$APPDATA\${APP_FILENAME}\output"
!ifdef APP_PRODUCT_FILENAME
!define /ifndef WDA_PRODUCT_SETTINGS_PATH "$APPDATA\${APP_PRODUCT_FILENAME}\desktop-settings.json"
!define /ifndef WDA_PRODUCT_OUTPUT_DIR "$APPDATA\${APP_PRODUCT_FILENAME}\output"
!else
!define /ifndef WDA_PRODUCT_SETTINGS_PATH ""
!define /ifndef WDA_PRODUCT_OUTPUT_DIR ""
!endif
!ifdef APP_PACKAGE_NAME
!define /ifndef WDA_PACKAGE_SETTINGS_PATH "$APPDATA\${APP_PACKAGE_NAME}\desktop-settings.json"
!define /ifndef WDA_PACKAGE_OUTPUT_DIR "$APPDATA\${APP_PACKAGE_NAME}\output"
!else
!define /ifndef WDA_PACKAGE_SETTINGS_PATH ""
!define /ifndef WDA_PACKAGE_OUTPUT_DIR ""
!endif
!ifndef BUILD_UNINSTALLER
!include nsDialogs.nsh
!include LogicLib.nsh
!include FileFunc.nsh

; Directory page is a "parent folder" picker. When users browse to a new folder,
; NSIS will set $INSTDIR to exactly what they pick (without app sub-folder),
; and electron-builder later appends "\${APP_FILENAME}" before installation.
; Make this explicit on the directory page to reduce confusion.
!define /ifndef MUI_DIRECTORYPAGE_TEXT_TOP "请选择安装位置（将自动创建并使用“${APP_FILENAME}”子文件夹）。"
!define /ifndef MUI_DIRECTORYPAGE_TEXT_DESTINATION "安装位置："

Var WDA_InstallDirPage
Var WDA_OutputDirPage
Var WDA_OutputDirInput
Var WDA_OutputDirBrowseButton
Var WDA_SelectedOutputDir
Var WDA_PreviousShellAppData

!ifndef INSTALL_MODE_PER_ALL_USERS
!macro WDA_CleanupGhostPerUserInstall
  ; Issue #77 can leave HKCU metadata and dead links without either installed
  ; binary. Only repair that exact state; never remove a real or partial app,
  ; a record for another location, or an installation on an offline volume.
  ReadRegStr $R8 HKCU "${INSTALL_REGISTRY_KEY}" InstallLocation
  ReadRegStr $R9 HKCU "${UNINSTALL_REGISTRY_KEY}" UninstallString
  ReadRegStr $R7 HKCU "${UNINSTALL_REGISTRY_KEY}" QuietUninstallString
  ${GetRoot} "$R8" $R6
  ${If} $R8 != ""
  ${AndIf} $R6 != ""
  ${AndIf} ${FileExists} "$R6\."
  ${AndIf} $R9 == '"$R8\${UNINSTALL_FILENAME}" /currentuser'
  ${AndIf} $R7 == '"$R8\${UNINSTALL_FILENAME}" /currentuser /S'
  ${AndIfNot} ${FileExists} "$R8\${APP_EXECUTABLE_FILENAME}"
  ${AndIfNot} ${FileExists} "$R8\${UNINSTALL_FILENAME}"
    Call WDA_UseCurrentUserAppData
    Call WDA_PrepareInstallDirScript
    !ifdef MENU_FILENAME
      nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\wda-install-dir.ps1" -Mode RemoveGhostShortcuts -InstallDir "$R8" -ExpectedExecutablePath "$R8\${APP_EXECUTABLE_FILENAME}" -ShortcutPath1 "$DESKTOP\${SHORTCUT_NAME}.lnk" -ShortcutPath2 "$SMPROGRAMS\${MENU_FILENAME}\${SHORTCUT_NAME}.lnk"'
    !else
      nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\wda-install-dir.ps1" -Mode RemoveGhostShortcuts -InstallDir "$R8" -ExpectedExecutablePath "$R8\${APP_EXECUTABLE_FILENAME}" -ShortcutPath1 "$DESKTOP\${SHORTCUT_NAME}.lnk" -ShortcutPath2 "$SMPROGRAMS\${SHORTCUT_NAME}.lnk"'
    !endif
    Pop $R5
    Pop $R4
    Call WDA_RestoreInstallShellContext

    ; Keep the record if shortcut inspection failed. A later run can retry and
    ; this avoids turning a partially inspected state into a broader cleanup.
    ${If} $R5 == "0"
      DeleteRegKey HKCU "${UNINSTALL_REGISTRY_KEY}"
      DeleteRegKey HKCU "${INSTALL_REGISTRY_KEY}"
      StrCpy $hasPerUserInstallation "0"
      ${If} $hasPerMachineInstallation == "1"
        !insertmacro setInstallModePerAllUsers
      ${Else}
        !insertmacro setInstallModePerUser
      ${EndIf}
    ${EndIf}
  ${EndIf}
!macroend
!endif

!macro customInit
  !ifndef INSTALL_MODE_PER_ALL_USERS
    !insertmacro WDA_CleanupGhostPerUserInstall
  !endif
  ; Custom pages do not run for /S. Validate /D before the install section so a
  ; current-user install cannot leave registry entries or shortcuts for an
  ; unwritable directory. The non-admin /allusers outer process must reach the
  ; install section first because electron-builder performs its UAC handoff there.
  IfSilent 0 WDA_CustomInitDone
  ${If} $installMode == "all"
  ${AndIfNot} ${UAC_IsAdmin}
    Goto WDA_CustomInitDone
  ${EndIf}
  Call WDA_EnsureAppSubDir
  Call WDA_ValidateInstallDir
  Pop $0
  ${If} $0 != "0"
    SetErrorLevel 2
    Quit
  ${EndIf}
  Call WDA_RemoveLegacyOutputLink
WDA_CustomInitDone:
!macroend

!macro customInstall
  ${If} $WDA_SelectedOutputDir == ""
    Call WDA_InitOutputDirSelection
  ${EndIf}
  Call WDA_WritePendingOutputDirSetting
!macroend

Function WDA_RemoveLegacyOutputLink
  Call WDA_UseCurrentUserAppData
  Call WDA_PrepareOutputDirScript
  ; $INSTDIR is usually the full install directory. Be defensive and also inspect the nested path
  ; in case the installer is running before electron-builder appends "\${APP_FILENAME}".
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\wda-output-dir.ps1" -Mode RemoveLegacyLinks -DefaultSettingsPath "${WDA_DEFAULT_SETTINGS_PATH}" -DefaultOutputPath "${WDA_DEFAULT_OUTPUT_DIR}" -LegacySettingsPath1 "${WDA_PRODUCT_SETTINGS_PATH}" -LegacySettingsPath2 "${WDA_FILENAME_SETTINGS_PATH}" -CandidateLinkPath1 "$INSTDIR\output" -CandidateLinkPath2 "$INSTDIR\${APP_FILENAME}\output"'
  Pop $0
  Pop $1
  Call WDA_RestoreInstallShellContext
  ${If} $0 != "0"
    MessageBox MB_ICONSTOP|MB_OK "无法安全检查旧版 output 链接，安装已停止。$\r$\n$1"
    Abort
  ${EndIf}
FunctionEnd

Function WDA_PrepareOutputDirScript
  InitPluginsDir
  File /oname=$PLUGINSDIR\wda-output-dir.ps1 "${__FILEDIR__}\installer-output-dir.ps1"
FunctionEnd

Function WDA_PrepareInstallDirScript
  InitPluginsDir
  File /oname=$PLUGINSDIR\wda-install-dir.ps1 "${__FILEDIR__}\installer-install-dir.ps1"
FunctionEnd

Function WDA_ValidateInstallDir
  Call WDA_PrepareInstallDirScript
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\wda-install-dir.ps1" -Mode Validate -InstallDir "$INSTDIR"'
  Pop $0
  Pop $1
  ${If} $0 == "0"
    Push "0"
  ${Else}
    Push "1"
  ${EndIf}
FunctionEnd

Function WDA_UseCurrentUserAppData
  ; In all-users mode electron-builder switches $APPDATA to ProgramData, while
  ; Electron userData remains under the interactive user's Roaming profile.
  ; This include is parsed before electron-builder declares $installMode, so
  ; preserve the effective AppData path instead of referencing that variable.
  StrCpy $WDA_PreviousShellAppData "$APPDATA"
  SetShellVarContext current
FunctionEnd

Function WDA_RestoreInstallShellContext
  StrCmp $WDA_PreviousShellAppData "$APPDATA" WDA_RestoreInstallShellContextDone
  SetShellVarContext all
WDA_RestoreInstallShellContextDone:
  StrCpy $WDA_PreviousShellAppData ""
FunctionEnd

!macro customPageAfterChangeDir
  ; Add a confirmation page after the directory picker so users clearly see
  ; the final install location (includes the app sub-folder).
  !ifdef allowToChangeInstallationDirectory
    Page custom WDA_InstallDirPageCreate WDA_InstallDirPageLeave
    Page custom WDA_OutputDirPageCreate WDA_OutputDirPageLeave
  !endif
!macroend

Function WDA_InitOutputDirSelection
  Call WDA_UseCurrentUserAppData
  Call WDA_PrepareOutputDirScript
  StrCpy $WDA_SelectedOutputDir "${WDA_DEFAULT_OUTPUT_DIR}"
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\wda-output-dir.ps1" -Mode Read -DefaultSettingsPath "${WDA_DEFAULT_SETTINGS_PATH}" -DefaultOutputPath "${WDA_DEFAULT_OUTPUT_DIR}" -LegacySettingsPath1 "${WDA_PRODUCT_SETTINGS_PATH}" -LegacySettingsPath2 "${WDA_FILENAME_SETTINGS_PATH}"'
  Pop $0
  Pop $1
  ${If} $0 == "0"
  ${AndIf} $1 != ""
    StrCpy $WDA_SelectedOutputDir "$1"
  ${EndIf}
  Call WDA_RestoreInstallShellContext
FunctionEnd

Function WDA_WritePendingOutputDirSetting
  Call WDA_UseCurrentUserAppData
  Call WDA_PrepareOutputDirScript
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\wda-output-dir.ps1" -Mode Write -DefaultSettingsPath "${WDA_DEFAULT_SETTINGS_PATH}" -DefaultOutputPath "${WDA_DEFAULT_OUTPUT_DIR}" -SelectedOutputPath "$WDA_SelectedOutputDir" -LegacySettingsPath1 "${WDA_PRODUCT_SETTINGS_PATH}" -LegacySettingsPath2 "${WDA_FILENAME_SETTINGS_PATH}"'
  Pop $0
  Pop $1
  Call WDA_RestoreInstallShellContext
  ${If} $0 != "0"
    MessageBox MB_ICONSTOP|MB_OK "无法保存 output 目录设置。$\r$\n$1"
    Abort
  ${EndIf}
FunctionEnd

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
  Call WDA_ValidateInstallDir
  Pop $0
  ${If} $0 != "0"
    MessageBox MB_ICONSTOP|MB_OK "无法写入安装目录：$\r$\n$INSTDIR$\r$\n$\r$\n请选择有写入权限的目录；如需安装到受保护目录，请返回安装范围页选择“所有用户”并接受 UAC 授权。"
    Abort
  ${EndIf}

  ; Safety: older versions created an `output` junction inside the install
  ; directory. Only unlink it after the final directory passes preflight.
  Call WDA_RemoveLegacyOutputLink
FunctionEnd

Function WDA_OutputDirBrowse
  nsDialogs::SelectFolderDialog "选择 output 目录" "$WDA_SelectedOutputDir"
  Pop $0
  ${If} $0 != error
    StrCpy $WDA_SelectedOutputDir "$0"
    ${NSD_SetText} $WDA_OutputDirInput "$0"
  ${EndIf}
FunctionEnd

Function WDA_OutputDirPageCreate
  Call WDA_InitOutputDirSelection

  ; If the user already moved output away from the default AppData location,
  ; keep that choice silently on install/update. Only show this migration prompt
  ; while the effective output directory is still the default.
  ${If} $WDA_SelectedOutputDir != "${WDA_DEFAULT_OUTPUT_DIR}"
    Abort
  ${EndIf}

  nsDialogs::Create 1018
  Pop $WDA_OutputDirPage

  ${If} $WDA_OutputDirPage == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0u 0u 100% 24u "请选择 output 目录（保存解密数据库、导出内容、缓存、日志等）。"
  Pop $0

  ${NSD_CreateText} 0u 28u 78% 12u "$WDA_SelectedOutputDir"
  Pop $WDA_OutputDirInput

  ${NSD_CreateButton} 82% 27u 18% 14u "浏览..."
  Pop $WDA_OutputDirBrowseButton
  ${NSD_OnClick} $WDA_OutputDirBrowseButton WDA_OutputDirBrowse

  ${NSD_CreateLabel} 0u 52u 100% 28u "安装器只记录你的选择；真正的数据迁移会在首次启动应用时执行。若目标目录已有内容，应用会阻止切换并提示处理。"
  Pop $0

  nsDialogs::Show
FunctionEnd

Function WDA_OutputDirPageLeave
  ${NSD_GetText} $WDA_OutputDirInput $WDA_SelectedOutputDir
  ${If} $WDA_SelectedOutputDir == ""
    StrCpy $WDA_SelectedOutputDir "${WDA_DEFAULT_OUTPUT_DIR}"
  ${EndIf}
FunctionEnd

!endif

!ifdef BUILD_UNINSTALLER
!include nsDialogs.nsh
!include LogicLib.nsh

Var WDA_UninstallOptionsPage
Var WDA_UninstallDeleteDataCheckbox
Var /GLOBAL WDA_DeleteUserData

Function un.WDA_PrepareOutputDirScript
  InitPluginsDir
  File /oname=$PLUGINSDIR\wda-output-dir.ps1 "${__FILEDIR__}\installer-output-dir.ps1"
FunctionEnd

!macro customUnInit
  ; Default: keep user data (also applies to silent uninstall / update uninstall).
  StrCpy $WDA_DeleteUserData "0"

  ; Safety: if an older build created an `output` junction inside the install dir, remove it early so
  ; directory cleanup can't traverse it and delete the real per-user output folder.
  RMDir "$INSTDIR\output"
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

      IfFileExists "$INSTDIR\output-location.path" 0 WDA_SkipCustomOutputDelete
        Call un.WDA_PrepareOutputDirScript
        nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$PLUGINSDIR\wda-output-dir.ps1" -Mode DeleteCustom -DefaultOutputPath "${WDA_DEFAULT_OUTPUT_DIR}" -PathFile "$INSTDIR\output-location.path" -LegacyOutputPath1 "${WDA_PRODUCT_OUTPUT_DIR}" -LegacyOutputPath2 "${WDA_FILENAME_OUTPUT_DIR}"'
        Pop $0
        Pop $1
      WDA_SkipCustomOutputDelete:

      ${if} $installMode == "all"
        SetShellVarContext all
      ${endif}
    ${endif}
  ${endif}
!macroend

!endif
