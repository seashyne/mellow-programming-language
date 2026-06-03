# Lockfile and import auto-resolution

Mellow 1.5.8 writes a `mellow.lock` file whenever you install packages with `--project-dir` or run `sync-imports`.

Example:

```powershell
py -m mellowlang.cli.main install core-gamekit --registry https://registry.example --project-dir .
py -m mellowlang.cli.main sync-imports . --registry https://registry.example
```

The lockfile stores the resolved package versions and registry source.
The `.mellow_imports.json` file maps imported package names to the installed package entry file on disk.
