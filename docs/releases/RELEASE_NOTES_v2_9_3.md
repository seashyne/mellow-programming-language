# Release Notes v2.9.3

Date: 2026-06-18

## Summary

2.9.3 is a patch stability release. It tightens release gates, removes the old
compatibility runtime names and direct-run CLI, separates experimental docs
from the core index, and ships the
`mellow-sdk` OpenAI-compatible provider package.

## Stability Gates

Run:

```powershell
.\scripts\test-v293-stability.ps1
```

This executes:

- `tests/core`
- `tests/language`
- package/registry smoke tests
- `mellow release-gate`

## Documentation Split

- Core index: `docs/CORE_DOCS.md`
- Experimental index: `docs/experimental/README.md`
- Canonical runtime modules: `compiler/bytecode.py`, `host/runtime.py`, and
  `vm/python_vm.py`

Agents, MMG, playground, desktop, and hosted-ecosystem docs now live under
`docs/experimental/`.

## mellow-sdk

See `docs/MELLOW_SDK.md` for the Python-shaped provider API.

## Upgrade Notes

- No stable-core language semantics changed in this patch.
- Invoke scripts with `mellow run <file>`; direct `mellow <file>` mode was removed.
- If you linked old experimental doc paths directly, update links to
  `docs/experimental/...`.
