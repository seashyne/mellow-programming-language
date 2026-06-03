# MellowLang v1.4.5 — Release Notes

## Bug Fixes

### 🔴 Fix: `evaluate_boolean` — compound conditions now work correctly
- **Before**: Used fragile string-splitting (`.split(op, 1)`) which broke on compound conditions
  like `x >= 10 and y < 5`, `not is_dead and hp > 0`, or anything with multiple operators
- **After**: Uses the full Pratt AST parser (`ExprParser`) — same engine used by the VM pipeline
- Supports: `and`, `or`, `not`, `==`, `!=`, `<`, `>`, `<=`, `>=`, parentheses, nested expressions

```mellow
# Before: broken
if x >= 10 and y < 5:
    print("was broken, now works")

# Before: broken
while not is_done and count < 100:
    count = count + 1
```

### 🔴 Fix: `list_core` — strings with commas no longer split incorrectly
- **Before**: `create_list` used naive `str.split(',')` which mangled quoted strings
- **After**: Proper parser that respects `"..."`, `'...'`, nested `[]`, `{}`, `()`

```mellow
# Before: ["hello, world", "test"] → 3 wrong items
# After:  ["hello, world", "test"] → 2 correct items
let tags = ["fast, responsive", "game-ready", "open-source"]
```

---

## New Features

### 🟡 Math stdlib: `min`, `max`, `floor`, `ceil`, `clamp` (and more)
- `min(a, b)` / `max(a, b)` — also accepts a list: `min([1, 2, 3])`
- `floor(n)` — round down to integer
- `ceil(n)` — round up to integer
- `clamp(val, lo, hi)` — clamp value between lo and hi
- `log(n, base?)` — logarithm (default base: e)
- `sin(n)`, `cos(n)`, `tan(n)` — trigonometry
- `sqrt()` now uses `math.sqrt` instead of 12-iteration Newton's method

```mellow
let hp = 150
let clamped_hp = clamp(hp, 0, 100)   # → 100

let speed = floor(3.9)                # → 3
let padding = ceil(2.1)               # → 3

let best = max(10, 20)                # → 20
let worst = min(10, 20)               # → 10
```

### 🟡 F-String Interpolation: `f"Hello {name}!"`
- Syntax: `f"..."` or `f'...'`
- Embed any expression inside `{...}`
- Supports variables, math, function calls, nested expressions

```mellow
let name = "Alice"
let hp = 85
let max_hp = 100

print(f"Player: {name}")
print(f"HP: {hp}/{max_hp}")
print(f"Percentage: {floor(hp / max_hp * 100)}%")

# Works in assignments too
let msg = f"Round {round_num}: {winner} wins!"
```

---

## Internal Improvements

- `math.sqrt` replaces the custom 12-iteration Newton's method (faster + handles edge cases)
- `_eval_ast` in legacy interpreter now correctly maps to actual AST class names
  (`Call`, `Index`, `ListLiteral`, `MapLiteral` instead of mismatched aliases)
- Added `std.string.tostr` syscall for f-string expression-to-string conversion in VM path
- All changes are **backward-compatible** with v1.x policy

---

## Compatibility

- ✅ All v1.x scripts continue to work unchanged
- ✅ CLI flags unchanged
- ✅ Bytecode format unchanged (f-strings compile to `PUSH`+`SYSCALL`+`ADD` sequences)
