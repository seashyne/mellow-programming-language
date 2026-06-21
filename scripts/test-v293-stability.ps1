$ErrorActionPreference = "Stop"

Write-Host "Mellow 2.9.3 stability gates"

$env:PYTHONPATH = "src"
py -3.11 -m mellowlang.cli.main release-gate --rounds 1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "All 2.9.3 stability gates passed."
