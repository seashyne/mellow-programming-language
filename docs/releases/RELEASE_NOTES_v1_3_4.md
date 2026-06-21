# Release Notes — MellowLang v1.3.4

Date: 2026-02-19

## Highlights

- **Secure Save System (standard)**
  - New built-ins: `save_init/save_set/save_get/save_commit/save_load/save_list/save_delete/save_clear`
  - Saves are stored in the **user data folder** (outside project) as `*.msav`
  - Save files are **encrypted** and **tamper-evident** (integrity check). If modified, load fails with `SAVE_TAMPERED`.

## Project mode permissions

Save is **deny-by-default** in project mode.

Enable via `mellow.json`:

```json
{
  "permissions": [
    "save",
    "save.max_slots:10",
    "save.max_bytes:1048576"
  ]
}
```

## Docs

- Updated `STDLIB_REFERENCE.md` and `MELLOWLANG_User_Manual.md` with the secure save API.

## Tests

- Added coverage for encrypted save: write/load, tamper detection, quota enforcement.
