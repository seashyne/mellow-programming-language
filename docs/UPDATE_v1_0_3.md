# MellowLang v1.0.3 Update Notes

## What changed

### 1) Internal structure (pro layout)
We moved implementation details into packages:

- `mellowlang/compiler/` – stable compiler facade + legacy implementation
- `mellowlang/vm/` – stable VM facade + legacy implementation
- `mellowlang/host/` – stable host API + allowlist

Compatibility shims remain:

- `mellowlang/compiler.py`, `mellowlang/vm.py`, `mellowlang/host.py`

So imports keep working while the internal layout is cleaner.

### 2) Locked API (CLI ↔ Compiler ↔ VM)

Stable contract for v1.x:

- `Compiler().compile(source: str, *, filename=None) -> CompiledProgram`
- `MellowVM().run(program: CompiledProgram, *, config: RunConfig) -> Any`

CLI only depends on these two contracts.

### 3) Syntax modern aliases
- `print(expr)` is an alias of `show(expr)`
- `input(prompt)` is an alias of `ask(prompt)`

We keep older forms but the docs recommend the modern ones.

### 4) CLI policy
- Legacy usage is supported: `mellow <file> [flags]`
- Modern commands are supported: `mellow run/check/fmt/init/modules/lsp`
- No breaking removals in v1.x (only additive)
