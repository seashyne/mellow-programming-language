# Mellow v1.9.9 — Full Paused VM Debugger Pack

Highlights:
- full paused Python VM debugger flow for Playground sessions
- pause/resume at real instruction boundaries
- step into / step over / step out
- live frame + locals + stack snapshots at pause points
- bytecode window with bytecode-to-source mapping
- opcode breakpoints and instruction breakpoints

What changed:
- `src/mellowlang/vm/legacy.py`
  - added runtime-paused debugger controller
  - added snapshot generation for stack/locals/globals/frames
  - added resume commands and per-instruction pause logic
- `src/mellowlang/vm/vm.py`
  - added debugger config fields for pause-on-start / instruction breaks / opcode breaks
- `src/mellowlang/playground/server.py`
  - added debugger session APIs
    - `POST /api/debug/start`
    - `POST /api/debug/command`
    - `GET /api/debug/session/<id>`
- `src/mellowlang/playground/assets/index.html`
  - added debugger control buttons
- `src/mellowlang/playground/assets/app.js`
  - added live debugger UI wiring

Notes:
- paused debugger currently targets the Python VM path and is the reference “full Mellow VM debugger” implementation.
- C VM execution remains available for normal runs, but paused stepping is intentionally routed through the Python VM for correctness and inspectability.
