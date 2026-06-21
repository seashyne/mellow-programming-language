# Release Notes v2.3.0 — MMG GPU-Native Engine

## Added
- Native MMG GPU backend source in `native/mmg_gpu/`
- SDL2 + OpenGL render path
- Scene export bridge `.mel -> .mmgscene`
- CLI support for `mellow mmg build-native`, `export-native`, and `run-native`
- Python module `mellowlang.mmg_gpu_runtime`

## Honest status
- Added a real GPU-native backend source tree and CLI integration.
- The native backend was not built in this environment because SDL2 development headers were unavailable here.
- Tk MMG runtime is still present as a fallback.
