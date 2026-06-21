# Mellow 1.7.4 — Agent lockfile + reproducible installs + private registry auth

## Highlights
- `agent.lock` for agent packages with exact versions and archive checksums
- deterministic `.magent` builds for reproducible archives
- install from lockfile with `--frozen` validation
- private agent registry auth stored separately from normal package auth
- CLI additions:
  - `mellow agent package lock <dir>`
  - `mellow agent package build <dir> --lock`
  - `mellow agent package install --lockfile <path> --frozen`
  - `mellow agent registry login --token <token> --private`
  - `mellow agent registry whoami`

## Why this matters
This version makes agent packages much closer to production workflows:
- teams can pin exact agent dependency trees
- CI can verify the package graph is unchanged
- archives are byte-for-byte reproducible when sources are unchanged
- private registries can use dedicated auth tokens without mixing with public package auth

## Notes
- lock generation currently resolves from the local agent registry first
- remote installs honor checksum verification when registry metadata provides SHA256
- reproducible archives use a fixed zip timestamp and deterministic file ordering
