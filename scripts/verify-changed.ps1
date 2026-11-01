param(
    [string]$Base = "HEAD",
    [switch]$ListOnly,
    [switch]$ByRoot
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$jobs = [ordered]@{
    workspace = @("python", "-m", "pytest", "tests/test_workspace_boundaries.py", "-q")
    native    = @("ctest", "--test-dir", "build/standalone-release", "-C", "Release", "--output-on-failure")
    nativePy  = @("python", "-m", "pytest", "tests/native", "-q")
    python    = @("python", "-m", "pytest", "tests/core", "tests/test_quality_gates.py", "-q")
    language  = @("python", "-m", "pytest", "tests/language", "-q")
    packages  = @("python", "-m", "pytest", "tests/test_v157_core_packages.py", "-q")
    benchmark = @("python", "benchmarks/run_all.py", "--profile", "quick")
}

function Get-JobsForPath {
    param([string]$Path)
    $normalized = $Path -replace "\\", "/"
    switch -Regex ($normalized) {
        '^tests/test_workspace_boundaries\.py$' { return @("workspace") }
        '^\.gitignore$'                         { return @("workspace") }
        '^tests/native/'                        { return @("native", "nativePy") }
        '^native/'                              { return @("native", "nativePy") }
        '^(spec|stdlib)/'                       { return @("native", "nativePy", "language") }
        '^src/mellowlang/vm/'                   { return @("native", "nativePy", "python") }
        '^src/mellowlang/'                      { return @("python", "language") }
        '^tests/core/'                          { return @("python") }
        '^tests/language/'                      { return @("language") }
        '^tests/'                               { return @("python", "nativePy", "language") }
        '^benchmarks/'                          { return @("benchmark") }
        '^(starter_packages|frameworks|mellow_packages|packages)/' { return @("packages") }
        '^(apps|docs|examples|project_template|sdk|plugin_sdk|vscode-extension|packaging)/' { return @() }
        '^(\.github|scripts)/'                  { return $jobs.Keys }
        '^(pyproject\.toml|setup\.py)$'         { return $jobs.Keys }
        default                                 { return @() }
    }
}

function Invoke-Git {
    param([string[]]$Arguments)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    $output = & git @Arguments 2>$null
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previous
    if ($code -ne 0) { throw "git $($Arguments -join ' ') failed (exit $code)" }
    @($output | Where-Object { $_ })
}

function Invoke-Job {
    param([string[]]$Command)
    $arguments = @($Command[1..($Command.Count - 1)])
    & $Command[0] @arguments
    return $LASTEXITCODE
}

$changed = Invoke-Git @("diff", "--name-only", $Base)
$changed += Invoke-Git @("ls-files", "--others", "--exclude-standard")
$changed = @($changed | Sort-Object -Unique)

if ($changed.Count -eq 0) {
    Write-Host "No changed files against $Base."
    return
}

$selected = @($changed | ForEach-Object { Get-JobsForPath $_ } | Sort-Object -Unique)

Write-Host "Changed files : $($changed.Count)"
if ($ByRoot) {
    $changed | ForEach-Object {
        $parts = $_ -split "/"
        if ($parts.Count -eq 1) { "(root)" } else { $parts[0] }
    } | Group-Object | Sort-Object Count -Descending | ForEach-Object {
        Write-Host ("  {0,6}  {1}" -f $_.Count, $_.Name)
    }
}
Write-Host "Affected jobs : $(if ($selected.Count) { $selected -join ', ' } else { 'none (docs-only change)' })"

if ($ListOnly) { return }

$failed = @()
foreach ($name in $selected) {
    Write-Host ""
    Write-Host "==> $($name): $($jobs[$name] -join ' ')"
    if ((Invoke-Job $jobs[$name]) -ne 0) { $failed += $name }
}

Write-Host ""
if ($failed.Count) {
    Write-Host "Failed jobs: $($failed -join ', ')"
    exit 1
}
Write-Host "All affected jobs passed."
