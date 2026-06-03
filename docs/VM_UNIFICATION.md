# VM Unification

Mellow v2.0 introduces a unified debugger payload contract.

- `typed_stack` gives per-slot types, reprs and sizes.
- `typed_locals` / `typed_globals` expose typed scope views.
- `watch_expressions` evaluates debugger expressions safely in a restricted context.
- `source_span` adds start/end coordinates for the current instruction.

Current limitation: when native C hooks are unavailable, paused debugging uses the Python inspector path to preserve a stable debugging surface.
