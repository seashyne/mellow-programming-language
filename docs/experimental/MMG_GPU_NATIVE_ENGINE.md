# Mellow v2.3.0 MMG GPU-Native Engine

This pack adds a **real native MMG rendering backend** built with **SDL2 + OpenGL**.
It is not a mock canvas path: when the native engine is built and launched, the app runs in a native window and draws through OpenGL on the GPU.

## What is included
- Native backend source in `native/mmg_gpu/`
- Scene export bridge from `.mel` to `.mmgscene`
- CLI commands:
  - `mellow mmg status --json`
  - `mellow mmg export-native examples/mmg_render_core_demo.mel -o demo.mmgscene`
  - `mellow mmg build-native`
  - `mellow mmg run-native examples/mmg_render_core_demo.mel`
- Real GPU path features in this pack:
  - window + frame loop
  - clear color
  - camera transform
  - textured sprites (BMP via SDL_LoadBMP)
  - colored rect / circle / line
  - Escape-to-close event

## Why SDL2 + OpenGL
SDL2 gives a cross-platform native window loop for Windows/Linux, while OpenGL gives a real GPU draw path.
This is the shortest path from the current MMG spec model to a true native renderer.

## Build requirements on the target machine
- CMake 3.20+
- SDL2 development libraries
- OpenGL libraries/drivers

## Notes
- This environment did not include SDL2 development headers, so the engine source and build system were added, but the native binary was not compiled here.
- The existing Tk backend remains available for fallback and fast iteration.
- Text rendering in the GPU path is parsed into the scene format but not yet drawn; text is planned for the next pack.
