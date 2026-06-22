# MellowLang v1.1.0

## Phase 2: Performance + Sandbox + Packaging

### New CLI flags (run)
- `--max-steps N` sandbox step limit
- `--max-ms MS` sandbox time limit (milliseconds)
- `--syscall-budget N` sandbox syscall budget
- `--no-storage` disable storage APIs
- `--storage-dir PATH` change storage base directory
- `--profile` return execution stats (steps, elapsed_ms, opcode_counts)

### New commands
- `mellow pack <entry.mellow> --out dist/mellow_pack.zip`
  - creates a portable bundle for game/mod distribution:
    - entry script
    - optional `libs/`, `assets/`
    - `mellow.json` manifest

### Sandbox behavior
- base storage directory: `mellow_saves` (default)
- base directory is auto-created on first storage use
- user subfolders are **not** auto-created (prevents surprising writes)
