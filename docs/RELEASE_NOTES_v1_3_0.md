# Release Notes — v1.3.0 (NEW Hybrid)

## Added
- `mellow test` command with dual-engine mode:
  - `mellow test tests --engine=dual`
- `mellow replay` and `mellow diff` commands.
- Modern `mellow run` now includes `--engine=auto|py|c` (modern CLI).

## Changed
- Hybrid runtime policy:
  - Default engine remains `auto` (prefer C VM if available).
  - If `--record` or `--replay` is used, runtime will use the Python engine to guarantee deterministic log semantics.

## Docs
- `docs/parity_matrix.md`
- `docs/v1_3_0_new.md`
