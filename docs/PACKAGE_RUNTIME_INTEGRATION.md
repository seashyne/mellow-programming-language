# Package Runtime Integration

`mellow new my-app` now creates a project that already contains:

- `src/main.mel`
- `mellow.toml`
- project-local `mellow_packages/installed/*`
- `.mellow_imports.json`
- `.mellow_runtime.json`

This makes `pkg:` imports work immediately in a new project without requiring a remote registry.

## Example

```bash
mellow new hello-world
cd hello-world
mellow run src/main.mel
```

## Resolution order

When Mellow resolves package imports for a project, it now prefers:

1. project-local installed packages
2. local registry packages
3. bundled starter packages
4. remote registry fallback

## Project-local preload

Projects created with `mellow new` get starter packages installed into:

```text
mellow_packages/installed/
```

and the project manifest includes matching dependencies.
