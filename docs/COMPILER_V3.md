# Mellow Compiler v3

Status: active development compiler on the `dev/2.9.5` branch.

## Pipeline

```text
UTF-8 source -> parser -> typed AST -> IR -> optimizer -> bytecode/native runtime
```

`mellowlang.compiler.Compiler` is the only source compiler facade. The
standalone image compiler uses the same facade and IR. There is no legacy
source compiler and no silent compiler fallback.

The bytecode backend is a v3 IR backend. It serializes IR operations for the
VM and must not be confused with the deleted legacy source-to-bytecode
compiler.

## Stability Contract

- The frozen Mellow 2.9 Core Profile must compile through v3 IR.
- Python and Native C execute bytecode emitted from the same IR backend.
- Standalone images report `v3-ir-bytecode` or `v3-ir-opt-bytecode`.
- Unsupported Extended or Experimental syntax raises a `COMPILER` error that
  identifies the missing lowering feature.
- Adding a fallback compiler is prohibited by the source-structure gate.

## Optimizer Boundary

The optimizer is enabled only for AST shapes whose control-flow and data-flow
passes are proven safe. Functions, events, control flow, indexed expressions,
and stateful host calls currently use unoptimized v3 IR. This is still the v3
pipeline; it is not a fallback.

## Required Gates

```powershell
py -3.11 -m pytest -q tests/core tests/language tests/native -p no:cacheprovider
```

Standalone compilation must additionally prove that the Core conformance
fixture produces a v3 pipeline image.
