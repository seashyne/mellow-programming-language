# Mellow v1.9.6 Playground Pro Pack

## Added
- Syntax-highlighted playground editor with line numbers
- Execution timeline panel backed by VM trace data
- Step debugger with previous/next navigation and watch-value display
- Workflow/CFG graph panel for visual inspection
- Shareable local sessions via `/api/share` and `/s/<session-id>`

## Updated
- Playground server now returns timeline, trace events, graph metadata, and editor metadata
- Playground API now supports session loading and shared session URLs

## Notes
- Trace-backed timeline/debugger currently use the Python VM trace mode for fidelity
- Shared sessions are in-memory for the running local playground server
