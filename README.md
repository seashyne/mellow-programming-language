# Mellow Programming Language 2.7.0

Mellow Programming Language, also known as MellowLang, is a sandbox scripting language focused on games, tools, and AI behavior experiments.

This release treats the language core as the stable surface:

- `let` / assignment
- `def` functions
- `if`, `while`, and `for`
- `range(...)`
- list and map literals
- string/math/list/map/json/money/data helpers
- `mellow run`, `mellow check`, `mellow fmt`, `mellow modules`, and `mellow doctor`

Larger systems such as agents, MMG, desktop bundles, package registries, and MELV video tools are available, but should be treated as extended or experimental surfaces unless their own tests are green. In v2.7.0 the native C VM covers the stable language core plus money and data stdlib services. Debugger, events, and record/replay still route through the Python VM.

## Quick Start

From a source checkout:

```powershell
python -m pip install -e .[dev]
mellow --version
mellow run examples\hello.mellow
mellow run examples\hello.mellow --engine=c
mellow check examples\hello.mellow
mellow doctor
```

Without installing:

```powershell
$env:PYTHONPATH = "src"
python -m mellowlang --version
python -m mellowlang run examples\hello.mellow
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

Both finance and data sandbox profiles can use `--engine=c` in v2.7.0. Native parity tests run with Python fallback disabled.

## Stable CLI

```bash
mellow run <file>
mellow check <file-or-dir>
mellow fmt <files...>
mellow modules --json
mellow doctor
```

Legacy direct-run mode is still supported:

```bash
mellow <file>
mellow <file> --check
```

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

The full suite currently includes legacy and experimental coverage. Use `tests/core` plus `tests/native` as the release gate for stable language core and native C parity.

## Release Process

- Stable core definition: `docs/STABLE_CORE.md`
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
- `tests`: legacy, extended, and experimental tests
- `examples`: runnable Mellow scripts
- `stdlib`, `starter_packages`, `mellow_packages`: package and stdlib content
- `native`, `plugin_sdk`, `deploy`, `websites`: extended platform surfaces

## License

MIT. See `LICENSE`.
