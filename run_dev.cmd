@echo off
setlocal

set "REPO_DIR=%~dp0"
set "REPO_DIR=%REPO_DIR:~0,-1%"
set "UV_DIR=C:\Users\shierqi\AppData\Local\WeChatDataAnalysis\dev-tools\uv\Scripts"
set "NODE_DIR=D:\soft\Node\node-v24.15.0-win-x64"

if not exist "%REPO_DIR%\desktop\package.json" (
    echo Project not found: "%REPO_DIR%"
    pause
    exit /b 1
)

if not exist "%UV_DIR%\uv.exe" (
    echo uv not found: "%UV_DIR%\uv.exe"
    pause
    exit /b 1
)

if not exist "%NODE_DIR%\npm.cmd" (
    echo npm not found: "%NODE_DIR%\npm.cmd"
    pause
    exit /b 1
)

set "PATH=%UV_DIR%;%NODE_DIR%;%PATH%"
cd /d "%REPO_DIR%\desktop"

echo Starting WeChatDataAnalysis desktop development mode...
echo Close with Ctrl+C in this window.
echo.

call npm.cmd run dev
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo Development process exited with code %EXIT_CODE%.
pause
endlocal & exit /b %EXIT_CODE%