param(
    [string]$Prefix = "$env:LOCALAPPDATA\MellowLang\bin",
    [switch]$NoBuild,
    [switch]$NoPath,
    [switch]$Uninstall,
    [Alias("?", "h")]
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
if ([System.IO.Path]::IsPathRooted($Prefix)) {
    $Prefix = [System.IO.Path]::GetFullPath($Prefix)
} else {
    $Prefix = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Prefix))
}
$BuildDir = Join-Path $Root "build\standalone-release"
$ReleaseDir = Join-Path $BuildDir "Release"
$BuiltMellow = Join-Path $ReleaseDir "mellow.exe"
$BuiltMellowRt = Join-Path $ReleaseDir "mellowrt.exe"

if ($Help) {
    Write-Host "Usage: .\scripts\install-native.ps1 [-Prefix PATH] [-NoBuild] [-NoPath] [-Uninstall]"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\scripts\install-native.ps1"
    Write-Host "  .\scripts\install-native.ps1 -Prefix E:\tools\mellow\bin"
    Write-Host "  .\scripts\install-native.ps1 -NoBuild -NoPath -Prefix .\bin"
    Write-Host "  .\scripts\install-native.ps1 -Uninstall"
    exit 0
}

function Remove-FromUserPath([string]$PathToRemove) {
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $current) { return }
    $parts = $current -split ";" | Where-Object { $_ -and ($_ -ne $PathToRemove) }
    [Environment]::SetEnvironmentVariable("Path", ($parts -join ";"), "User")
}

function Add-ToFrontOfUserPath([string]$PathToAdd) {
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @()
    if ($current) {
        $parts = $current -split ";" | Where-Object { $_ -and ($_ -ne $PathToAdd) }
    }
    [Environment]::SetEnvironmentVariable("Path", ($PathToAdd + ";" + ($parts -join ";")).TrimEnd(";"), "User")
}

if ($Uninstall) {
    if (Test-Path -LiteralPath $Prefix) {
        Remove-Item -LiteralPath $Prefix -Recurse -Force
    }
    Remove-FromUserPath $Prefix
    Write-Host "Mellow native install removed from $Prefix"
    Write-Host "Open a new terminal for PATH changes to fully apply."
    exit 0
}

if (-not $NoBuild) {
    cmake -S (Join-Path $Root "native\standalone") -B $BuildDir -DCMAKE_BUILD_TYPE=Release
    cmake --build $BuildDir --config Release
}

if (-not (Test-Path -LiteralPath $BuiltMellow)) {
    throw "Native build output not found: $BuiltMellow"
}

New-Item -ItemType Directory -Force -Path $Prefix | Out-Null
Copy-Item -LiteralPath $BuiltMellow -Destination (Join-Path $Prefix "mellow.exe") -Force
if (Test-Path -LiteralPath $BuiltMellowRt) {
    Copy-Item -LiteralPath $BuiltMellowRt -Destination (Join-Path $Prefix "mellowrt.exe") -Force
}

if (-not $NoPath) {
    Add-ToFrontOfUserPath $Prefix
    $env:Path = $Prefix + ";" + (($env:Path -split ";" | Where-Object { $_ -and ($_ -ne $Prefix) }) -join ";")
}

Write-Host "Mellow native installed:"
Write-Host "  $Prefix\mellow.exe"
Write-Host ""
& (Join-Path $Prefix "mellow.exe") doctor
Write-Host ""
Write-Host "Next:"
Write-Host "  Open a new terminal, then run: mellow doctor"
