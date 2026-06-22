# Mellow v2.1.8 Native Desktop UI Runtime Pack

## Added

- Native-style desktop runtime facade for Windows/Linux
- Portable desktop bundle generation without PyInstaller
- Slider and listbox widgets
- Runtime/source vendoring into app bundles
- Bundle launchers for Linux and Windows

## Changed

- `mellow desktop build` now produces a portable bundle by default
- Desktop status reports `native-ui-runtime`

## Known limits

- Current backend remains Tk/ttk under the runtime facade
- Generated bundles still require Python + Tk on the target machine
- This is not a Win32/GTK/Qt compiled binary runtime yet
