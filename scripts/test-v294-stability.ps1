$ErrorActionPreference = "Stop"

Write-Host "Mellow 2.9.4 stability gates"

$env:PYTHONPATH = "src"
$python = (Get-Command python -ErrorAction Stop).Source
& $python -B -m mellowlang.cli.main release-gate --rounds 1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "All 2.9.4 stability gates passed."
