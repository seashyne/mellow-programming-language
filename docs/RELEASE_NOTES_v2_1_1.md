# Mellow v2.1.1 Standalone Opcode Migration Pack

Highlights:
- moved more opcode coverage into the pure-C standalone runtime
- locals and frame-local windows
- call/return with function refs
- compare ops and branch-oriented execution
- list/map builders
- syscall bridge contract for host integration
- `stdlib/core.mellow` added as a recommended language-level core module

Important note:
- `core.mellow` is recommended, not mandatory, for the C VM itself
- the runtime can boot without it
- the module is useful as the ecosystem-level stable surface for helpers and future stdlib wiring
