# MellowLang Style Guide (Recommended Modern Style)

MellowLang supports multiple syntaxes for friendliness.
For consistency in teams and tutorials, we recommend this **modern style**.

## Output
Preferred:
- `print("hello")`

Also supported:
- `show("hello")`

## Input
Preferred:
- `name = input("your name: ")`

Also supported:
- `name = ask("your name: ")` (may be sandbox-disabled unless `--allow-ask`)

## Loops
Preferred (Python-like):
- `for i in range(0, 10): ...`
- `while cond: ...`

MellowLang also supports additional loop styles for compatibility, but tutorials should prefer the above.

## Naming
- variables: `snake_case`
- constants: `UPPER_SNAKE_CASE`
- skills/functions: `verb_noun` (e.g. `move_to`, `calc_score`)

## CLI
Recommended:
- `mellow run file.mellow`
- `mellow check file.mellow`
- `mellow fmt -w .`

Use the documented canonical syntax and explicit CLI subcommands.


### Modern keywords

Prefer these in new code:
- `let` / `def` / `print` / `input`
- `for ... in range(...)` and `while ...`

Avoid:
- `end` (not used)
- mixing multiple styles within the same file (choose one style per project)
