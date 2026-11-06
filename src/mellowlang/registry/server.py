"""The Mellow package registry server: a store, an HTTP handler and a launcher.

The machinery lives in `mellowlang/registry/server_groups/`, one module per
concern; this module keeps the import path `mellowlang.registry.server` that
`registry/__init__.py`, the `mellow pkg serve` command and `python -m
mellowlang.registry.server` already use."""

from __future__ import annotations

from .server_groups.store import (
    RegistryStore,
)

from .server_groups.handler import (
    Handler,
)

from .server_groups.launch import (
    main,
    run_registry_server,
)

if __name__ == "__main__":
    raise SystemExit(main())
