# MellowLang Capabilities (v1.0.3)

## Language
- Basic types: number, string, bool, none/null
- Variables: `keep x = ...`, assignment `x = ...`
- Conditions: `check/also/else`
- Loops: while, for-range, foreach styles (see Syntax Reference)
- Skills (functions): `skill name(args): ... return ...`
- Lists, maps, strings, math helpers (via allowlisted modules)

## Built-ins
- Output: `print(...)` (alias of `show(...)`)
- Input: `input(...)` (alias of `ask(...)`, sandbox gated)
- Random: `randi(a,b)`, `rand()` etc
- Determinism: `global_seed(n)` (runtime)

## Sandbox
- Allowlisted modules via `get("math")` / `import "math" as m`
- `input()` gated by `--allow-ask`
- `wait()` can be disabled by `--no-wait`

## Tooling
- CLI subcommands
- VS Code extension (syntax highlighting + basic LSP)
- Formatter: `mellow fmt`


## Storage & Files (v1.0.7)

- Base directory: `./mellow_saves` (auto-created when you use storage)
- JSON helpers: `save_data(data, name)` / `load_data(name)` (forces `.json`)
- File helpers (explicit modes):
  - `file_read(path, mode="r")`  (`r`, `rb`)
  - `file_write(path, data, mode="w")` (`w`, `wb`)
  - `file_append(path, data, mode="a")` (`a`, `ab`)
  - `file_exists(path)` / `file_delete(path)`
  - `mkdir(path)` (required if you want subfolders; Mellow will **not** create them automatically)


## AI Runtime Layer

Mellow now includes an offline AI runtime layer with session memory, prompt templating, vector search, and simple retrieval-augmented answers.

Functions:
- ai.runtime_boot(config?)
- ai.runtime_info()
- ai.session_open(name?, system?)
- ai.session_message(session_id, prompt)
- ai.session_history(session_id)
- ai.prompt_template(template, vars)
- ai.vector_search(query, docs, top_k?)
- ai.rag_answer(query, docs, top_k?)


## v1.5.1 additions

- Local package manager for publish/install/build workflows
- Game scripting engine primitives: scene, entity, collision, animation frame
- Unified AI API layer for offline providers and embeddings
- Compiler command for bytecode JSON and generated Python


## v1.5.2 Online Package Manager
- Remote registry server
- Publish/install/search over HTTP
- Auth tokens stored in local config
- `mellow.toml` manifest support
- SHA-256 package integrity metadata
