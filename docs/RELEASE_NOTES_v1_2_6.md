# MellowLang v1.2.6 (Hybrid C VM)

## Highlights
- Hybrid runtime: optional C-accelerated VM (`mellowlang._mellowvm`) with broader opcode coverage.
- C VM now supports **user-defined functions** (`CALL/RETURN/ARG`) via `func_table`.
- Added support in C VM for common core ops: boolean ops, len/getitem, build list/map, list_has/list_put, RNG seed/random/randfloat, wait/ask (permission gated), and legacy save/load mapping.

## CLI
- `mellow run <file.mellow> --engine=auto|py|c`
  - `auto` (default): try C VM, fallback to Python VM on missing opcodes or if extension is not built.
  - `c`: require C VM (errors if extension missing or opcode unsupported).
  - `py`: force legacy Python VM.

## Notes / Known gaps
- Some advanced error handling (e.g. TRY/CATCH semantics parity) may still fallback to Python VM in `--engine=auto` mode.
