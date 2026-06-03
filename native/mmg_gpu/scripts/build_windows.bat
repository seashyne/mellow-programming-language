@echo off
setlocal
set ROOT_DIR=%~dp0\..
set BUILD_DIR=%ROOT_DIR%uild
cmake -S "%ROOT_DIR%" -B "%BUILD_DIR%" -DCMAKE_BUILD_TYPE=Release
if errorlevel 1 exit /b 1
cmake --build "%BUILD_DIR%" --config Release
if errorlevel 1 exit /b 1
echo Built %BUILD_DIR%\Release\mmg_gpu.exe
