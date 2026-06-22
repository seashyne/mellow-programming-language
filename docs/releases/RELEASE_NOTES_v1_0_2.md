# Release Notes — v1.0.3

## Highlights
- ✅ คืน CLI “แบบเดิม” (Frinds-style): `mellow <script> [options]` + help แบบคุ้นเคย
- ✅ เพิ่มความสามารถใหม่ใน CLI legacy:
  - `--check` ตรวจ syntax/lint โดยไม่รัน
  - `--modules` แสดงรายการ host modules ที่อนุญาต
- ✅ คง CLI แบบใหม่ (subcommands) ไว้เพื่อ tooling: `run/check/fmt/init/modules/lsp`
- ✅ เพิ่มเอกสาร:
  - `docs/CLI.md`
  - `docs/CAPABILITIES.md`

## Compatibility Notes
- `--engine` และ `--legacy` ถูกเก็บไว้เป็น compat flags (ไม่ทำให้สคริปต์เก่าพัง)
- ปัจจุบัน MellowLang ใช้ VM เป็นค่าเริ่มต้น
