# Release Checklist

For Mellow 2.9 and later, grammar or semantic changes must also:

- update the normative language specification
- update `spec/mellow-<version>-core.json`
- add Python and Full Native C conformance coverage
- bump the language minor version unless the change is a semantics-preserving bug fix

Use this checklist before tagging a stable Mellow Programming Language release.

## Version

- [ ] `pyproject.toml` version is updated.
- [ ] `src/mellowlang/__init__.py` version is updated.
- [ ] `README.md` title/version is updated.
- [ ] `CHANGELOG.md` has a dated entry.

## Quality Gate

- [ ] Stable core tests pass:

  ```powershell
  $env:PYTHONPATH = "src"
  $env:PYTHONDONTWRITEBYTECODE = "1"
  python -m pytest -q tests\core -p no:cacheprovider
  ```

- [ ] Doctor runs:

  ```powershell
  python -m mellowlang doctor
  ```

- [ ] Hello example runs:

  ```powershell
  python -m mellowlang run examples\hello.mellow
  ```

## Native VM

- [ ] Native build status checked:

  ```powershell
  python -m mellowlang native status
  ```

- [ ] If releasing native support, build the optional extension:

  ```powershell
  .\scripts\build-native-windows.ps1
  ```

## Git

- [ ] Working tree is clean.
- [ ] Release commit is on `main`.
- [ ] Tag created:

  ```powershell
  git tag vX.Y.Z
  git push origin main --tags
  ```

## Do Not Release

Do not include generated or local artifacts:

- `build/`
- `dist/`
- `.mellow/`
- `__pycache__/`
- `.pytest_cache/`
- `node_modules/`
- `*.pyd`, `*.pyc`, `*.exe`, `*.dll`
