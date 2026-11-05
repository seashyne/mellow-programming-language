# MellowLang Stdlib Reference (v2.9.9)

This is a pragmatic reference for the stable 2.9 line plus the v2.9.9
native C I/O, system, builtin-module, and GC/concurrency foundation additions.

> Note: Host modules are **allowlisted**. Use `mellow modules` to see what is available.

---

## Core built-ins

- `print(...)` / `println(...)` — print values separated by spaces and end with a newline
- `write(...)` — print values separated by spaces without adding a trailing newline
- `input(prompt="")` — write an optional prompt, read one line from stdin, and return a string
- `readline()` / `read_line()` — aliases for `input()` with no prompt
- `ask(prompt="")` — alias for `input(prompt)`
- `args()` / `argv()` — return command-line arguments passed after the script path
- `cwd()` — return the native process current working directory
- `sleep_ms(ms)` — sleep for an integer number of milliseconds
- `exit(code=0)` — terminate the native process with a status code
- `gc_collect()` — run native mark/sweep collection for runtime-owned native handles and return `0`
- `gc_stats()` — return a map with GC/concurrency and native-handle heap counters
- `spawn(fn)` — register a cooperative native task handle for a function and return a task id
- `yield()` — explicit cooperative yield point
- `workers(n)` / `thread.workers(n)` — configure the native scheduler worker topology and return the active worker count
- `worker_count()` / `thread.worker_count()` — return the active native scheduler worker count
- `scheduler_mode()` / `thread.scheduler_mode()` — return the scheduler mode string, currently `m:n-cooperative`
- `channel()` — create a native FIFO channel handle
- `send(ch, value)` — enqueue a value into a channel and return `true`
- `recv(ch)` — dequeue the next value or return `none` when the channel is empty
- `range(a, b)`
- `len(x)`
- `call(fn, ...args)` *(dynamic function call)*

Full Native C supports these built-ins directly in the standalone runtime and
is the authoritative implementation for new v2.9.9 runtime work.

The v2.9.9 GC API marks reachable native handles from the VM stack/locals and
sweeps unreachable channel handles. `gc_stats()["mode"]` reports
`mark-sweep-native-handles`. Channels work as native FIFO handles. `spawn`,
`yield`, `workers`, `worker_count`, and `scheduler_mode` expose the native M:N
scheduler topology. Execution is still cooperative while parallel bytecode
execution waits on thread-safe heap/channel ownership.

Module forms are available for native built-ins:

```mellow
gc.collect()
let stats = gc.stats()

use chan as c
let ch = c.channel()
c.send(ch, "message")
print(c.recv(ch))

thread.yield()
thread.workers(4)
print(thread.worker_count())
print(thread.scheduler_mode())
```

## Math / vectors

- `vec(x, y)`
- `vec_add(a, b)`, `vec_sub(a, b)`
- `vec_len(v)`

The vector family resolves through `std.math.*` host services and runs on the
Python VM, the `--engine=c` extension, and the standalone `mellow` executable,
which implements the whole family in native C.

### Standalone host coverage

| Family | Standalone `mellow` |
| --- | --- |
| `std.string` | native and UTF-8 aware (`len`, `chr`, `ord`, padding, `format`) |
| `std.list` | native; mutators return new lists |
| `std.map` | native; `set` returns a new map |
| `std.type` | native |
| `std.json` | native encode/decode with Python-compatible separators |
| `std.math` | native, including vectors, `distance`, `angle_between`, `sum` |
| `std.time` | native `unix`, `ms`, and monotonic `now` |
| `std.assert`, `std.event` | native; `AssertionError` messages match the Python VM |
| `std.game` | native easing, tween, grid neighbors, A*, scene/entity, AABB, animation |
| `std.ai` steering, perception, and decisions | native `seek`, `flee`, `arrive`, `wander`, `patrol`, `in_range`, `in_sight`, `nearest`, `filter_range`, `utility_choose`, `bt_tick`, `fsm_tick` |

