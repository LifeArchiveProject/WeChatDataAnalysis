; This file is included for both installer and uninstaller builds.
; Guard installer-only pages/functions to avoid "function not referenced" warnings
; when electron-builder compiles the standalone uninstaller.
!define /ifndef WDA_DEFAULT_SETTINGS_PATH "$APPDATA\${APP_FILENAME}\desktop-settings.json"
!define /ifndef WDA_DEFAULT_OUTPUT_DIR "$APPDATA\${APP_FILENAME}\output"
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

!macro customInit
  ; Safety: older versions created an `output` junction inside the install directory that points to the
  ; per-user AppData `output` folder. Some uninstall/update flows may traverse that junction and delete
  ; real user data. Remove it as early as possible during install/update.
  Call WDA_RemoveLegacyOutputLink
!macroend

!macro customInstall
  ${If} $WDA_SelectedOutputDir == ""
    Call WDA_InitOutputDirSelection
  ${EndIf}
  Call WDA_WritePendingOutputDirSetting
!macroend

Function WDA_RemoveLegacyOutputLink
  ; $INSTDIR is usually the full install directory. Be defensive and also try the nested path
  ; in case the installer is running before electron-builder appends "\${APP_FILENAME}".
  RMDir "$INSTDIR\output"
  RMDir "$INSTDIR\${APP_FILENAME}\output"
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
  StrCpy $WDA_SelectedOutputDir "${WDA_DEFAULT_OUTPUT_DIR}"
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -Command "& { param([string] $$defaultSettingsPath, [string] $$defaultOutputPath, [string] $$legacySettingsPath1, [string] $$legacySettingsPath2) $$candidates = @($$defaultSettingsPath, $$legacySettingsPath1, $$legacySettingsPath2) | Where-Object { -not [string]::IsNullOrWhiteSpace($$_) } | Select-Object -Unique; $$settingsPath = $$defaultSettingsPath; foreach ($$candidate in $$candidates) { if (Test-Path -LiteralPath $$candidate) { $$settingsPath = $$candidate; break } }; $$result = $$defaultOutputPath; if (Test-Path -LiteralPath $$settingsPath) { try { $$json = Get-Content -LiteralPath $$settingsPath -Raw | ConvertFrom-Json; $$value = [string] $$json.pendingOutputDir; if ([string]::IsNullOrWhiteSpace($$value)) { $$value = [string] $$json.outputDir }; if ($$value -eq '''') { $$result = $$defaultOutputPath } elseif (-not [string]::IsNullOrWhiteSpace($$value)) { $$result = $$value } } catch {} }; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; [Console]::Write($$result) }" "${WDA_DEFAULT_SETTINGS_PATH}" "${WDA_DEFAULT_OUTPUT_DIR}" "${WDA_PRODUCT_SETTINGS_PATH}" "${WDA_PACKAGE_SETTINGS_PATH}"'
  Pop $0
  Pop $1
  ${If} $0 == "0"
  ${AndIf} $1 != ""
    StrCpy $WDA_SelectedOutputDir "$1"
  ${EndIf}
FunctionEnd

Function WDA_WritePendingOutputDirSetting
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -Command "& { param([string] $$defaultSettingsPath, [string] $$defaultOutputPath, [string] $$selectedOutputPath, [string] $$legacySettingsPath1, [string] $$legacySettingsPath2) $$candidates = @($$defaultSettingsPath, $$legacySettingsPath1, $$legacySettingsPath2) | Where-Object { -not [string]::IsNullOrWhiteSpace($$_) } | Select-Object -Unique; $$sourceSettingsPath = $$defaultSettingsPath; foreach ($$candidate in $$candidates) { if (Test-Path -LiteralPath $$candidate) { $$sourceSettingsPath = $$candidate; break } }; if ([string]::IsNullOrWhiteSpace($$selectedOutputPath)) { $$selectedOutputPath = $$defaultOutputPath }; $$pending = if ([string]::Equals($$selectedOutputPath, $$defaultOutputPath, [System.StringComparison]::OrdinalIgnoreCase)) { '''' } else { $$selectedOutputPath }; $$obj = @{}; if (Test-Path -LiteralPath $$sourceSettingsPath) { try { $$existing = Get-Content -LiteralPath $$sourceSettingsPath -Raw | ConvertFrom-Json; if ($$null -ne $$existing) { $$existing.PSObject.Properties | ForEach-Object { $$obj[$$_.Name] = $$_.Value } } } catch {} }; $$obj[''pendingOutputDir''] = $$pending; $$dir = Split-Path -Parent $$defaultSettingsPath; New-Item -ItemType Directory -Force -Path $$dir | Out-Null; $$json = [PSCustomObject] $$obj | ConvertTo-Json -Depth 10; Set-Content -LiteralPath $$defaultSettingsPath -Value $$json -Encoding UTF8 }" "${WDA_DEFAULT_SETTINGS_PATH}" "${WDA_DEFAULT_OUTPUT_DIR}" "$WDA_SelectedOutputDir" "${WDA_PRODUCT_SETTINGS_PATH}" "${WDA_PACKAGE_SETTINGS_PATH}"'
  Pop $0
  Pop $1
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
        nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -Command "& { param([string] $$pathFile, [string] $$defaultPath1, [string] $$defaultPath2, [string] $$defaultPath3) if (Test-Path -LiteralPath $$pathFile) { $$target = (Get-Content -LiteralPath $$pathFile -Raw).Trim(); $$defaults = @($$defaultPath1, $$defaultPath2, $$defaultPath3) | Where-Object { -not [string]::IsNullOrWhiteSpace($$_) }; $$isDefault = $$false; foreach ($$defaultPath in $$defaults) { if ([string]::Equals($$target, $$defaultPath, [System.StringComparison]::OrdinalIgnoreCase)) { $$isDefault = $$true; break } }; if (-not $$isDefault -and -not [string]::IsNullOrWhiteSpace($$target) -and (Test-Path -LiteralPath $$target)) { Remove-Item -LiteralPath $$target -Recurse -Force -ErrorAction SilentlyContinue } } }" "$INSTDIR\output-location.path" "${WDA_DEFAULT_OUTPUT_DIR}" "${WDA_PRODUCT_OUTPUT_DIR}" "${WDA_PACKAGE_OUTPUT_DIR}"'
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
