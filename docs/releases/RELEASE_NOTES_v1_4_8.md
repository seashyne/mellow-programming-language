# MellowLang v1.4.8 Release Notes

**Release Date:** 2026-03-05  
**Stability:** Stable  
**Compatibility:** Fully backwards-compatible with v1.4.7

---

## Highlights

### 1. `get` / `call` Module System

A new first-class syntax for invoking stdlib modules with Mellow's own identity:

```mellow
keep x = get math.sqrt(25)        # → 5
keep y = call string.upper("hi")  # → "HI"
keep z = get ai.chat("hello")     # → {response: "...", ...}

# Also valid as statement (result discarded):
call list.push(mylist, 99)
get ai.model_create("net", layers, "classify")
```

Both `get` and `call` are semantically identical. Use whichever reads naturally.
All modules in the allowlist (`math`, `string`, `list`, `map`, `json`, `time`, `ai`, `game`) work.

### 2. Full AI Engine (`ai` module)

MellowLang now supports building, training, and running AI models — entirely offline.

```mellow
# Create a 2-layer neural network
call ai.model_create("xor", [
    {in:2, out:4, activation:"relu"},
    {in:4, out:2, activation:"softmax"}
], "classify")

# Train
call ai.train("xor", [[0,0],[0,1],[1,0],[1,1]], [0,1,1,0], 50, 0.05)

# Predict
keep pred = call ai.predict("xor", [0,1])
show pred  # → {prediction: 1, probabilities: [...], ...}

# Chat
keep r = call ai.chat("hello")
show r  # → {response: "Hey! Ready to assist.", ...}

# Embed text (64-dim offline embedding)
keep emb = call ai.embed("MellowLang")

# Save/Load
call ai.model_save("xor", "xor_model")
call ai.model_load("xor_model")
```

**Supported tasks:** `classify`, `regress`  
**Activations:** `relu`, `sigmoid`, `softmax`, `linear`

### 3. C VM Full Python Fallback

The C VM extension is now fully optional. All 44+ opcodes are handled by the Python VM:

- C VM available → runs C VM for performance
- Any unsupported opcode → seamlessly falls back to Python VM
- No C compiler needed to use 100% of MellowLang features

---

## Changed Files

| File | Change |
|------|--------|
| `src/mellowlang/ai_core.py` | **NEW** — full AI engine (chat, train, predict, embed) |
| `src/mellowlang/lexer.py` | Added `get`, `call` keywords |
| `src/mellowlang/ast.py` | Added `GetModuleStmt`, `GetModuleExpr` nodes |
| `src/mellowlang/parser.py` | `get`/`call` statement + expression parsing |
| `src/mellowlang/compiler/bytecode.py` | `_compile_get_module()`, `GetModuleExpr` in expr compiler |
| `src/mellowlang/vm/cbridge.py` | Full Python fallback for all opcodes |
| `src/mellowlang/host/runtime.py` | Extended AI allowlist, `register_ai_functions()` |
| `native/mellowvm/src/mellowvm_module.c` | Full opcode table documented |
| `pyproject.toml` | Version → 1.4.8 |
| `tests/test_v148.py` | **NEW** — 70+ tests for all v1.4.8 features |
| `docs/MELLOWLANG_v148_Manual.md` | **NEW** — comprehensive manual |
| `examples/ai_v148.mellow` | **NEW** — AI engine examples |
| `examples/modules_v148.mellow` | **NEW** — get/call module examples |

## Removed

- `MellowLang_v1_4_6/` — stale nested copy of old version
- All `__pycache__/` directories
- All `*.pyc` compiled Python files
- `.pytest_cache/` directories
- `*.egg-info/` build artifacts