Native lists and maps are value types: `list.push`, `list.insert`, `list.remove`,
`list.pop`, `list.sort`, and `map.set` return new collections and leave the
receiver unchanged, while the Python VM mutates it. Code that uses the return
value behaves the same on both engines. Game helpers follow the same rule: the
native `entity.move` returns the updated entity map and `astar` returns a new
path list.

Callbacks stay Python-only for now: `list.map`, `list.filter`, `list.reduce`,
`list.map_fn`, and `list.filter_fn` need to invoke a Mellow function and remain a
compile error in the standalone runtime.

`ai.bt_tick` and `ai.fsm_tick` invoke the syscall named in their tree or state
map, so the standalone runtime resolves that name through the same builtin table
the compiler uses. Unknown names fail with `SANDBOX: syscall not allowed: <name>`,
and a missing `args` value means zero arguments while a non-list value is passed
as the single argument, matching the Python VM.

## Money / decimal-safe rules

Money helpers use Python `Decimal` internally and return a map shaped like
`{"type": "money", "currency": "THB", "amount": "12.34"}`.

```mellow
let a = money("0.10", "THB")
let b = money("0.20", "THB")
let total = money_add(a, b)
print(money_format(total))  # THB 0.30
```

Available helpers:

- `money(amount, currency="USD")`
- `money_add(a, b)`, `money_sub(a, b)`
- `money_mul(a, factor)`, `money_div(a, divisor)`
- `money_quantize(a, scale="0.01")`
- `money_format(a)`, `money_amount(a)`, `money_currency(a)`
- `money_eq(a, b)`, `money_lt(a, b)`, `money_gt(a, b)`

Module form is also available:

```mellow
let total = money.add(money.of("12.34", "THB"), money.of("0.01", "THB"))
```

## Immutable ledger

Ledger transactions use signed Decimal amounts. Every transaction must balance
to `0.00`; posting returns a new ledger and leaves the original unchanged.

```mellow
let empty = ledger_create("THB")
let book = ledger_post(
    empty,
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

- `ledger_create(currency="USD")`
- `ledger_post(ledger, transaction_id, postings, memo="", metadata={})`
- `ledger_balance(ledger, account)`
- `ledger_verify(ledger)`
- `ledger_entries(ledger)`

Each entry includes its previous hash and deterministic SHA-256 hash. See
`docs/LEDGER_CORE.md` for the data contract and security boundaries.

## Data processing

JSONL and CSV readers return opaque stream handles. `data_next` returns at most
the configured batch size, so large files do not need to be loaded into memory.

```mellow
let stream = data_open_jsonl("records.jsonl", 1000)
let batch = data_next(stream)
while len(batch) > 0:
    let active = data_where(batch, "active", "==", true)
    let view = data_project(active, ["id", "amount"])
    print(data_sum(view, "amount"))
    batch = data_next(stream)
