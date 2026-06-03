# Mellow v2.1 Standalone Runtime Core Pack

## Highlights

- new `native/standalone/` tree for the future Python-free runtime
- `MValue` typed value model in pure C
- `MInstruction`, `MProgram`, `MFrame`, `MDebugSnapshot`, and `MVM` runtime contracts
- minimal standalone VM loop for arithmetic/control-flow subset
- new CLI family: `mellow standalone ...`

## Notes

This pack is an architectural extraction milestone, not full feature parity.
It reduces future migration risk by defining the standalone runtime contracts explicitly.
