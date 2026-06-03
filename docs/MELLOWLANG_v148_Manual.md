# MellowLang v1.4.8 — Complete User Manual

> **Version:** 1.4.8  |  **Engine:** Python + C VM (auto-fallback)  |  **License:** See LICENSE

---

## Table of Contents
1. [What's New in v1.4.8](#whats-new)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Syntax Reference](#syntax-reference)
5. [Module System — `get` / `call`](#module-system)
6. [AI Module](#ai-module)
7. [C VM & Python Fallback](#c-vm)
8. [Standard Library](#stdlib)
9. [Examples](#examples)
10. [Release Notes v1.4.8](#release-notes)

---

## 1. What's New in v1.4.8 {#whats-new}

| Feature | Description |
|---------|-------------|
| **`get`/`call` Module System** | New idiomatic syntax for calling stdlib modules |
| **AI Engine** | Full `ai` module: chat, train, predict, embed, model save/load |
| **C VM Full Python Fallback** | Every opcode covered — C VM is optional, Python VM always works |
| **Cleaner Project Structure** | Removed legacy nested directories and `.pyc` cache |

---

## 2. Installation {#installation}

```bash
pip install mellowlang          # from PyPI
# or from source:
pip install -e .
```

**Run a script:**
```bash
mellow run myfile.mellow
# or:
python -m mellowlang myfile.mellow
```

---

## 3. Quick Start {#quick-start}

```mellow
# hello.mellow
show "Hello, MellowLang 1.4.8!"

keep name = "World"
show f"Hello {name}!"

# get/call module system
keep root = get math.sqrt(16)
show root   # → 4

# AI
keep reply = call ai.chat("hello")
show reply  # → {response: "Hey! Ready to assist.", ...}
```

---

## 4. Syntax Reference {#syntax-reference}

### Variables
```mellow
keep x = 42          # persistent variable
let y = "hello"      # alias for keep
var z = [1, 2, 3]    # alias for keep
```

### Conditionals
```mellow
check x > 10:
    show "big"
also x > 5:
    show "medium"
else:
    show "small"

# modern aliases
if x > 10:
    show "big"
elif x > 5:
    show "medium"
else:
    show "small"
```

### Loops
```mellow
loop i < 10:           # while loop
    keep i = i + 1

for i = 1, 10:         # numeric for (1 to 9)
    show i

for x in mylist:       # foreach
    show x

repeat:                # do-while
    keep x = x + 1
until x >= 5

loop 3:                # loop N times (count loop)
    show "hi"
```

### Functions
```mellow
skill greet(name):
    return f"Hello {name}!"

show greet("World")

# Aliases: def, fn, function
def add(a, b):
    return a + b
```

### Error Handling
```mellow
try:
    keep x = risky_call()
catch err:
    show f"Error: {err}"
finally:
    show "done"
```

### Collections
```mellow
keep nums = [1, 2, 3]
keep info = {name: "mellow", version: 1}

# access
show nums[0]
show info["name"]

# f-string interpolation
show f"v{info['version']}"
```

### String Interpolation (f-strings)
```mellow
keep hp = 80
keep max_hp = 100
show f"Health: {hp}/{max_hp}"
```

---

## 5. Module System — `get` / `call` {#module-system}

v1.4.8 introduces **two idiomatic keywords** for calling stdlib modules.
Both `get` and `call` are equivalent — choose whichever reads more naturally.

### Syntax
```mellow
# As expression (with assignment):
keep result = get  module.function(args...)
keep result = call module.function(args...)

# As statement (result discarded):
get  module.function(args...)
call module.function(args...)
```

### Examples
```mellow
# Math
keep root  = get math.sqrt(25)       # → 5
keep clamped = call math.clamp(15, 0, 10) # → 10
keep pi = get math.pi                 # → 3.14159...

# String
keep upper = get string.upper("hello")   # → "HELLO"
keep lower = call string.lower("WORLD")  # → "world"
keep parts = get string.split("a,b,c", ",") # → ["a","b","c"]
keep trimmed = call string.trim("  hi  ")  # → "hi"

# List
keep n = get list.len([1,2,3,4])     # → 4
call list.push(mylist, 42)

# JSON
keep json_str = call json.encode({name: "mellow"})
keep data = get json.decode('{"x":1}')

# Time
keep ts = get time.unix()
keep ms = call time.ms()

# AI (see section 6)
keep reply = call ai.chat("hello")
keep model = call ai.model_create("mynet", layers, "classify")
```

### Module Allowlist
All modules available via `get`/`call`:

| Module | Functions |
|--------|-----------|
| `math` | `abs`, `sqrt`, `pow`, `sin`, `cos`, `tan`, `atan2`, `floor`, `ceil`, `round`, `clamp`, `lerp`, `min`, `max`, `pi`, `vec2`, `vec3`, `vec_add`, `vec_sub`, `vec_dot`, `vec_len`, `vec_norm`, `vec_dist` |
| `string` | `len`, `upper`, `lower`, `trim`, `replace`, `find`, `split`, `join`, `contains`, `starts_with`, `ends_with`, `pad_left`, `pad_right`, `repeat`, `format` |
| `list` | `push`, `pop`, `len`, `insert`, `remove`, `has`, `sort` |
| `map` | `get`, `set`, `keys`, `values`, `has` |
| `json` | `encode`, `decode` |
| `time` | `unix`, `ms`, `now` |
| `ai` | See AI Module section |
| `game` | `ease_*`, `tween`, `astar`, `neighbors4`, `neighbors8` |

---

## 6. AI Module {#ai-module}

MellowLang v1.4.8 includes a **full offline AI engine** — no network required.

### 6.1 AI Chat
```mellow
keep reply = call ai.chat("hello")
show reply
# → {response: "Hey! Ready to assist.", model: "_chat_default", memory_size: 1}

# With custom model and system prompt:
keep reply = call ai.chat("help me", "my_bot", "You are a game assistant.")
```

### 6.2 Create a Model
```mellow
# ai.model_create(name, layers, task)
# task: "classify" | "regress"

keep info = call ai.model_create("mynet", [
    {in: 2, out: 8, activation: "relu"},
    {in: 8, out: 4, activation: "relu"},
    {in: 4, out: 2, activation: "softmax"}
], "classify")

show info
# → {model: "mynet", layers: 3, task: "classify", status: "created"}
```

**Activation functions:** `relu`, `sigmoid`, `softmax`, `linear`

### 6.3 Train
```mellow
# ai.train(model_name, data, labels, epochs?, lr?)

keep result = call ai.train("mynet",
    [[1,0],[0,1],[1,1],[0,0]],   # input data
    [0, 1, 0, 1],                 # labels (class indices)
    epochs=50,
    lr=0.01
)

show result
# → {model: "mynet", epochs: 50, samples: 4, final_loss: 0.23, status: "trained"}
```

### 6.4 Predict
```mellow
# ai.predict(model_name, input)

keep pred = call ai.predict("mynet", [1, 0])
show pred
# → {model: "mynet", input: [1,0], prediction: 0, probabilities: [0.72, 0.28]}
```

### 6.5 Text Embedding
```mellow
# ai.embed(text)  →  64-dimensional float vector (offline, deterministic)

keep emb = call ai.embed("MellowLang AI")
keep n = get list.len(emb)
show n  # → 64
```

### 6.6 Save & Load Models
```mellow
# Save (writes to mellow_models/<name>.mmodel)
call ai.model_save("mynet", "mynet")

# Load
keep loaded = call ai.model_load("mynet")
show loaded  # → {loaded: "mynet", layers: 3, task: "classify"}
```

### 6.7 Model Info & Management
```mellow
keep info  = call ai.model_info("mynet")
keep names = call ai.models_list()
keep hist  = call ai.loss_history("mynet")
```

### Complete AI Example
```mellow
# XOR classifier

# 1. Create model
call ai.model_create("xor", [
    {in: 2, out: 4, activation: "relu"},
    {in: 4, out: 2, activation: "softmax"}
], "classify")

# 2. Train
keep result = call ai.train("xor",
    [[0,0],[0,1],[1,0],[1,1]],
    [0,   1,   1,   0  ],
    50, 0.05)
show result

# 3. Predict
keep p = call ai.predict("xor", [0,1])
show p  # prediction: 1

keep p2 = call ai.predict("xor", [0,0])
show p2 # prediction: 0

# 4. Save
call ai.model_save("xor", "xor_model")
```

---

## 7. C VM & Python Fallback {#c-vm}

MellowLang v1.4.8 uses a **three-tier execution strategy**:

```
Script
  │
  ▼
Compiler (Python) → Bytecode
  │
  ▼
C VM Extension (if compiled)
  │  If CVM_UNSUPPORTED_OPCODE raised:
  ▼
Python VM (full opcode coverage, 100% fallback)
```

**Check availability:**
```python
from mellowlang.vm.cbridge import c_vm_available
print(c_vm_available())  # True | False
```

**Build C extension:**
```bash
python setup.py build_ext --inplace
```

The Python VM covers **all 44+ opcodes** including the new v1.4.8 additions. The C VM is optional performance optimization.

---

## 8. Standard Library {#stdlib}

### Math
```mellow
show math.sqrt(16)          # 4
show math.abs(-5)           # 5
show math.clamp(15, 0, 10)  # 10
show math.lerp(0, 10, 0.5)  # 5
show math.sin(math.pi)      # ~0
show math.pow(2, 8)         # 256
show math.min(3, 7)         # 3
show math.max(3, 7)         # 7
```

### Vectors
```mellow
keep v1 = math.vec2(3, 4)
keep v2 = math.vec2(1, 2)
keep sum  = math.vec_add(v1, v2)
keep dot  = math.vec_dot(v1, v2)
keep dist = math.vec_dist(v1, v2)
keep norm = math.vec_norm(v1)
keep len  = math.vec_len(v1)   # → 5
```

### Strings
```mellow
keep s = "MellowLang"
show string.len(s)              # 10
show string.upper(s)            # MELLOWLANG
show string.lower(s)            # mellowlang
show string.trim("  hi  ")      # hi
show string.replace(s, "Lang", "AI")  # MellowAI
show string.contains(s, "mellow")     # false (case-sensitive)
show string.split("a,b,c", ",")       # ["a","b","c"]
show string.join(["a","b","c"], "-")  # a-b-c
show string.starts_with(s, "Mellow")  # true
show string.ends_with(s, "Lang")      # true
```

### Lists
```mellow
keep xs = [1, 2, 3]
list.push(xs, 4)               # xs = [1,2,3,4]
keep popped = list.pop(xs)     # 4
show list.len(xs)              # 3
show list.has(xs, 2)           # true
list.sort(xs)                  # in-place sort
```

### Maps
```mellow
keep m = {hp: 100, name: "Hero"}
show map.get(m, "hp")          # 100
map.set(m, "hp", 90)
show map.has(m, "name")        # true
show map.keys(m)               # ["hp","name"]
show map.values(m)             # [90,"Hero"]
```

---

## 9. Examples {#examples}

### Neural Network Classifier
```mellow
# Classify Iris-style data (3 features → 3 classes)
call ai.model_create("iris", [
    {in: 4, out: 16, activation: "relu"},
    {in: 16, out: 8, activation: "relu"},
    {in: 8,  out: 3, activation: "softmax"}
], "classify")

# Simplified training data
keep data = [
    [5.1,3.5,1.4,0.2], [4.9,3.0,1.4,0.2],  # class 0
    [7.0,3.2,4.7,1.4], [6.4,3.2,4.5,1.5],  # class 1
    [6.3,3.3,6.0,2.5], [5.8,2.7,5.1,1.9]   # class 2
]
keep labels = [0, 0, 1, 1, 2, 2]

keep result = call ai.train("iris", data, labels, 100, 0.01)
show result

keep pred = call ai.predict("iris", [5.1, 3.5, 1.4, 0.2])
show pred
```

### Chat Bot
```mellow
skill chat_loop():
    keep msg = input("You: ")
    loop msg != "bye":
        keep reply = call ai.chat(msg, "bot", "You are a helpful game guide.")
        show f"Bot: {reply}"
        keep msg = input("You: ")
    show "Goodbye!"

chat_loop()
```

### Data Analysis
```mellow
keep data = [3.2, 1.5, 4.8, 2.1, 5.5, 1.9, 3.8]

# Stats using math module
keep n = get list.len(data)
keep total = 0
for x in data:
    keep total = total + x
keep mean = total / n
show f"Mean: {mean}"

keep sq_diff_sum = 0
for x in data:
    keep diff = x - mean
    keep sq_diff_sum = sq_diff_sum + diff * diff
keep variance = sq_diff_sum / n
keep std = get math.sqrt(variance)
show f"Std Dev: {std}"
```

---

## 10. Release Notes v1.4.8 {#release-notes}

### New Features
- **`get`/`call` Module System**: Two equivalent keywords for idiomatic module calls
  - `keep x = get math.sqrt(16)` → 4
  - `keep y = call ai.chat("hello")` → `{response: ...}`
  - Works as statement (result discarded) or expression (can assign)
- **AI Module** (`ai.*`):
  - `ai.model_create(name, layers, task)` — create neural network
  - `ai.train(name, data, labels, epochs, lr)` — train model
  - `ai.predict(name, input)` — run inference
  - `ai.embed(text)` — 64-dim offline text embedding
  - `ai.chat(prompt, model?, system?)` — offline chat AI
  - `ai.model_save(name, path)` / `ai.model_load(path)` — persistence
  - `ai.model_info(name)`, `ai.models_list()`, `ai.loss_history(name)` — management
- **C VM Full Python Fallback**: All opcodes covered by Python VM; C extension is optional
- **Project Cleanup**: Removed nested v1.4.6 directory, `__pycache__`, `.pyc` files

### Bug Fixes
- GetModuleExpr now works in all expression contexts (nested calls, arithmetic, conditions)
- Module allowlist extended with all new AI functions

### Removed
- `MellowLang_v1_4_6/` nested directory (stale copy)
- All `__pycache__`, `*.pyc`, `.pytest_cache` directories
- Duplicate `*.egg-info` artifacts

### Migration from v1.4.7
All v1.4.7 code runs unchanged. New features are purely additive.
