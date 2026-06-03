# Mellow Package Registry Spec v1.5.3

## Goal
Provide an official hosted registry with an install experience close to Python's `pip`, while keeping Mellow package archives simple and deterministic.

## Client UX
### Install
```bash
mellow install physics2d
mellow install @mellow/gamekit
mellow install dialoguekit@1.2.0
```

### Publish
```bash
mellow login --token <publish-token>
mellow publish ./dialoguekit
```

### Search
```bash
mellow search dialogue
```

## Manifest
Packages may include either `mellow.toml` or `mellow.pkg.json`.
Required fields:
- `name`
- `version`
- `entry`

Recommended fields:
- `description`
- `authors`
- `license`
- `keywords`
- `dependencies`

## Archive format
- Extension: `.mpkg`
- Container: ZIP archive
- Contents:
  - `mellow.toml` or `mellow.pkg.json`
  - `src/**`
  - optional `README.md`
  - optional `tests/**`

## HTTP API
### `GET /health`
Health probe.

### `GET /api/v1/packages/search?q=<query>`
Returns package summaries.

### `GET /api/v1/packages/<name>`
Returns package metadata and available versions.

### `GET /api/v1/packages/<name>/versions/<version>`
Returns version metadata.

### `GET /api/v1/packages/<name>/download/<version>`
Returns the `.mpkg` archive bytes.

### `GET /api/v1/auth/whoami`
Requires `Authorization: Bearer <token>`.
Returns publish-token owner info.

### `POST /api/v1/packages/publish`
Requires `Authorization: Bearer <token>`.
Payload:
```json
{
  "manifest": {"name": "dialoguekit", "version": "1.0.0", "entry": "src/main.mellow"},
  "filename": "dialoguekit-1.0.0.mpkg",
  "archive_b64": "...",
  "sha256": "..."
}
```

## Auth model
- Install and search are public.
- Publish requires a token with the `publish` scope.
- Tokens should be stored hashed in the registry database.
- Local CLI stores per-registry tokens in `~/.mellow/config.json` unless `MELLOW_PUBLISH_TOKEN` is set.

## Recommended production architecture
- **Workers** for API endpoints
- **R2** for package archives
- **D1** for metadata and token records
- Optional: Cloudflare Cache or KV for search response caching

## Ownership rules
- First publisher becomes owner of an unclaimed package name.
- Later publishes to the same package require the same owner or delegated scopes.
- Namespace support such as `@owner/pkg` is recommended next.

## Next production upgrades
- Semver dependency resolver
- `mellow.lock`
- transitive dependency install
- package signing
- malware scanning
- web UI for docs and package browsing
