# Mellow Magic Graphics (MMG)

MMG is the graphics/runtime direction for Mellow.

## Current scope in this pack

- `core-mmg` starter package
- `mellow mmg run` runtime command
- canvas primitives: `rect`, `circle`, `line`, `text`
- `.mel`-first authoring flow

## Important

This is **not** a full OpenGL replacement yet. It is the first practical MMG foundation that makes graphics apps possible from Mellow source today.

## Example

```bash
mellow mmg status
mellow mmg run starter_packages/core-mmg/examples/demo.mel
mellow mmg run starter_packages/core-mmg/examples/demo.mel --dump-spec
```
