# Mellow 1.6.0 Overview

Mellow 1.6.0 turns the 1.5.x registry foundation into a usable platform layer.

## Highlights

- `mellow add <package>` and `mellow remove <package>`
- `mellow run` auto-resolves project imports and runtime metadata before execution
- stronger dependency resolver with `^`, `~`, `>=`, `<=`, `>`, `<`, exact, and comma-separated constraints
- lockfile-first install flow with package cache
- package signing with Ed25519 keys generated under `~/.mellow/keys/`
- namespace-ready package names like `@mellow/core-ai`
- stdlib starter packages, docs site, package website, plugin SDK, AI agents, and game framework scaffolds

## Scope

This release is production-oriented foundation work, not the final hosted ecosystem. The hosted registry and web surfaces are starter implementations meant to be extended.
