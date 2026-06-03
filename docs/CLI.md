# MellowLang CLI (v1.0.3)

MellowLang v1.0.3 คืน **CLI แบบเดิม** (Frinds-style) และยังคง **CLI แบบใหม่ (subcommands)** ไว้ด้วย

## 1) Legacy-compatible mode (เหมือนเดิม)
รูปแบบ:
- `mellow <script> [options...]`
- `mellow --lsp`
- `mellow --modules`

ตัวอย่าง:
```bash
mellow examples/hello.mellow
mellow examples/hello.mellow --seed 123 --record out.jsonl
mellow examples/events.fds --emit Spawn --emit-args "["p1",10]"
mellow --check examples/loops.mellow
mellow --lsp
```

Options สำคัญ:
- `--lsp` เริ่ม Language Server
- `--emit/--emit-args` emit event หลังรันจบ
- `--record/--replay` deterministic replay
- `--seed/--global-seed` ควบคุม randomness
- `--color/--no-color` สี error
- `--json` output แบบเครื่องอ่านได้
- `--engine/--legacy` (compat) คงไว้เพื่อความคุ้นเคย

## 2) Modern subcommands (แนะนำสำหรับ tooling)
```bash
mellow run <file>
mellow check <file>
mellow fmt [-w] [--check] <files...>
mellow init <dir> [--force]
mellow modules [--json]
mellow lsp
```

## 3) ความเข้ากันได้
- ถ้า arg แรกเป็น `run/check/fmt/init/modules/lsp` → ใช้โหมดใหม่
- อย่างอื่น → ใช้โหมดเดิมอัตโนมัติ


## Package Registry (v1.5.2)

```bash
mellow pkg serve --host 127.0.0.1 --port 8089
mellow pkg registry http://127.0.0.1:8089
mellow pkg login --username admin --password admin
mellow pkg search demo
mellow pkg publish mypkg --online
mellow pkg install mypkg --online
```
