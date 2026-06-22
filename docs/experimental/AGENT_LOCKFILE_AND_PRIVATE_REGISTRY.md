# Agent lockfile and private registry auth

## Lockfile
Generate a lockfile for an agent package:

```bash
mellow agent package lock my-agent
```

This writes `my-agent/agent.lock` with:
- root package name/version
- exact resolved dependency versions
- archive SHA256 for reproducible installs

Install from the lockfile:

```bash
mellow agent package install --lockfile my-agent/agent.lock --frozen
```

## Reproducible archives
`mellow agent package build` now creates deterministic `.magent` archives.
If the source tree is unchanged, repeated builds produce the same SHA256.

## Private registry auth
Save a token for a private agent registry:

```bash
mellow agent registry login --registry https://agents.example.com --token SECRET --private
```

Check current auth state:

```bash
mellow agent registry whoami --registry https://agents.example.com
```

Clear the token:

```bash
mellow agent registry logout --registry https://agents.example.com --private
```
