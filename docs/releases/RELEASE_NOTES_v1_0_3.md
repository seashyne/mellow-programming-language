# Release Notes — MellowLang v1.0.3

## Highlights
- ✅ Pro internal structure: `compiler/`, `vm/`, `host/`
- ✅ Locked API between CLI ↔ Compiler ↔ VM (stable v1.x contract)
- ✅ Fixed CLI/runtime mismatch that caused `Compiler(host=...)` crash
- ✅ Added modern aliases:
  - `print(...)` (alias of `show(...)`)
  - `input(...)` (alias of `ask(...)`, sandbox gated)
- ✅ New docs:
  - `CAPABILITIES.md`
  - `STYLE_GUIDE.md`
  - `UPDATE_v1_0_3.md`
  - `ROADMAP.md`

## CLI
- Legacy: `mellow <file> [flags]`
- Modern: `mellow run/check/fmt/init/modules/lsp`

No breaking removals in v1.x.
