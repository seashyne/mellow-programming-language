# MellowLang Roadmap

MellowLang is a **friendly sandbox scripting language** focused on **game scripting** and **AI behavior**.
The goal is to compete with Python/Lua in the *scripting* space by being:

- **Easier to embed** (safe sandbox + allowlisted host modules)
- **More deterministic** (seed + record/replay)
- **Better developer UX** (clear errors + stable CLI + good tooling)

## Guiding Principles

1. **No breaking CLI in v1.x**  
   Only additive changes. Old flags keep working.
2. **Deterministic by default (when configured)**  
   Same inputs → same results (seed + replay logs).
3. **Modern, readable syntax**  
   Keep aliases for familiarity, but recommend a single “modern style”.

---

## v1.x (Stability + UX)

### v1.4.0 (current)
- Standard library expansion (game/AI oriented)
  - `get("game")` allowlisted module (pure deterministic helpers)
  - easing + tween step helper
  - grid neighbors + A* pathfinding
- Keep v1.x compatibility (additive)

### v1.3.5
- Always-online standard: Networking built-ins (HTTP + WebSocket)
- Hybrid Save (Level C): server-signed saves + local encrypted saves
- Project mode permissions for net allowlists + quotas
- Docs + tests updated for networking + signed saves

### v1.3.4
- Secure Save System standard (`*.msav`): encrypted + tamper-evident
- Project mode permission for save (deny-by-default)
- Docs + tests updated for save

### v1.0.3 (history)
- Restructure internals into packages: `compiler/`, `vm/`, `host/`
- Lock API between **CLI ↔ Compiler ↔ VM**
- Fix CLI/runtime mismatches
- Add `print(...)` alias of `show(...)`
- Add `input(...)` alias of `ask(...)`
- Document: CLI, Capabilities, Style Guide, Roadmap

### v1.1 – v1.3
- Better diagnostics: error span + caret + nearby lines everywhere
- `mellow check` upgrades: lint + warnings + suggestions
- Improve formatter (`mellow fmt`) and introduce `--fix`
- VS Code: better highlighting + diagnostics roundtrip

---

## v1.4 – v1.8 (Performance + Determinism)

- Bytecode improvements (smaller + faster)
- Deterministic runtime improvements (replay coverage for more ops)
- Sandbox budgets (time/cost limits per script)
- Module system: versioned allowlist + project-local libs

---

## v2.0 (Ecosystem)

- Debugger: breakpoints, step, watch
- Profiler: time/cost hotspots
- Packaging: `mellow pack` → distributable bundles
- Standard library expansion (game/AI oriented)
