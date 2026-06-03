$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
$build = Join-Path $root "build"
cmake -S $root -B $build -DCMAKE_BUILD_TYPE=Release
cmake --build $build --config Release
Write-Host "Built $(Join-Path $build 'Release/mmg_gpu.exe')"
