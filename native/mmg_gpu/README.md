# MMG GPU Native Backend

This backend uses SDL2 + OpenGL and now ships with:

- VBO-based sprite batching
- External GLSL shader files
- PNG/JPG loading when SDL2_image is available
- Runtime bridge callbacks for input/state sync
- Windows/Linux build scripts in `scripts/`

## Build

Linux:

```bash
./scripts/build_linux.sh
```

Windows CMD:

```bat
scripts\build_windows.bat
```

Windows PowerShell:

```powershell
./scripts/build_windows.ps1
```
