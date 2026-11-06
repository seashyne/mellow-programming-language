param(
    [string]$Version = "",
    [ValidateSet("windows-x64", "windows-arm64")]
    [string]$Target = "windows-x64",
    [string]$BuildDir = "",
    [string]$DistDir = "dist",
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $Version) {
    try {
        $VersionText = Get-Content -LiteralPath (Join-Path $Root "src\mellowlang\__init__.py") -Raw
        if ($VersionText -match "__version__\s*=\s*['""]([^'""]+)['""]") {
            $Version = $Matches[1]
        } else {
            $Version = "dev"
        }
    } catch {
        $Version = "dev"
    }
}

if (-not $BuildDir) {
    $BuildDir = Join-Path $Root "build\standalone-release-$Target"
}

$CmakeArch = if ($Target -eq "windows-arm64") { "ARM64" } else { "x64" }
$ReleaseDir = Join-Path $BuildDir "Release"
$Mellow = Join-Path $ReleaseDir "mellow.exe"
$MellowRt = Join-Path $ReleaseDir "mellowrt.exe"

if (-not $NoBuild) {
    cmake -S (Join-Path $Root "native\standalone") -B $BuildDir -A $CmakeArch -DCMAKE_BUILD_TYPE=Release
    cmake --build $BuildDir --config Release --parallel 2
}

if (-not (Test-Path -LiteralPath $Mellow)) {
    throw "native build output not found: $Mellow"
}

$Pkg = "mellow-$Version-$Target"
$PkgRoot = Join-Path $Root (Join-Path $DistDir $Pkg)
$BinDir = Join-Path $PkgRoot "bin"
$ShareDir = Join-Path $PkgRoot "share\mellow"
if (Test-Path -LiteralPath $PkgRoot) {
    Remove-Item -LiteralPath $PkgRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
New-Item -ItemType Directory -Force -Path $ShareDir | Out-Null

Copy-Item -LiteralPath $Mellow -Destination (Join-Path $BinDir "mellow.exe") -Force
if (Test-Path -LiteralPath $MellowRt) {
    Copy-Item -LiteralPath $MellowRt -Destination (Join-Path $BinDir "mellowrt.exe") -Force
}
Copy-Item -LiteralPath (Join-Path $Root "LICENSE") -Destination (Join-Path $PkgRoot "LICENSE") -Force
Copy-Item -LiteralPath (Join-Path $Root "NOTICE.md") -Destination (Join-Path $PkgRoot "NOTICE.md") -Force
Copy-Item -LiteralPath (Join-Path $Root "README.md") -Destination (Join-Path $PkgRoot "README.md") -Force
Copy-Item -LiteralPath (Join-Path $Root "docs\INSTALL.md") -Destination (Join-Path $PkgRoot "INSTALL.md") -Force
Copy-Item -LiteralPath (Join-Path $Root "scripts\install-native.ps1") -Destination (Join-Path $PkgRoot "install-native.ps1") -Force
Copy-Item -LiteralPath (Join-Path $Root "starter_packages") -Destination (Join-Path $ShareDir "starter_packages") -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $ShareDir "mellow_packages") | Out-Null
Copy-Item -LiteralPath (Join-Path $Root "mellow_packages\registry") -Destination (Join-Path $ShareDir "mellow_packages\registry") -Recurse -Force
Get-ChildItem -LiteralPath $ShareDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

$Manifest = [ordered]@{
    name = "mellow"
    version = $Version
    target = $Target
    runtime = "standalone-c"
    binaries = @("bin/mellow.exe", "bin/mellowrt.exe")
    packages = @("share/mellow/starter_packages", "share/mellow/mellow_packages/registry")
}
$Manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $PkgRoot "manifest.json") -Encoding UTF8

$Archive = Join-Path $Root (Join-Path $DistDir "$Pkg.zip")
Compress-Archive -Path (Join-Path $PkgRoot "*") -DestinationPath $Archive -Force

$Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
"$Hash  $(Split-Path -Leaf $Archive)" | Set-Content -LiteralPath (Join-Path $Root (Join-Path $DistDir "$Pkg.SHA256SUMS")) -Encoding ASCII

Write-Host "release archive: $Archive"
Write-Host "sha256: $Hash"
