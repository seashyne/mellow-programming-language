<p align="center">
  <img src="docs/assets/mellow-logo.png" alt="Mellow logo" width="96">
</p>

# Mellow Programming Language 2.9.6

Mellow Programming Language, also known as MellowLang, is a sandbox scripting language focused on games, tools, and AI behavior experiments.

This release treats the language core as the stable surface:

- `let` / assignment
- `def` functions
- `if`, `while`, and `for`
- `range(...)`
- list and map literals
- string/math/list/map/json/money/data/ledger helpers
- `mellow run`, `mellow check`, `mellow fmt`, `mellow modules`, and `mellow doctor`

Larger systems such as agents, MMG, desktop bundles, package registries, and MELV video tools are available, but are documented as **experimental** under [`docs/experimental/README.md`](docs/experimental/README.md). In v2.9.6 the standalone `mellow` executable includes a C lexer, compiler, bytecode runtime, native terminal/system built-ins, builtin module aliases, and the first native GC/concurrency foundation APIs. Debugger, events, record/replay, package tooling, LSP, and extended services remain optional Python tooling.

## Quick Start

Fresh Windows install from Git:

```powershell
git clone https://github.com/seashyne/mellow-programming-language.git
cd mellow-programming-language
.\scripts\install-native.ps1
mellow doctor
mellow run examples\hello.mellow
mellow check examples\hello.mellow
```

Fresh Linux/macOS install from Git:

```bash
git clone https://github.com/seashyne/mellow-programming-language.git
cd mellow-programming-language
sh scripts/install-native.sh --add-path
export PATH="$HOME/.local/bin:$PATH"
mellow doctor
mellow run examples/hello.mellow
mellow check examples/hello.mellow
```

From an existing source checkout, install the native C CLI first:

```powershell
.\scripts\install-native.ps1
mellow doctor
mellow run examples\hello.mellow
mellow check examples\hello.mellow
```

On Linux/macOS:

```bash
sh scripts/install-native.sh --add-path
mellow doctor
mellow run examples/hello.mellow
mellow check examples/hello.mellow
```

If you prefer npm after cloning the repository:

```bash
npm install -g ./packages/npm/mellowlang
mellow doctor
```

Native C is the default execution engine. The native `mellow` executable runs
without Python and reports `Python: not required` in `mellow doctor`. New runtime
work should land in `native/standalone` first.

The native runtime is also starting to expose an experimental embeddable C API.
For now, standalone C remains the main supported path; `mellow_runtime.h` is a
provisional wrapper for trying host embedding before the runtime ABI is marked
stable.

Without installing the Python package, build and run the standalone native
runtime:

```powershell
cmake -S native\standalone -B native\standalone\build
cmake --build native\standalone\build
native\standalone\build\Debug\mellow.exe examples\hello.mellow
```

Full install guide: [`docs/INSTALL.md`](docs/INSTALL.md)

Python module entry points remain available for development tooling:

```powershell
$env:PYTHONPATH = "src"
python -m mellowlang --version
python -m mellowlang run examples\hello.mellow
```

คู่มือ syntax ฉบับเต็ม: [`docs/SYNTAX_REFERENCE.md`](docs/SYNTAX_REFERENCE.md)

คู่มือ Mellow SDK (Python vs Mellow): [`docs/MELLOW_SDK.md`](docs/MELLOW_SDK.md)

ข้อกำหนดภาษา 2.9 ที่ล็อกแล้ว: [`docs/LANGUAGE_SPEC_2_9.md`](docs/LANGUAGE_SPEC_2_9.md)

คู่มือติดตั้ง editor และ LSP: [`docs/LSP.md`](docs/LSP.md)

ตัวอย่างรวมที่รันได้:

```powershell
mellow run tests\fixtures\full_native_core.mellow
```

## Example

```mellow
let score = 0

def add(a, b):
    return a + b

for i in range(0, 6):
    score = add(score, i)

print(score)
```

Run it:

```powershell
mellow run my_script.mellow
```

Money-safe rules:

```mellow
let subtotal = money("0.10", "THB")
let fee = money("0.20", "THB")
let total = money_add(subtotal, fee)
print(money_format(total))  # THB 0.30
```

Run finance-style scripts with a tighter sandbox:

```powershell
mellow run rules.mellow --sandbox=finance
```

Process JSONL/CSV in bounded batches:

