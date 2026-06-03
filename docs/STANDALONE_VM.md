# Standalone Mellow VM

Mellow v2.1.2 adds a native standalone image path for the pure-C runtime.

## Commands

```bash
mellow standalone status
mellow standalone build
mellow standalone compile examples/hello.mellow -o examples/hello.mvi
mellow standalone run examples/hello.mvi
```

## File format

The standalone runtime consumes `.mvi` files.

The format is a simple text image with:

- source name
- globals table
- function metadata
- constant pool
- instruction stream
- source spans

This keeps the first standalone VM format easy to inspect and debug.

## Notes

- The execution path for `mellow standalone run` is native C once the `.mvi` image is produced.
- The Python compiler is still used to emit the `.mvi` image in this release.
- The runtime no longer depends on `Python.h`.
