@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem ============================================================
rem  MellowLang v2.3.4 — Windows Full Build Script
rem
rem  Produces (in dist\):
rem    mellow\                         — onedir  (fast startup)
rem    mellow_onefile.exe              — onefile (single portable .exe)
rem    MellowLang_Setup_2.3.4.exe      — Inno Setup installer (onedir)
rem    MellowLang_Setup_2.3.4_portable.exe — Inno Setup installer (onefile)
rem
rem  Requirements:
rem    Python 3.10+    — https://python.org
rem    PyInstaller     — auto-installed
rem    cmake + gcc     — optional, for mellowrt.exe (standalone C runtime)
rem    Inno Setup 6+   — optional, for .exe installers
rem                      https://jrsoftware.org/isinfo.php
rem
rem  Usage: double-click or run from repo root:
rem    packaging\windows\build_exe.bat
rem ============================================================

set "THIS_DIR=%~dp0"
for %%I in ("%THIS_DIR%..\..") do set "ROOT=%%~fI"
set "SPEC_ONEDIR=%ROOT%\packaging\pyinstaller\mellowlang_onedir.spec"
set "SPEC_ONEFILE=%ROOT%\packaging\pyinstaller\mellowlang_onefile.spec"
set "ISS_ONEDIR=%ROOT%\packaging\windows\mellowlang.iss"
set "ISS_ONEFILE=%ROOT%\packaging\windows\mellowlang_onefile.iss"
set "VERSION=2.3.4"

rem ── locate Python ─────────────────────────────────────────
set "PY=python"
for %%V in (313 312 311 310) do (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
        goto :py_found
    )
)
where python >nul 2>&1 || (
    echo [ERROR] Python 3.10+ not found. Download from https://python.org
    pause & exit /b 1
)
:py_found

echo.
echo ============================================================
echo  MellowLang v%VERSION% Windows Build
echo  ROOT: %ROOT%
echo  PY:   %PY%
echo ============================================================

pushd "%ROOT%" >nul

rem ── [1/5] Install Python package ──────────────────────────
echo.
echo [1/5] Installing MellowLang package...
"%PY%" -m pip install -e . --quiet
if errorlevel 1 ( echo [ERROR] pip install failed & goto :fail )
echo       Done.

rem ── [2/5] Install PyInstaller ─────────────────────────────
echo.
echo [2/5] Checking PyInstaller...
"%PY%" -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo       Installing PyInstaller...
    "%PY%" -m pip install pyinstaller --quiet
    if errorlevel 1 ( echo [ERROR] Could not install PyInstaller & goto :fail )
)
echo       OK.

rem ── [3/5] Build standalone C runtime (optional) ───────────
echo.
echo [3/5] Building standalone C runtime (mellowrt.exe)...
where cmake >nul 2>&1
if errorlevel 1 (
    echo       cmake not found — skipping mellowrt build.
    echo       Install MinGW + cmake for Python-free execution support.
) else (
    set "RT_BUILD=%ROOT%\native\standalone\build"
    rem Try MinGW first, fallback to default generator
    cmake -S native\standalone -B "!RT_BUILD!" -DCMAKE_BUILD_TYPE=Release -G "MinGW Makefiles" >nul 2>&1
    if errorlevel 1 (
        cmake -S native\standalone -B "!RT_BUILD!" -DCMAKE_BUILD_TYPE=Release >nul 2>&1
    )
    cmake --build "!RT_BUILD!" --config Release
    if errorlevel 1 (
        echo       [WARN] mellowrt build failed — continuing without it.
    ) else (
        echo       mellowrt.exe built OK.
    )
)

rem ── [4/5] PyInstaller — both builds ───────────────────────
echo.
echo [4/5] Building onedir ^(dist\mellow\^)...
"%PY%" -m PyInstaller "%SPEC_ONEDIR%" --clean --noconfirm
if errorlevel 1 ( echo [ERROR] onedir build failed & goto :fail )
echo       onedir OK: dist\mellow\mellow.exe

echo.
echo [4/5] Building onefile ^(dist\mellow_onefile.exe^)...
"%PY%" -m PyInstaller "%SPEC_ONEFILE%" --clean --noconfirm
if errorlevel 1 ( echo [ERROR] onefile build failed & goto :fail )
echo       onefile OK: dist\mellow_onefile.exe

rem ── [5/5] Inno Setup — both installers ────────────────────
echo.
echo [5/5] Checking Inno Setup...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe"      set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo       Inno Setup not found — skipping installer creation.
    echo       Download: https://jrsoftware.org/isinfo.php
    echo       Then re-run this script to build the .exe installers.
    goto :summary
)

echo       Building onedir installer...
"%ISCC%" "%ISS_ONEDIR%"
if errorlevel 1 ( echo [WARN] onedir installer failed ) else (
    echo       OK: dist\MellowLang_Setup_%VERSION%.exe
)

echo       Building onefile installer...
"%ISCC%" "%ISS_ONEFILE%"
if errorlevel 1 ( echo [WARN] onefile installer failed ) else (
    echo       OK: dist\MellowLang_Setup_%VERSION%_portable.exe
)

:summary
popd >nul
echo.
echo ============================================================
echo  Build summary:
if exist "%ROOT%\dist\mellow\mellow.exe"          echo   [OK] dist\mellow\mellow.exe          (onedir)
if exist "%ROOT%\dist\mellow_onefile.exe"          echo   [OK] dist\mellow_onefile.exe          (onefile)
if exist "%ROOT%\dist\MellowLang_Setup_%VERSION%.exe"          echo   [OK] dist\MellowLang_Setup_%VERSION%.exe
if exist "%ROOT%\dist\MellowLang_Setup_%VERSION%_portable.exe" echo   [OK] dist\MellowLang_Setup_%VERSION%_portable.exe
echo ============================================================
echo.
echo  Test: dist\mellow\mellow.exe --version
echo  Test: dist\mellow_onefile.exe --version
echo.
pause
exit /b 0

:fail
popd >nul
echo.
echo [FAIL] Build did not complete. See error above.
pause
exit /b 1
