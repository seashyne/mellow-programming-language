# Standalone Opcode Migration Notes

## Should Mellow have `core.mellow` or `.mel`?

Yes, **recommended**.

Not because the standalone VM needs it to execute bytecode, but because the language should expose a stable core module for:
- helper functions
- future stdlib imports
- host/runtime capability shims
- keeping language-level APIs separate from the C runtime internals

## Rule of thumb

- **C runtime core**: does not require `core.mellow`
- **Mellow language ecosystem**: should have `stdlib/core.mellow`

Use `.mellow` as the primary canonical extension. Support `.mel` only as a short alias if you want it.
