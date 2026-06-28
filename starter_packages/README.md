# Mellow starter_packages

This directory contains the default starter packages shipped with Mellow.
Each package is written in `.mellow`; older `.mel` mirrors may exist for legacy
host surfaces.

Example:
```mellow
import "pkg:core-print" as out
out.banner("hello")
```

- core-canvas: native headless canvas drawing helpers
- core-window: desktop app preset helpers
