#!/usr/bin/env pwsh
$mellowExe = Join-Path $PSScriptRoot "bin/mellow.exe"
if (Test-Path -LiteralPath $mellowExe) {
    & $mellowExe @args
    exit $LASTEXITCODE
}
Write-Error "Mellow native executable not found: $mellowExe"
Write-Error "Build it with: cmake --build build\standalone-bench-release --config Release"
exit 1
