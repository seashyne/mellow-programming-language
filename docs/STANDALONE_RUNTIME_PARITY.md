# Standalone Runtime Parity

## Image format

The standalone VM now consumes a binary image format called **MLVI v2**.

The image contains:

- source name
- pipeline name
- constant pool
- bytecode
- source spans
- globals table
- function table
- event table
- module table

## Module/core loading

Standalone images can now carry module metadata, including a `core` module hint when `stdlib/core.mellow` or `stdlib/core.mel` is present in the project.

At runtime this is currently used for parity metadata and loader visibility. Full module execution parity will be layered on top of the same image contract in later releases.

## Syscalls

The native standalone runtime currently exposes:

| Syscall ID | Name | Behavior |
|---|---|---|
| 1 | print | prints values to stdout |
| 2 | len | returns length for strings/lists/maps |
| 3 | clock_ms | returns process CPU clock in milliseconds |
| 4 | getenv | fetches an environment variable |
| 5 | str | converts a value to string |
| 6 | type | returns the value tag name |

## Current limitations

- `IMPORT` is a metadata/runtime no-op in this pack.
- Event dispatch metadata exists, but native event handler execution is not yet wired up.
- Standalone compilation still uses the Python compiler frontend to produce the `.mvi` image.
