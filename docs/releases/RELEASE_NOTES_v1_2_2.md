# MellowLang v1.2.2

## UX / Game Script Improvements

### ✅ Named arguments in function calls (game-friendly)
You can now write calls like:

```mellow
file_write("notes.txt", "hello\n", mode="w")
file_append("notes.txt", "world\n", mode="a")
```

Under the hood, named args are compiled as a trailing map argument to keep the v1.x VM/bytecode stable.

### ✅ Better “AI-ish” error hints
- **Unknown skill** errors now suggest close names (typos)
- **Unknown statement** errors now add small hints when the line looks like a function call / named args

## Tooling
- No changes to CLI commands in this patch (doctor/explain remain in modern commands as in v1.2.1)
