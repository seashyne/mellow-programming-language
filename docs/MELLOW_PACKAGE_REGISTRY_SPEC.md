# Mellow Package Registry Spec (v1.5.2)

## Goals
Build a production-oriented package ecosystem for Mellow with a small core, deterministic packaging, simple auth, and a path to enterprise scaling.

## Core Concepts
- **Manifest**: `mellow.toml` is the preferred format. `mellow.pkg.json` remains supported for backwards compatibility.
- **Archive**: `.mpkg` zip archive containing source, manifest, readme, tests, and assets.
- **Registry**: HTTP service that stores package metadata and archives.
- **CLI**: `mellow pkg ...` commands for creation, publish, install, login, search, and registry config.

## Manifest
Preferred file: `mellow.toml`

```toml
name = "@studio/physics2d"
version = "0.1.0"
description = "2D helpers for Mellow games"
entry = "src/main.mellow"
license = "MIT"
authors = ["c"]
keywords = ["physics", "game", "mellow"]

[dependencies]
@studio/vector = "^1.0.0"
mathx = "^0.3.0"
```

Required fields now:
- `name`
- `version`
- `entry`

Recommended fields:
- `description`
- `license`
- `authors`
- `keywords`
- `dependencies`

## Package Layout
```text
mypkg/
├ mellow.toml
├ mellow.pkg.json        # optional compatibility mirror
├ README.md
├ src/
│ └ main.mellow
├ tests/
│ └ basic_test.mellow
└ assets/
```

## HTTP API
Base path: `/api/v1`

### Health
- `GET /health`

### Auth
- `POST /auth/login`
- `GET /auth/whoami`

### Search
- `GET /packages/search?q=<text>`

### Package metadata
- `GET /packages/{name}`
- `GET /packages/{name}/versions/{version}`
- `GET /packages/{name}/download/{version}`

### Publish
- `POST /packages/publish`
- Requires `Authorization: Bearer <token>`

## CLI Contract
```bash
mellow pkg init mypkg
mellow pkg build mypkg
mellow pkg serve --host 127.0.0.1 --port 8089
mellow pkg registry http://127.0.0.1:8089
mellow pkg login --username admin --password admin
mellow pkg whoami
mellow pkg search physics
mellow pkg publish mypkg --online
mellow pkg install @studio/physics2d --online
```

## Local Storage
Client:
- config: `~/.mellow/config.json`
- installs: `mellow_packages/installed/<name>/current`
- local registry mirror: `mellow_packages/registry`

Server:
- packages: `<data-dir>/packages/<name>/<version>/`
- package index: `<data-dir>/index.json`
- users: `<data-dir>/users.json`
- tokens: `<data-dir>/tokens.json`

## Roadmap
Current 1.5.2:
- exact version install from remote registry
- search, publish, install, login, whoami
- SHA-256 integrity metadata

Next recommended milestones:
1. semver resolver (`^`, `~`, ranges)
2. lockfile generation (`mellow.lock`)
3. transitive dependency install
4. package signing and namespace ownership
5. PostgreSQL + object storage backend for hosted registry
