# Mellow Runtime Parity Matrix 3.0

Status: draft

Legend:

- `pass`: expected to work in the runtime.
- `fallback`: routes through the Python VM or host bridge when needed.
- `partial`: implemented but not complete enough to claim stable parity.
- `unsupported`: not available in that runtime.

| Surface | Python VM | Native C VM | v3 Status | Notes |
| --- | --- | --- | --- | --- |
| Core arithmetic | pass | pass | core | Covered by `tests/core` and native parity tests. |
| Variables and assignment | pass | pass | core | Stable core behavior. |
| `def` and calls | pass | pass | core | Native parity must stay covered. |
| `if` / `else` | pass | pass | core | Stable core behavior. |
| `while` | pass | pass | core | Stable core behavior. |
| `for ... in range(...)` | pass | pass | core | Stable core behavior. |
| Lists and maps | pass | pass | core | Literal/indexing parity required. |
| Strings | pass | pass | core | UTF-8 source is required. |
| Undefined-name diagnostics | pass | partial | core | Python VM raises a runtime error; native parity must match. |
| Money core | pass | pass | core-host | Decimal semantics are host-backed. |
| Data processing | pass | pass | core-host | Bounded data helpers are stable when enabled. |
| Ledger core | pass | pass | core-host | Hash-chain behavior must remain deterministic. |
| Package imports | pass | fallback | extended | Runtime resolution is still host/tooling assisted. |
| `interop` module | pass | fallback | extended | External process execution stays host-backed and allowlisted. |
| Network helpers | pass | fallback | extended | Deny-by-default project permissions. |
| Secure save | pass | fallback | extended | Optional security dependency may be required. |
| LSP | pass | unsupported | tooling | Editor tooling, not runtime execution. |
| Debugger | pass | partial | tooling | Native debugger parity is not yet complete. |
| Record/replay | pass | fallback | tooling | Python VM remains canonical replay path. |
| Events | pass | fallback | extended | Native event parity is not complete. |
| Agents | pass | unsupported | experimental | Platform feature, not v3 core. |
| Desktop/MMG/video | pass | unsupported | experimental | Host/runtime-specific surfaces. |

## Release Rule

v3 may claim "native core parity" only when:

```powershell
py -3.11 -m pytest -q tests/native -p no:cacheprovider
```

passes in CI or the release notes clearly mark native parity as partial.
