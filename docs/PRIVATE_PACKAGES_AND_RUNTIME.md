# Private packages and runtime resolver

## Package visibility

Add this to `mellow.toml`:

```toml
visibility = "private"
```

Private packages are visible only to the package owner when using an authenticated token against the public registry.

## Runtime resolver

Build the runtime map for a project:

```powershell
py -m mellowlang.cli.main resolve-runtime . --registry https://your-registry.example
```

This writes `.mellow_runtime.json` and resolves package imports from installed packages.

## Import syntax

Mellow now supports:

```mellow
use core-ai as ai
need core-gamekit as gamekit
import math as math
keep net = get("http")
```

Use `use` or `need` for package-style imports. Use `get("module")` when you want a host/builtin module directly.

## Missing imports

If an import cannot be resolved:

- `sync-imports` tries to install it from declared dependencies
- `resolve-runtime --strict` fails with a clear list of missing imports
- non-strict mode writes the missing names into `.mellow_runtime.json`
