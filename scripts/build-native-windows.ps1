param(
    [string]$VsDevCmd = "",
    [string]$WindowsSdkVersion = "10.0.26100.0"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $VsDevCmd) {
    $candidates = @(
        "C:\Program Files\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat",
        "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat",
        "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            $VsDevCmd = $candidate
            break
        }
    }
}

if (-not $VsDevCmd -or -not (Test-Path -LiteralPath $VsDevCmd)) {
    throw "Could not find VsDevCmd.bat. Install Visual Studio Build Tools or pass -VsDevCmd."
}

$sdkBin = "C:\Program Files (x86)\Windows Kits\10\bin\$WindowsSdkVersion\x64"
$pathPrefix = ""
if (Test-Path -LiteralPath $sdkBin) {
    $pathPrefix = "set `"PATH=$sdkBin;%PATH%`" && "
}

$command = "call `"$VsDevCmd`" -arch=x64 -host_arch=x64 && $pathPrefix python setup.py build_ext --inplace --force"
cmd.exe /d /c $command

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

python -m mellowlang native status
