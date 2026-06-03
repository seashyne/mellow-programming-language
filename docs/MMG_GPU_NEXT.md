# Mellow v2.3.1 GPU Runtime Extensions

This pack adds three concrete next-step layers on top of the v2.3.0 MMG GPU starter:

- sprite batching metadata and batch-friendly scene export
- shader pipeline source stubs for native OpenGL backend work
- input/state callback export so native backends can react to Mellow-authored events

It also adds two new media/data formats:

- `.sm` via **Mellow Smallless** for reversible source compression
- `.melv` for **Mellow Video** containers backed by frame sequences

## Important limits

The new GPU-facing native source is included and updated, but it is **not compiled in this environment** because SDL2/OpenGL development headers are not available here.
PNG texture loading is wired for target environments that provide `SDL2_image`; without it, runtime still falls back to BMP-only loading.
