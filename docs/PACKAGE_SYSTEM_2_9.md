# Mellow Package System 2.9

Status: usable for local development, self-hosted registries, and the deployed
public registry at
`https://mellow-public-registry.jirayut-wh.workers.dev`.

## Package format

- Preferred manifest: `mellow.toml`
- Compatibility manifest: `mellow.pkg.json`
- Archive: deterministic ZIP-compatible `.mpkg`
- Project lockfile: `mellow.lock`
- Import map: `.mellow_imports.json`
- Runtime map: `.mellow_runtime.json`
- Alias map: `.mellow_aliases.json`

Packages declare a name, version, entry file, metadata, visibility, and
dependencies. Version constraints support exact versions, `*`, `latest`, `^`,
`~`, comparison operators, and comma-separated constraints.

Creator metadata is first-class. Set `authors` in `mellow.toml` or
`mellow.pkg.json`; the CLI also accepts `mellow pkg init --author "Name"`.
Search, info, install, publish, and installed-package lists display the package
creator. Older packages without author metadata display `unknown`.

Registry metadata now includes ecosystem fields when available:

- `downloads`
- `published_at`
- `license`
- `keywords`
- `badges` such as `official`, `verified`, and `deprecated`
- package signature metadata from `/signature`

## Storage and resolution

Resolution uses this order:

1. project-local installed packages
2. local registry packages
3. bundled starter packages
4. configured remote registry

The default project-local layout is:

```text
mellow_packages/
  installed/<name>/current/
  registry/<name>/<version>/
```

User configuration, cached archives, and signing keys live under
`~/.mellow/` by default. Set `MELLOW_CONFIG_DIR` to isolate them.

## Main commands

```bash
mellow pkg init ./my-package --name my-package --author "Your Name"
mellow pkg build ./my-package
mellow pkg publish ./my-package
mellow pkg install my-package

mellow registry https://registry.example.com
mellow login --token TOKEN
mellow search my-package
mellow info my-package
mellow author "Your Name"
mellow profile "Your Name"
mellow verify my-package
mellow trust "Mellow Code Team"
mellow verify --strict my-package
mellow signature my-package
mellow publish ./my-package
mellow install my-package --project-dir .

mellow add my-package
mellow remove my-package
mellow update --check
mellow update my-package
mellow update --all
mellow uninstall my-package

mellow seed-core ./packages
mellow sync-imports .
mellow resolve-runtime .
mellow diagnose-imports .
```

Use `--online` with the grouped `mellow pkg publish/install` commands. The
top-level `publish`, `install`, `search`, and auth commands use the configured
remote registry directly.

## Current capabilities

- local and HTTP registry publish, search, install, and authentication
- recursive dependency installation
- lockfile and project-local installs
- package cache and SHA-256 archive verification
- Ed25519 manifest signing when the `security` extra is installed
- namespace ownership enforcement in the registry implementation
- private package visibility with registry authentication
- package aliases, autocomplete suggestions, and import diagnostics
- automatic runtime/import map generation
- archive path-traversal protection
- creator/author metadata shown in package search, info, install, publish, and list output
- author/profile package listings
- checksum/signature verification with `mellow verify` and `mellow signature`
- local creator trust policy with `mellow trust` and strict signature verification
- update planning with `mellow update --check`, targeted updates, and lockfile refresh
- registry browse page at `/packages?q=<query>`
- registry package detail pages at `/packages/<name>`
- package badges, downloads, publication time, license, and keywords

## Bundled package sets

Starter packages include:

`core-ai`, `core-canvas`, `core-collections`, `core-data`, `core-gamekit`, `core-http`,
`core-json`, `core-ledger`, `core-math`, `core-mmg`, `core-money`,
`core-print`, `core-save`, `core-storage`, `core-strings`, `core-time`,
`core-window`, and `core-workflow`.

The local registry also contains `core-melv` and `core-sm`. `core-melv` now has
a complete starter manifest for the dependency-free MELV2 path; `core-sm` still
needs a complete starter manifest before joining the starter package set.

The default `mellow new` set is intentionally smaller: `core-print`,
`core-strings`, `core-collections`, `core-math`, `core-json`, and `core-time`.
Use presets such as `app`, `automation`, `finance`, `data`, `ai-agent`,
`gamekit`, and `api-webhook` to opt into domain packages.

The scoped standard-library package set contains:

`@mellow/std-ai`, `@mellow/std-console`, `@mellow/std-game`,
`@mellow/std-http`, `@mellow/std-json`, and `@mellow/std-storage`.

## Publishing an update

1. Change the package version in `mellow.toml`.
2. Keep `mellow.pkg.json` synchronized when the compatibility manifest exists.
3. Run the package tests and build the archive.
   The CI release gate also checks manifest synchronization, archive safety,
   signature verification, and a clean install smoke test:

   ```bash
   python scripts/package_release_gate.py
   ```
4. Publish to a local registry first.
5. Publish the same immutable version to the configured remote registry.

Registries reject overwriting an existing version. Publish a new patch, minor,
or major version instead.

## Known boundaries

- Package tooling is still implemented in Python and is outside the frozen
  Full Native C Core Profile.
- The repository registry server is suitable for development and self-hosting;
  production deployment still needs durable database/object storage,
  operational monitoring, backups, rate limiting, and key rotation.
- Package signing is optional rather than mandatory.
- `core-sm` needs a complete starter manifest and package-level tests before
  joining the starter package set.
