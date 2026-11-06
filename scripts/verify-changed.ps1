param(
    [string]$Base = "HEAD",
    [string]$Only = "",
    [switch]$ListOnly,
    [switch]$ByRoot
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$checkJobs = [ordered]@{
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
        '^(\.github|scripts)/'                  { return $checkJobs.Keys }
        '^(pyproject\.toml|setup\.py)$'         { return $checkJobs.Keys }
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
    param([string]$Name)
    $command = $script:checkJobs[$Name]
    $executable = $command[0]
    if (-not (Get-Command $executable -CommandType Application -ErrorAction SilentlyContinue) -and
        -not (Get-Command $executable -ErrorAction SilentlyContinue)) {
        Write-Host "    '$executable' is not available, so this job could not run."
        return $true
    }
    $arguments = @($command[1..($command.Count - 1)])
    # Piping keeps the child output on the host so only the boolean reaches the caller.
    & $executable @arguments | Out-Host
    return ($LASTEXITCODE -ne 0)
}

$changed = Invoke-Git @("diff", "--name-only", $Base)
$changed += Invoke-Git @("ls-files", "--others", "--exclude-standard")
$changed = @($changed | Sort-Object -Unique)

if ($changed.Count -eq 0) {
    Write-Host "No changed files against $Base."
    return
}

$wanted = @{}
foreach ($path in $changed) {
    foreach ($name in Get-JobsForPath $path) {
        if ($name) { $wanted[$name] = $true }
    }
}
# Keep the declared order so cheap gates run before the benchmark job.
$selected = @($checkJobs.Keys | Where-Object { $wanted[$_] })

$onlyNames = @($Only -split "[,; ]+" | Where-Object { $_ })
if ($onlyNames.Count) {
    $unknown = @($onlyNames | Where-Object { -not $checkJobs.Contains($_) })
    if ($unknown.Count) {
        throw "Unknown job(s): $($unknown -join ', '). Known: $($checkJobs.Keys -join ', ')"
    }
    $selected = @($selected | Where-Object { $onlyNames -contains $_ })
}

Write-Host "Changed files : $($changed.Count)"
if ($ByRoot) {
    $changed | ForEach-Object {
        $parts = $_ -split "/"
        if ($parts.Count -eq 1) { "(root)" } else { $parts[0] }
    } | Group-Object | Sort-Object Count -Descending | ForEach-Object {
        Write-Host ("  {0,6}  {1}" -f $_.Count, $_.Name)
    }
}
Write-Host "Affected jobs : $(if ($selected.Count) { $selected -join ', ' } else { 'none' })"

if ($ListOnly) { return }

$failed = @()
foreach ($name in $selected) {
    Write-Host ""
    Write-Host "==> $($name): $($checkJobs[$name] -join ' ')"
    if (Invoke-Job $name) { $failed += $name }
}

Write-Host ""
if ($failed.Count) {
    Write-Host "Failed jobs: $($failed -join ', ')"
    exit 1
}
Write-Host "All affected jobs passed."
