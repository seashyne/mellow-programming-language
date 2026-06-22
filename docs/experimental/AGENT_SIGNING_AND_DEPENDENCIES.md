# Agent signing and dependency graph

## Signing

Build or publish with a signing key:

```bash
mellow agent package build my-agent --signing-key secret --signer seash
mellow agent package publish my-agent --signing-key secret --signer seash
```

Install with verification:

```bash
mellow agent package install my.agent --verify-key secret
```

## Version constraints

In `agent.toml`:

```toml
[dependencies]
"helper.agent" = "^1.0.0"
"retrieval.agent" = ">=1.2.0,<2.0.0"
```

## Dependency graph

```bash
mellow agent package graph my.agent
```
