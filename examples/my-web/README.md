# my-web

Scaffolded with `mellow new --preset web`.

## Quick Start

```bash
mellow web dev
```

Edit `src/App.mellow` to change the project entry point. Project settings live in `mellow.toml` and `mellow.json`.

## Web Preview

Prepare the generated React/Vite app without starting a server:

```bash
mellow web dev --prepare-only
```

Start the dev server:

```bash
mellow web dev
```

`mellow web dev` reads `web.entry` from `mellow.json` and installs the local `mellow-web` package when needed.

## Starter Packages

No starter packages are preloaded. This keeps the project native-minimal and avoids generated package metadata.

Create a package starter when you need package examples:

```bash
mellow new my-web --preset web --with-core
```

## Add Packages

Add a dependency to this project and install it:

```bash
mellow add core-print
```

Then import it from `src/App.mellow` when package imports are supported by your runtime target:

```mellow
import "pkg:core-print" as out
```

Useful package commands:

```bash
mellow search core
mellow pkg list
mellow sync-imports .
```
