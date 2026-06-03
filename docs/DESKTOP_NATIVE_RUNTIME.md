# Mellow Desktop Native Runtime

Mellow v2.1.8 introduces a deeper desktop runtime layer for Windows and Linux.

## What changed

- Desktop runtime now exposes a stable `native-ui-runtime` contract.
- UI/state/events live behind a dedicated runtime layer instead of being only a thin Tk launcher.
- Portable desktop bundles are generated without PyInstaller.
- Bundles include:
  - the Mellow desktop runtime source
  - the app source
  - launch scripts for Windows and Linux

## Commands

```bash
mellow desktop status
mellow desktop run src/main.mel
mellow desktop build src/main.mel --out dist/desktop
```

## Portable bundle output

A desktop bundle now looks like this:

```text
MyApp/
├─ app/
│  └─ src/
├─ runtime/
│  └─ src/mellowlang/
├─ run_app.py
├─ run_linux.sh
├─ run_windows.bat
└─ bundle.json
```

## Supported widgets

- label
- button
- input
- textarea
- checkbox
- select
- slider
- listbox
- menu / menu_item
- vstack / hstack / grid

## Notes

This pack removes the PyInstaller dependency from the default desktop build path.

The generated bundle is portable, but it still expects Python 3 and Tk to exist on the target machine.
It is not a fully native OS-compiled binary runtime yet.
