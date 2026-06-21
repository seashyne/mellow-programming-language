# Mellow 1.6.4 — CLI UX Upgrade

## Highlights

- Run files directly with `mellow script.mellow` or `mellow script.mel`
- Better top-level command suggestions for typos such as `mellow serch`
- Auto-fetch now reports packages installed during `mellow run`
- `mellow search --interactive` can install or add the chosen package immediately
- `mellow add` now fully supports `--alias` without crashing
- Cleaner CLI status output and clearer hints for package failures

## Example

```bash
mellow examples/hello.mellow
mellow search openai --interactive
mellow add @ai/openai --alias gpt
```
