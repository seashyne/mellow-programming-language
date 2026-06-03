# Mellow Playground Pro

## Features
- Syntax highlighting and line numbers
- Timeline and debugger views
- Workflow graph visualization
- Shareable sessions on the local playground server

## Commands
```bash
mellow playground
mellow playground --port 8787
```

## Share flow
1. Run or compile code in the playground.
2. Click **Share session**.
3. Open the generated `/s/<session-id>` link while the local server is still running.

## Notes
- Sessions are stored in-memory and are intended for local development demos.
- Trace mode can be disabled if you only want compile/run without debugger data.
