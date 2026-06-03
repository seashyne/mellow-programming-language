# Release Notes — MellowLang v1.0.3

## Highlights
- ✅ Fix packaging/installer issues: PyInstaller bundle path + CLI now supports subcommands.
- ✅ New CLI workflow: `run`, `check`, `fmt`, `init`, `modules`, `lsp`
- ✅ Updated examples to modern `.mellow/.fds` style
- ✅ Updated user manual + syntax reference

## CLI
- `mellow <script>` ยังใช้ได้ (compat) -> เทียบเท่า `mellow run <script>`

## Dev/Build
- Exposed `MODULE_ALLOWLIST` from host for tooling/docs (`mellow modules`)

