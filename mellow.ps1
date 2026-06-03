#!/usr/bin/env pwsh
$env:PYTHONPATH = "$PSScriptRoot/src" + [IO.Path]::PathSeparator + ($env:PYTHONPATH ?? "")
py -3 "$PSScriptRoot/main.py" @args
