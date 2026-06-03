# MellowLang v1.2.5 Stable

## Summary
- Standardizes **Dev mode** vs **Project mode** file behavior.
- `print/show` supports multiple values (e.g. `print("loaded =", data)`).
- Adds regression tests for multi-value printing.

## Dev mode (no mellow.json)
- File APIs operate relative to the current working directory (CWD).
- `storage_dir(".")` is allowed.

## Project mode (has mellow.json)
- `file_*` APIs write inside the sandbox root: `<project_root>/<sandbox_root>/`.
- Host filesystem access uses `fs_*` APIs and is governed by allowlist permissions in `mellow.json`.

## Compatibility
- Stays within v1.x compatibility policy.
- PEP 440 version: `1.2.5`.
