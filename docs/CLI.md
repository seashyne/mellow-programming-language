# MellowLang CLI (v2.9.6)

MellowLang ใช้ CLI แบบ subcommand เท่านั้น เพื่อให้คำสั่งชัดเจนและเหมาะกับ
terminal, editor และ CI

## คำสั่งหลัก
```bash
mellow run <file>
mellow run <file> --sandbox=finance
mellow run <file> --sandbox=data
mellow check <file>
mellow fmt [-w] [--check] <files...>
mellow init <dir> [--force]
mellow modules [--json]
mellow lsp
```

การเรียก `mellow <file>` ถูกถอดออกแล้ว ให้ใช้ `mellow run <file>` เสมอ


## Package Registry (v1.5.2)

```bash
mellow pkg serve --host 127.0.0.1 --port 8089
mellow pkg registry http://127.0.0.1:8089
mellow pkg login --username admin --password admin
mellow pkg search demo
mellow pkg publish mypkg --online
mellow pkg install mypkg --online
```
