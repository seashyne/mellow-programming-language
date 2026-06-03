@echo off
setlocal
set "MELLOW_ROOT=%~dp0"
py -3 "%MELLOW_ROOT%main.py" %*
