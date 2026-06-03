# MellowLang v1.1.1

This is a hotfix release.

## Fixes
- Fixed a SyntaxError in `src/mellowlang/vm/legacy.py` caused by a stray `import time as _time` line in the opcode dispatch section. This prevented `mellow --version` (and any CLI command) from starting.

## Compatibility
- No language/CLI breaking changes from v1.1.0.
