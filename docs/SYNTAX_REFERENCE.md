# MellowLang Syntax Reference (v2.7.0)

Mellow is a **safe, deterministic scripting language** for games and AI logic.

This document is the **source-of-truth** for the v1.3.x syntax that ships with the CLI zip.
For a longer narrative tutorial, see `docs/MELLOWLANG_User_Manual.md`.

---

## 1) Files, comments

- File extension: `.mellow`
- Single-line comment: `# like this`

```mellow
# hello
print("hi")
```

---

## 2) Blocks and indentation (important)

Blocks are **indentation-based** (Python-like).

- A block starts after a statement ending with `:`
- Indent consistently (recommended: **4 spaces**)
- There is **no** `end`

```mellow
if hp < 10:
    print("low")
    heal()
print("done")
```

---

## 3) Variables

```mellow
let hp = 100
hp = hp - 10
```

---

## 4) Types (runtime)

- number (int/float), string, bool
- list: `[1, 2, 3]`
- dict: `{ "a": 1, "b": 2 }`
- vec: `vec(x, y)`
- money maps from `money("12.34", "THB")` for exact decimal-style rules
- opaque data stream/database handles returned by `data_*` helpers

---

## 5) Expressions

Common operators:

- arithmetic: `+ - * / %`
- compare: `== != < <= > >=`
- boolean: `and or not`

---

## 6) Conditionals

```mellow
if score >= 10:
    print("win")
elif score >= 5:
    print("close")
else:
    print("try again")
```

---

## 7) Loops

### for + range

```mellow
let s = 0
for i in range(0, 5):
    s = s + i
print(s)
```

### while

```mellow
let i = 0
while i < 3:
    print(i)
    i = i + 1
```

---

## 8) Functions

```mellow
def add(a, b):
    return a + b

print(add(2, 3))
```

---

## 9) Function calls as statements (game-friendly)

You can call functions as standalone statements:

```mellow
file_write("notes.txt", "hello\n", mode="w")
```

Legacy `call(...)` still exists:

```mellow
call(file_write, "notes.txt", "hello\n", {"mode": "w"})
```

---

## 10) Named arguments

Named args are supported for many built-ins:

```mellow
file_write("a.txt", "hi", mode="w")
file_append("a.txt", "!", mode="a")
```

---

## 11) Imports and modules

Mellow ships with safe, allowlisted host modules.

```mellow
import "ai" as ai
call(ai["decide"], "patrol", "start")
```

List available modules:

```bash
mellow modules
```

---

## 12) Storage (deterministic saves)

High-level statements:

```mellow
save {"score": 42} into "profile"
load "profile" into data
print(data)
```

Low-level file APIs are available in the sandbox (see `docs/CAPABILITIES.md`).

---

## 13) Determinism: seed, record, replay, diff

Run with a fixed seed:

```bash
mellow run main.mellow --seed 123
```

Record a run:

```bash
mellow run main.mellow --record run.jsonl --seed 7
```

Replay the exact same run (seed can differ):

```bash
mellow run main.mellow --replay run.jsonl --seed 999
```

Diff two logs:

```bash
mellow diff a.jsonl b.jsonl
```

---

## 14) Sandbox & permissions

Some actions are deny-by-default and require flags or a project manifest (`mellow.json`).

Common flags:

- `--allow-ask` (enable user input)
- `--no-wait` (disable sleep/wait)
- budgets: `--max-steps`, `--max-ms`, `--syscall-budget`
- `--sandbox=finance` disables ask/wait/storage/save/network on both Python and native C execution
- `--sandbox=data` enables bounded read-oriented data processing; writes additionally require `--data-write`

See: `docs/CAPABILITIES.md` and `docs/CLI.md`.
