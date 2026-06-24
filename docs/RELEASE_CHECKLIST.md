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

- [ ] Native doctor runs without Python:

  ```powershell
  mellow doctor
  ```

- [ ] Native hello example runs:

  ```powershell
  mellow run examples\hello.mellow
  ```

## Native Runtime

- [ ] Standalone native runtime builds:

  ```powershell
  cmake -S native\standalone -B build\standalone-release -DCMAKE_BUILD_TYPE=Release
  cmake --build build\standalone-release --config Release
  ```

- [ ] Standalone native runtime smoke test passes:

  ```powershell
  .\build\standalone-release\Release\mellow.exe doctor
  .\build\standalone-release\Release\mellow.exe check examples\hello.mellow
  .\build\standalone-release\Release\mellow.exe run examples\hello.mellow
  ```

- [ ] GitHub Actions `core-tests` passes, including `native-safety`.

## Native-first release pipeline

Mellow 2.9.6 and later ship native C artifacts from GitHub Actions.

To create a release from the current release branch:

```powershell
git tag vX.Y.Z
git push origin vX.Y.Z
```

The `release` workflow builds and uploads:

- `mellow-<version>-windows-x64.zip`
- `mellow-<version>-linux-x64.tar.gz`
- `mellow-<version>-macos-x64.tar.gz`
- `mellow-<version>-macos-arm64.tar.gz`
- `mellowlang-<version>.vsix`
- `mellowlang-<version>.tgz`

Only tag pushes create a GitHub Release. To check packaging without publishing
a release, run the `release` workflow manually with `workflow_dispatch`.

Native archives include:

- `bin/mellow` or `bin/mellow.exe`
- `bin/mellowrt` or `bin/mellowrt.exe`
- `LICENSE`
- `NOTICE.md`
- `README.md`
- `INSTALL.md`
- the matching native install helper.

## Git

- [ ] Working tree is clean.
- [ ] Release commit is on `main` or the active release branch.
- [ ] Tag created:

  ```powershell
  git tag vX.Y.Z
  git push origin vX.Y.Z
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
