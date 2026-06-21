# Mellow Programming Language 2.9.3

Mellow Programming Language, also known as MellowLang, is a sandbox scripting language focused on games, tools, and AI behavior experiments.

This release treats the language core as the stable surface:

- `let` / assignment
- `def` functions
- `if`, `while`, and `for`
- `range(...)`
- list and map literals
- string/math/list/map/json/money/data/ledger helpers
- `mellow run`, `mellow check`, `mellow fmt`, `mellow modules`, and `mellow doctor`

Larger systems such as agents, MMG, desktop bundles, package registries, and MELV video tools are available, but are documented as **experimental** under [`docs/experimental/README.md`](docs/experimental/README.md). In v2.9.3 the standalone `mellow` executable includes a C lexer, compiler, bytecode runtime, and core built-ins. Debugger, events, record/replay, package tooling, LSP, and extended services remain optional Python tooling.

## Quick Start

From a source checkout:

```powershell
python -m pip install -e .[dev]
mellow --version
mellow run examples\hello.mellow
mellow check examples\hello.mellow
mellow doctor
```

Native C is the default execution engine. Mellow falls back to the Python VM
when a script requests debugger, event, or record/replay features that do not
yet have native parity. Use `--engine=py` to force Python.

Without installing:

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
mellow run examples\syntax_tour_v280.mellow
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
in v2.9.3. Native parity tests run with Python fallback disabled.

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

The default install keeps core Mellow lightweight. Install extras only when you need them:

```powershell
python -m pip install -e .[lsp]       # language server
python -m pip install -e .[net]       # websocket/network helpers
python -m pip install -e .[security]  # signing and secure-save helpers
python -m pip install -e .[video]     # MELV video encode/decode
python -m pip install -e .[all]       # all optional features
```

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

## Release Process

- Stable core definition: `docs/STABLE_CORE.md`
- Core docs index: `docs/CORE_DOCS.md`
- Experimental docs: `docs/experimental/README.md`
- 2.9.3 stability gates: `scripts/test-v293-stability.ps1`
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

- `src/mellowlang`: compiler, VM, CLI, stdlib bridges, and runtime support
- `tests/core`: stable core language tests
- `tests/native`: native C VM parity tests for the stable core
- `tests`: core, extended, and experimental tests
- `examples`: runnable Mellow scripts
- `stdlib`, `starter_packages`, `mellow_packages`: package and stdlib content
- `native`, `plugin_sdk`, `deploy`, `websites`: extended platform surfaces

## License

MIT. See `LICENSE`.