```

Streaming helpers:

- `data_open_jsonl(path, batch_size=100)`
- `data_open_csv(path, batch_size=100)`
- `data_next(stream)`, `data_close(stream)`, `data_cancel(stream)`
- `data_info(stream)`
- `data_where(rows, field, operator, expected)`
- `data_project(rows, fields)`
- `data_sum(rows, field)`

Parameterized SQLite:

- `data_sqlite_open(path=":memory:", readonly=false)`
- `data_sqlite_query(db_or_path, sql, params=[], limit=max_rows)`
- `data_sqlite_execute(db_or_path, sql, params=[])`
- `data_sqlite_close(db)`

Writes require `--data-write`. Query values must use `?` or named placeholders.

## Interop

External language interop is available through the allowlisted `interop` module.
It is deny-by-default and should be enabled per project:

```json
{
  "permissions": ["interop:node"]
}
```

```mellow
keep result = get interop.run("node", ["tools/hello.js"], {"name": "Mellow"})
print(result)
```

- `interop.available(command)`
- `interop.describe()`
- `interop.run(command, args=[], payload={}, options={})`

See `docs/INTEROP.md` for the JSON stdio protocol and examples for
JavaScript, Go, Rust, Java, C++, C#, TypeScript, COBOL, and other runtimes.

## Random (deterministic)

- `random(min, max)` *(deterministic under seed / replay)*
- `random()` returns a float in `[0, 1)`; `random(n)` returns an int in `[0, n]`.

`std.random.range` is seeded from `RunConfig(seed=...)` per run, so the same seed
gives the same sequence on the Python VM and on `--engine=c`. Record/replay
capture is Python-VM only.

The standalone `mellow` executable implements the same generator in native C:
CPython's MT19937 with `random()`, `random(n)` (an inclusive `[0, n]` integer)
and `random(a, b)` (swapping the bounds when `a > b`). Seed it with
`--seed N` or `--seed=N` anywhere on the command line; the flag is stripped
before argument dispatch, so the script never sees it.

```mellow
print(random())        # float in [0, 1)
print(random(10))      # int in [0, 10]
print(random(5, 15))   # int in [5, 15]
```

```bash
mellow --seed 42 run game.mellow
mellow run game.mellow --seed=42
```

The three engines produce byte-identical sequences for the same seed.

## Storage statements

- `save <expr> into "name"`
- `load "name" into var`

## File & storage API (sandboxed)

- `mkdir(path)`
- `file_read(path, mode="r")`
- `file_write(path, data, mode="w")`
- `file_append(path, data, mode="a")`
- `file_exists(path)`
- `file_delete(path)`
- `save_data(name_or_data, data_or_name)`
- `load_data(name)`

## Secure Save System (encrypted, tamper-evident) — v1.3.4+

This is the **recommended** way to store player progress outside the project folder.

### API

- `save_init(app_id)`
- `save_set(key, value)`
- `save_get(key, default=None)`
- `save_commit(slot)`
- `save_load(slot)` -> `true/false`
- `save_list()` -> `list<string>`
- `save_delete(slot)` -> `true/false`
- `save_clear()`

## Hybrid Save (Level C): Server-signed Save + Online calls — v1.3.5

Use this when the game is **always-online** and you want to detect/stop save tampering.

### Signed Save

- `save_commit_signed(slot, sign_url, pubkey_b64, token=None)`
  - Sends `sha256(payload)` to `sign_url` and expects JSON response `{ "signature_b64": "..." }`.
  - Verifies signature locally (Ed25519) and writes a signed `.msav`.

- `save_load_signed(slot, pubkey_b64)` -> `true/false`
  - Loads save and verifies the server signature.
  - Fails with `SAVE_SIGNATURE_INVALID` if the file was modified.

### Networking

- `net_http_post(url, json_obj, token=None)` -> `map`
- `net_http_get(url, token=None)` -> `map`
- `net_ws_connect(url, token=None)` -> `conn_id`
- `net_ws_send(conn_id, data)` -> `true/false`
- `net_ws_recv(conn_id, timeout_s=0)` -> `string|base64|null`
- `net_ws_state(conn_id)` -> `map`
- `net_ws_close(conn_id)` -> `true/false`

> Networking is **deny-by-default** in project mode. Enable with `permissions` allowlists.

### Notes

- Save files are stored under the user's OS data folder: `<AppData>/<app_id>/saves/*.msav`.
- Each save is **encrypted** and **integrity-protected**. If the file is modified, `save_load` fails with `SAVE_TAMPERED`.
- In **project mode**, save is **deny-by-default**. Enable with permissions in `mellow.json`.

## AI host module (allowlisted)

```mellow
import "ai" as ai
call(ai["decide"], "tag", "event")
```

When running with `--ai-timeline path.jsonl`, decisions are written as JSONL.

### OpenAI-compatible completions

`ai.api_complete(provider, prompt, options?)` answers from the built-in offline
providers unless the provider is configured with a `base_url`:

```mellow
call ai.api_configure("openai", {
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "api_key_env": "OPENAI_API_KEY"
})
let reply = call ai.api_complete("openai", "Summarize MellowLang", {"temperature": 0.2})
print(reply["response"])
```

- `api_complete` POSTs to `{base_url}/chat/completions` with `model` and
  `messages`; `options.system` becomes the system message and `options.messages`
  replaces the generated ones.
- The key is read from `api_key` or the environment variable named by
  `api_key_env`. Returned configs and `api_providers()` redact it.
- Networking is deny-by-default like `net_http_*`: set `allow_net` and put the
  base URL under `net_http_allow` in project `permissions`. Timeouts are clamped
  to 0.1-120 s and responses are capped by `net_max_bytes`.
- Provider state is per host process, so `api_configure` must run before
  `api_complete` in the same run.

### Standalone C runtime

The standalone `mellow` executable implements the `std.ai` surface in native C
with no Python dependency. Calls use either the direct dotted form
(`ai.train(...)`) or the `call` keyword (`call ai.train(...)`); the Python VM
reaches the same functions through `get ai.train(...)`.

- Models: `ai.model_create`, `ai.train`, `ai.predict`, `ai.model_save`,
  `ai.model_load`, `ai.loss_history`, `ai.model_info`, `ai.models_list`,
  `ai.embed`
- LLMs: `ai.llm_create`, `ai.llm_train`, `ai.llm_eval`, `ai.llm_generate`,
  `ai.llm_tokenize`, `ai.llm_complete`, `ai.llm_chat`, `ai.llm_dataset`,
  `ai.llm_info`, `ai.llm_models`, `ai.llm_backends`, `ai.llm_device_plan`,
  `ai.llm_save`, `ai.llm_load`
- Retrieval, prompts and sessions: `ai.vector_search`, `ai.rag_answer`,
  `ai.prompt_template`, `ai.session_open`, `ai.session_message`,
  `ai.session_history`, `ai.chat`, `ai.decide`
- Runtime and providers: `ai.runtime_boot`, `ai.runtime_info`,
  `ai.api_providers`, `ai.api_configure`, `ai.api_complete`, `ai.api_embed`
- Tensor kernels: `ai.llm_tensor` and `ai.llm_tensor_batch`, reported under the
  `mellow-native-c` backend

Trained checkpoints land in `mellow_models/` and are interchangeable across
engines: a `.mmodel` trained by the Python VM loads in the standalone runtime
and a `.mllm` trained by the standalone runtime loads in the Python VM. Model
training draws from CPython's MT19937, so `--seed 42` reproduces Python's
weights exactly. Container values that `ai.decide` or `prompt_template` render
use Python's `str()`/`repr()` spelling (`['a', 'b']`, `{'k': v}`, `True`,
`None`), so logs match across engines.

`api_complete` uses the same offline providers and `local-rag` strategy as the
Python VM. Only the network transport needs the Python host: in the standalone
runtime an `openai`-configured provider fails with
`AI_PROVIDER_ERROR: network transport is not available in the standalone runtime`.

---

## Game module (v1.4.0, allowlisted)

Use `get("game")` (or `lib("game")`) to access game helpers.

```mellow
g = get("game")

# easing
t = call(g["ease_in_quad"], 0.25)

# tween step: from, to, t, ease_name?
x = call(g["tween"], 0, 100, 0.50, "out_quad")

# grid neighbors: x, y, width, height
ns = call(g["neighbors4"], 1, 1, 10, 10)

# A* pathfinding: grid (0=free, 1=blocked), start [x,y], goal [x,y], diag?
grid = [
  [0,0,0,0],
  [1,1,0,1],
  [0,0,0,0],
]
path = call(g["astar"], grid, [0,0], [3,2], false)
print(path)
```

The standalone `mellow` runtime implements these helpers in native C, together
with `scene_create`, `entity_create`, `entity_move`, `collide_aabb`,
`anim_frame`, and the allowlisted `ai.*` behaviour functions:
`ai.seek`, `ai.flee`, `ai.arrive`, `ai.wander`, `ai.patrol`, `ai.in_range`,
`ai.in_sight`, `ai.nearest`, and `ai.filter_range`. Results match the Python VM;
`tests/native/test_native_game_standalone.py` diffs native stdout against the
reference engine.

---

## CLI tooling

- `mellow run <file|projectdir>`
- `mellow run <file> --sandbox=finance`
- `mellow run <file> --sandbox=data`
- `mellow check <file|dir>`
- `mellow fmt <file|dir> [--write|--check]`
- `mellow test`
- `mellow replay <log.jsonl>`
- `mellow diff <a.jsonl> <b.jsonl>`
- `mellow doctor`
- `mellow explain <ERROR_ID>`
