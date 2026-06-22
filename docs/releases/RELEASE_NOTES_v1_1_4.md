# MellowLang v1.1.4 — Release Notes

## Fixes
- **File / Storage API:** String literals now support common escape sequences (e.g. `\n`, `\t`, `\r`, `\\`, `\"`, `\'`, `\uXXXX`).
  This fixes cases where writing/reading text files produced literal `\n` instead of a new line.
- **Storage base folder checks:** `load_data()` and `file_read()` now emit a clearer error if the storage base folder is missing
  (create it first with `mkdir(".")`).

## Sandbox
- `allow_storage=false` now correctly disables all StorageCore commands.