```mellow
let stream = data_open_jsonl("records.jsonl", 1000)
let batch = data_next(stream)
while len(batch) > 0:
    let sales = data_where(batch, "kind", "==", "sale")
    print(data_sum(sales, "amount"))
    batch = data_next(stream)
```

Use `--sandbox=data` for read-oriented data jobs. Add `--data-write` only when parameterized SQLite writes are required.

Finance and data sandbox profiles, plus Ledger Core, run on the default C engine
in v2.9.6. Native parity tests run in native-only mode.

Native runtime foundation APIs:

```mellow
gc_collect()
let stats = gc_stats()

def worker():
    return 1

let task = spawn(worker)
yield()

let ch = channel()
send(ch, "hello")
print(recv(ch))
```

These APIs are native C built-ins in v2.9.6. They provide a truthful foundation
for GC accounting, cooperative task handles, explicit yield points, and FIFO
channels. Full tracing GC and full M:N stack-switching scheduling remain runtime
engine work rather than being claimed as complete.

Build an immutable, balanced ledger:

```mellow
let book = ledger_create("THB")
book = ledger_post(
    book,
    "sale-001",
    [
        {"account": "cash", "amount": "100.00"},
        {"account": "revenue", "amount": "-100.00"}
    ],
    "cash sale"
)
print(money_format(ledger_balance(book, "cash")))
print(ledger_verify(book)["ok"])
```

Ledger Core is intended for deterministic business rules and audit-friendly prototypes. Durable storage, identity, authorization, signatures, and compliance controls belong in the host application.

## Stable CLI

```bash
mellow run <file>
mellow check <file-or-dir>
mellow fmt <files...>
mellow modules --json
mellow doctor
```

Direct script invocation has been removed. Use explicit commands such as
`mellow run <file>` and `mellow check <file-or-dir>`.

## Optional Features

The default install keeps core Mellow lightweight. Python is optional tooling,
not the primary runtime. Install Python extras only when you need them:

```powershell
python -m pip install -e .[lsp]       # language server
python -m pip install -e .[net]       # websocket/network helpers
python -m pip install -e .[security]  # signing and secure-save helpers
python -m pip install -e .[video]     # optional MELV common-video bridge
python -m pip install -e .[all]       # all optional features
```

Native MELV2 pack/inspect/validate/extract is dependency-free. The `video` extra
is only for bridge commands that import/export common video files.

`mellow doctor` reports which optional features are available in the current Python environment.

## Testing

Core language gate:

```powershell
$env:PYTHONPATH = "src"
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q tests\core -p no:cacheprovider
python -m pytest -q tests\native -p no:cacheprovider
```

Native core parity gate:

```powershell
python setup.py build_ext --inplace
python -m pytest -q tests\native -p no:cacheprovider
```

Full suite:

```powershell
python -m pytest -q tests
```

The full suite includes extended and experimental coverage. Use `tests/core`
plus `tests/native` as the release gate for stable language core and native C
parity.

For C-first release confidence, always include the standalone native binary gate
or the native pytest gate in native-only mode.

## Release Process

- Stable core definition: `docs/STABLE_CORE.md`
- Core docs index: `docs/CORE_DOCS.md`
- Experimental docs: `docs/experimental/README.md`
- 2.9.6 stability manifest: `spec/mellow-2.9.6-stability.json`
- 2.9.x stability gates: `scripts/test-v294-stability.ps1`
- Release checklist: `docs/RELEASE_CHECKLIST.md`
- Changelog: `CHANGELOG.md`
- Windows native build helper: `scripts/build-native-windows.ps1`

## Frameworks

`frameworks.mellow_ui` is the first usable framework package. It provides a small React-like virtual UI tree and an in-memory renderer:

```powershell
python -m frameworks.mellow_ui
```

Direct Mellow-script imports such as `import("mellow.ui")` are planned, but the stable v1 framework surface is the Python package.

## Project Layout

Start with [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md) when you need
to find or add code. The short version is:

- Language: `src`, `native`, `spec`, `stdlib`
- Verification: `tests`, `benchmarks`
- Packages and SDKs: `starter_packages`, `mellow_packages`, `sdk`, `plugin_sdk`, `frameworks`
- Tools: `vscode-extension`, `project_template`, `scripts`
- Delivery: `.github`, `packaging`, `deploy`
- Learning: `docs`, `examples`

Generated build files, runtime metadata, local package installs, and temporary
benchmark workspaces are ignored. Preview or remove them with
`scripts/clean-worktree.ps1`.

## License

MIT. See `LICENSE`.
