# Release Notes v2.9.10

v2.9.10 is the release where the standalone C runtime stops delegating data work
to Python. `std.data` and SQLite run in the `mellow` binary, `--engine c
--data-write` stays native, and the remaining standard library families
(string, list, map, type, json, math, time, assert, event, game, and the AI
behaviour helpers) already execute there. The other half of the release is
structure: the last oversized Python modules and native translation units were
split along their seams, and the line ceilings now enforce the result.

## Native standard library

- `std.string`, `std.list`, `std.map`, `std.type`, `std.json`, `std.math`,
  `std.time`, `std.assert`, and `std.event` run in native C. Native lists and
  maps are value types, so `list.push`, `list.insert`, `list.remove`,
  `list.pop`, `list.sort`, and `map.set` return new collections while the Python
  VM still mutates its receivers; `tests/native/test_native_std_standalone.py`
  pins that difference instead of masking it.
- `std.game` runs natively: the eleven easing curves, `tween.step`,
  `grid.neighbors4`/`neighbors8`, `path.astar` with the Python heap
  tie-breaking and `1.41421356237` diagonal cost, scene and entity helpers,
  `physics.collide_aabb`, and `anim.frame`. The `ai.*` behaviour helpers
  (`steering.*`, `perception.*`, `utility_choose`, `bt_tick`, `fsm_tick`) are
  native too, including the `success`/`fail`/`running` passthrough and the
  syscall-name lookup that re-enters the dispatcher.
- `std.data` reads JSONL and CSV in native C with `csv.DictReader` quoting,
  embedded newlines, duplicate headers, missing columns, and extra values. Batch
  sizes stay in 1-1000, at most eight streams stay open, records cap at 1 MiB,
  and paths obey the `fs` sandbox.
- `data_sqlite_open`, `data_sqlite_close`, `data_sqlite_query`, and
  `data_sqlite_execute` run through the vendored SQLite 3.54.1 amalgamation in
  `native/standalone/vendor/sqlite/`. Statement classification, parameter
  binding, row limits, read-only opens, and `--data-write` gating match the
  Python `DataCoreError` behaviour, including the DDL `rows_changed` of 0.

## Data runs stay native

The CLI probe used to send any run carrying `--data-write` back to the Python VM.
It now selects the standalone binary and forwards `--data-write` and
`--data-max-rows`, so the permission and the row limit reach the native runtime
instead of being silently dropped. Without the flag the binary still refuses
writes with `data writes are disabled`.

## AI transport

`ai.api_complete` can POST to any OpenAI-compatible endpoint configured with
`base_url`, `model`, and `api_key` or `api_key_env`. Keys are redacted from
provider reports and returned configs, the call reuses the `net_http_*` sandbox
rules, and the 0.1-120 s timeout clamp plus `net_max_bytes` still apply. Offline
and `local-rag` providers are byte-identical to the previous release.

## Performance

The standalone heap now keeps a pointer-keyed bucket index, so `heap_find` no
longer scans the global block list on every release and GC mark. Money 1,000
steps moved from 188.4 ms to 9.5 ms, 4,000 steps from 3,438.4 ms to 21.1 ms, and
80 ledger posts from 15,128.4 ms to 29.9 ms. The sweep still walks the list, and
the cost that remains in the ledger curve is the per-post clone of the whole
book.

## Structure and gates

- `cli/commands/runtime.py` became `cli/commands/runtime_groups/`, and the
  benchmark entry points, the Cloudflare public-registry Worker, `web`,
  `desktop_host`, `mmg_runtime`, the registry server, `lint`, `ast`, the
  debugger, `cbridge`, the agent control plane, the agent registry, and IR
  lowering split into concern packages behind imports-only facades.
- Every native `.c`/`.h`/`.inc` file is at most 300 lines. Each parent keeps its
  opening code and includes contiguous `*_partN.inc` slices, and
  `tests/language/test_source_structure.py` pins numbering, include order, and
  the bound.
- The line gate skips vendored third-party trees, so the 250k-line SQLite
  amalgamation does not count as project code, and the ceilings still only move
  down.

## Deferred

- `package_manager.py` remains unsplit because that file carries uncommitted
  work; it stays over its 1,100-line ceiling.
- Python is still required for `list.map`/`filter`/`reduce`/`map_fn`/`filter_fn`,
  `interop`, the encrypted save envelope, MELV standalone CLI hooks,
  debugger/events/record/replay, LSP, and package tooling.
