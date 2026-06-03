# MellowLang v1.0.7 — Release Notes (2026-01-29)

## Highlights
- **Token-accurate columns**: parser now carries `col` per token for more precise `line:col` error pointers.
- **Modern syntax aliases** (recommended): `let/var`, `def`, `print`, `input` added as friendly aliases.
- **Storage refresh**:
  - System-managed base dir is `./mellow_saves` (auto-created on first storage use).
  - Subfolders are **not** auto-created; user should call `mkdir()` first.
  - Added file helpers with explicit **file modes**: `file_read`, `file_write`, `file_append`, `file_exists`, `file_delete`, `mkdir`.

## Notes
- This release is API/behavior tightening for CLI ↔ Compiler ↔ VM error locations and storage safety.
