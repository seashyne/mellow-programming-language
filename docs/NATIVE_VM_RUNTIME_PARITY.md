# Native VM Runtime Parity (v2.0.3)

## New run controls

```python
from mellowlang.vm import MellowVM, RunConfig

vm = MellowVM()
result = vm.run(program, config=RunConfig(
    engine='c',
    native_allow_fallback=False,
    native_require=True,
))
```

## What changed

- The VM facade records `last_native_result` with fallback metadata.
- `run_bytecode_ex()` returns a structured result instead of hiding whether Python was used.
- When native execution is required, unsupported runtime paths now raise `NATIVE_REQUIRED`.

## Remaining gaps

Native-only execution is still blocked for:

- debugger parity
- record/replay parity
- event handler parity

Those areas still route to Python unless native execution is explicitly required, in which case the runtime fails fast.
