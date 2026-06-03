@echo off
rem ============================================================
rem  MellowLang v2.3.4 — VS Code Extension Build
rem  Requirements: Node.js + vsce  (npm install -g @vscode/vsce)
rem ============================================================
set "THIS_DIR=%~dp0"
for %%I in ("%THIS_DIR%..\..") do set "ROOT=%%~fI"
set "EXT_DIR=%ROOT%\vscode-extension"

if not exist "%EXT_DIR%\package.json" (
    echo [ERROR] VS Code extension not found at %EXT_DIR%
    pause & exit /b 1
)

where vsce >nul 2>&1
if errorlevel 1 (
    echo [INFO] vsce not found — installing...
    npm install -g @vscode/vsce
)

pushd "%EXT_DIR%" >nul
echo [1/2] Installing extension dependencies...
npm install --quiet

echo [2/2] Packaging extension...
vsce package --out "%ROOT%\dist\mellowlang-2.3.4.vsix"
if errorlevel 1 ( echo [ERROR] vsce failed. & popd >nul & pause & exit /b 1 )

popd >nul
echo.
echo [OK] VS Code extension: dist\mellowlang-2.3.4.vsix
echo      Install: code --install-extension dist\mellowlang-2.3.4.vsix
pause
