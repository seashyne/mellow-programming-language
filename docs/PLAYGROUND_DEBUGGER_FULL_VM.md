# Playground Full VM Debugger

New endpoints:

- `POST /api/debug/start`
  - starts a paused debugger session at instruction 0
- `POST /api/debug/command`
  - commands: `continue`, `step_into`, `step_over`, `step_out`, `stop`
- `GET /api/debug/session/<id>`
  - reads latest paused state

Returned pause payload includes:
- `pc`
- `opcode`
- `operands`
- `line` / `col`
- `source`
- `stack`
- `locals`
- `globals`
- `frames`
- `bytecode_window`

Example flow:

```bash
mellow playground
```

In the UI:
1. Click **Debug**
2. Use **Into / Over / Out / Continue**
3. Inspect locals, stack, and frames in the debugger panel
4. Add source breakpoints by clicking the gutter
5. Add opcode breakpoints like `CALL,RETURN`
