# Native Mellow VM

Mellow now ships a native C VM source tree in `native/mellowvm/` and a CLI workflow to inspect and build it.

## Commands

```bash
mellow native status
mellow native build
mellow native doctor
```

## Notes

- `mellow native status` shows whether the current Python can load the extension.
- `mellow native build` runs `python setup.py build_ext --inplace`.
- If Python development headers are missing, the build will fail cleanly and the Python VM remains available.
- The runtime still auto-falls back to Python VM when the extension is not loadable.
