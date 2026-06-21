# Testing MellowLang

This repo uses **pytest** for automated tests.

## Run all tests

From the project root:

```bash
python -m pytest -q
```

If you want verbose output:

```bash
python -m pytest -vv
```

## Run a single test file

```bash
python -m pytest -q tests/test_cli.py
```

## Run a single test by name

```bash
python -m pytest -q -k doctor
```

## Lint / format (CLI)

These are developer tools for scripts (not Python code):

```bash
mellow check path/to/file.mellow
mellow fmt path/to/file.mellow --check
mellow fmt path/to/file.mellow -w
```

## Mellow script tests

`mellow test` runs `.mellow` files directly. It is the preferred language-level
test command for examples, conformance fixtures, and eventual native gates.

```bash
mellow test tests/language/fixtures --engine=py
mellow test tests/language/fixtures --engine=c
mellow test tests/language/fixtures --engine=dual
mellow test tests/language/fixtures --engine=py --json
mellow test tests/language/fixtures --engine=c --native-required
```

If a test file has a sibling golden output file, stdout must match exactly:

- `example.mellow`
- `example.mellow.out`

Without a golden output file, the test passes when the script runs without a
runtime error.

## Golden tests for error messages

Error output is part of Mellow's UX. When changing error formatting,
add or update a **golden test**.

Pattern used in this repo:

1. Arrange: provide a small `.mellow` source string (or temp file).
2. Act: compile/run and capture the formatted error text.
3. Assert: compare against an expected multi-line string.

Tips:
- Always include `file:line:col`
- Always include the code frame with `>` and `^`
- Keep expected outputs stable across platforms (avoid absolute paths)

## Spec tests ("must error" rules)

When a language rule requires an error, add a test that asserts:

- the error **kind** (SYNTAX / RUNTIME / SANDBOX)
- the **error id** (if applicable)
- the **location** (line/col)
- a short, stable message fragment

This makes refactors safe and keeps v1.x backwards-compatible.
