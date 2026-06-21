param(
  [int]$Top = 25
)

$ErrorActionPreference = "SilentlyContinue"

$IgnoredPathPattern = '\\(\.git|node_modules|__pycache__|\.pytest_cache|\.wrangler|build|dist)(\\|$)'

function Test-AuditPath {
  param([string]$Path)
  return ($Path -notmatch $IgnoredPathPattern)
}

Write-Host "Mellow workspace audit"
Write-Host ""

Write-Host "Top directories by file count"
Get-ChildItem -Directory -Force |
  Where-Object { Test-AuditPath $_.FullName } |
  ForEach-Object {
    $count = (Get-ChildItem -LiteralPath $_.FullName -Recurse -Force -File |
      Where-Object { Test-AuditPath $_.FullName } |
      Measure-Object).Count
    [pscustomobject]@{ Name = $_.Name; Files = $count }
  } |
  Sort-Object Files -Descending |
  Select-Object -First $Top |
  Format-Table -AutoSize

Write-Host ""
Write-Host "Largest files"
Get-ChildItem -Recurse -Force -File |
  Where-Object { Test-AuditPath $_.FullName } |
  Sort-Object Length -Descending |
  Select-Object -First $Top FullName, Length |
  Format-Table -AutoSize

Write-Host ""
Write-Host "Longest source-like files"
Get-ChildItem -Recurse -Force -File -Include *.py,*.ts,*.js,*.c,*.h,*.mellow,*.mel |
  Where-Object { Test-AuditPath $_.FullName } |
  ForEach-Object {
    $lines = (Get-Content -LiteralPath $_.FullName | Measure-Object -Line).Lines
    [pscustomobject]@{ Path = $_.FullName; Lines = $lines }
  } |
  Sort-Object Lines -Descending |
  Select-Object -First $Top |
  Format-Table -AutoSize

Write-Host ""
Write-Host "Git status summary"
git status --short
