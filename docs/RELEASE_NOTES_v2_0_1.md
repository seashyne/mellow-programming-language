# Mellow v2.0.1 Native C Debug Hook Parity Pack

This pack improves VM parity reporting and debugger payload shape across Python and C execution paths.

Included:
- native C capability probing (`_mellowvm.capabilities()` when rebuilt)
- facade-level engine/detail reporting
- richer typed frame snapshots in debugger payloads
- source span text included alongside span coordinates
- playground payload now surfaces native C parity metadata

Current limitation:
- the shipped prebuilt native extension is conservative and still reports debug parity features as unavailable until the extension is rebuilt with real pause/inspect hooks.
