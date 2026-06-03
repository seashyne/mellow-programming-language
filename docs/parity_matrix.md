# Parity Matrix (Python VM vs C VM)

This document tracks feature parity between engines.

Legend:
- ✅ parity
- ⚠️ partial / known gaps
- ❌ not supported

| Feature | Python VM | C VM | Notes |
|---|---:|---:|---|
| Core expressions (math/compare) | ✅ | ✅ | |
| Variables (keep/auto) | ✅ | ✅ | |
| Functions (CALL/RETURN/ARG) | ✅ | ✅ | |
| TRY/CATCH | ✅ | ✅ | Jumps to catch frame; error surfaces mapped via pc |
| Host/skills syscall | ✅ | ✅ | C VM calls host via bridge |
| Debug trace/step/break | ✅ | ⚠️ | Trace/step supported; step UX parity is WIP |
| Replay record/replay | ✅ | ⚠️ | v1.3.0: auto forces Python when record/replay is used |
| Memory quota | ✅ | ⚠️ | Implemented in Python; C VM WIP |
