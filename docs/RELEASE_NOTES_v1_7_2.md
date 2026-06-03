# Mellow 1.7.2 — Agent Registry + Publish/Install

Mellow 1.7.2 upgrades the AI-native agent system with a real agent package lifecycle.

## Added

- `mellow agent package build <dir>` builds `.magent` archives
- `mellow agent package publish <dir>` publishes agent packages to the local registry
- `mellow agent package install <name>` installs agent packages from the local registry
- `mellow agent package search <query>` searches agent packages
- Optional remote workflow:
  - `mellow agent package publish --online`
  - `mellow agent package install --online`
  - `mellow agent package search --online`
- Installed agent packages can be executed by package name with:
  - `mellow agent package run my.agent --task "..."`

## Storage layout

- Local registry: `mellow_agent_packages/registry/<name>/<version>/`
- Installed agent packages: `mellow_agent_packages/installed/<name>/<version>/package/`
- Cache: `~/.mellow/cache/agent_packages/`

## Agent package archive

- Archive extension: `.magent`
- Archive contains `agent.toml`, prompts, tool manifests, and package files
- SHA-256 hash is returned on build and publish

## Notes

- Remote agent registry endpoints follow `/api/v1/agents/*`
- Registry auth reuses normal `mellow login` credentials
- Agent packages remain backward compatible with 1.7.1 package format
