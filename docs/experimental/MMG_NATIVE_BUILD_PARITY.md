# MMG Native Build Parity Pack

v2.3.3 focuses on native parity work for the SDL2/OpenGL backend.

## Added

- Windows and Linux build scripts
- External GLSL shader files
- VBO sprite batch path
- Runtime bridge metadata for input/state callbacks
- Scene format bump to `MMGSCENE 3`

## Scene additions

- `SHADER`
- `BATCH_GROUP`
- `BRIDGE_EVENT`
- `BRIDGE_STATE`

## Notes

This pack improves native-source parity and export/runtime integration. It still depends on SDL2/OpenGL headers on the target machine for full native builds.
