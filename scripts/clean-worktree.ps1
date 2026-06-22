param(
    [switch]$Apply
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$exactTargets = @(
    ".mellow",
    ".mellow-release-gate-work",
    ".tmp",
    ".tmp_money_finance_test",
    ".tmp_data_core_test",
    "build",
    "mellow_models",
    "mellow_saves",
    ".mellow_aliases.json",
    ".mellow_imports.json",
    ".mellow_runtime.json"
)

$targets = foreach ($name in $exactTargets) {
    Get-Item -LiteralPath (Join-Path $repoRoot $name) -Force -ErrorAction SilentlyContinue
}
$targets += Get-ChildItem -LiteralPath $repoRoot -Force -ErrorAction Stop |
    Where-Object { $_.Name -like ".mellow-data-benchmark-*" -or $_.Name -like "mellow-*-check.exe" }
$targets = @($targets | Sort-Object FullName -Unique)

if ($targets.Count -eq 0) {
    Write-Host "Mellow workspace is already clean."
    exit 0
}

$rootPrefix = $repoRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
foreach ($target in $targets) {
    if (-not $target.FullName.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean outside the repository: $($target.FullName)"
    }

    if ($Apply) {
        Remove-Item -LiteralPath $target.FullName -Recurse -Force
        Write-Host "removed  $($target.Name)"
    } else {
        Write-Host "preview  $($target.Name)"
    }
}

if (-not $Apply) {
    Write-Host "Run scripts/clean-worktree.ps1 -Apply to remove these generated files."
}
