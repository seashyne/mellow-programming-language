@echo off
setlocal
set "MELLOW_ROOT=%~dp0"
set "MELLOW_EXE=%MELLOW_ROOT%bin\mellow.exe"
if exist "%MELLOW_EXE%" (
  "%MELLOW_EXE%" %*
  exit /b %ERRORLEVEL%
)
echo Mellow native executable not found: %MELLOW_EXE% 1>&2
echo Build it with: cmake --build build\standalone-bench-release --config Release 1>&2
exit /b 1
