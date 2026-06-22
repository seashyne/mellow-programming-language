# Mellow CLI UX

Mellow CLI should be easy first, complete second.

## Rules

- Use workflow verbs for common tasks: `run`, `check`, `record`, `replay`, `test`, `release-gate`.
- Use long options for modifiers, not primary workflows.
- Keep `mellow -h` short enough to scan in one terminal screen.
- Put detailed argparse output behind `mellow help --full`.
- Keep old flags working when replacing them with clearer commands.
- Provide examples in `mellow guide <topic>`.
- Keep `mellow ask ...` offline by default. It should suggest commands, not execute them.

## Preferred Forms

```powershell
mellow record app.mellow replay.jsonl
mellow replay app.mellow replay.jsonl
mellow security audit
mellow release-gate
mellow config list
```

## Compatibility Forms

These remain supported for scripts and older documentation:

```powershell
mellow run app.mellow --record replay.jsonl
mellow run app.mellow --replay replay.jsonl
mellow replay app.mellow --input replay.jsonl
```

## AI Helper Scope

`mellow ask` is a command helper. It is good at mapping plain-language intent to CLI commands and guide topics. It should not claim to understand project code deeply. For code-level help, use `mellow assistant <file>`.
