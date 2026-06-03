# Mellow starter_packages

This directory contains the default starter packages shipped with Mellow.
Each package is written in `.mel` and mirrored to `.mellow` for compatibility with older tooling.

Example:
```mellow
import "pkg:core-print" as out
out.banner("hello")
```

- core-window: desktop app preset helpers
