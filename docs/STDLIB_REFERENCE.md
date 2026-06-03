# MellowLang Stdlib Reference (v1.4.0)

This is a pragmatic reference for what ships in the **v1.3.3 CLI zip**.

> Note: Host modules are **allowlisted**. Use `mellow modules` to see what is available.

---

## Core built-ins

- `print(...)`
- `input(prompt)` *(requires `--allow-ask`)*
- `range(a, b)`
- `len(x)`
- `call(fn, ...args)` *(legacy escape hatch)*

## Math / vectors

- `vec(x, y)`
- `vec_add(a, b)`, `vec_sub(a, b)`
- `vec_len(v)`

## Random (deterministic)

- `random(min, max)` *(deterministic under seed / replay)*

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

---

## CLI tooling

- `mellow run <file|projectdir>`
- `mellow check <file|dir>`
- `mellow fmt <file|dir> [--write|--check]`
- `mellow test`
- `mellow replay <log.jsonl>`
- `mellow diff <a.jsonl> <b.jsonl>`
- `mellow doctor`
- `mellow explain <ERROR_ID>`
