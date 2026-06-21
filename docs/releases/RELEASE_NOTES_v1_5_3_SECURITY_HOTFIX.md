# MellowLang v1.5.3 Security Hotfix

This hotfix makes the public registry pack safer and fixes token login.

## Fixed
- `mellow login --token ...` now succeeds when the registry returns `ok: true`.
- Login tokens are saved **only after** the token is validated by `/api/v1/auth/whoami`.
- Remote installs now verify package SHA-256 before extraction.
- Package extraction now blocks unsafe archive entries such as absolute paths and `..` traversal.
- Registry publish validates package name, version, base64 input, archive size, and checksum.
- Registry now rejects overwriting an existing package version.
- Safer HTTP headers were added to registry responses.

## Operational cleanup
- Cloudflare deploy config was reset to placeholders so the pack no longer ships real IDs, URLs, or secrets.
- Example seed SQL was sanitized.
- Local `.wrangler` runtime state should not be distributed.
