# Mellow Plugin SDK

This SDK is a minimal contract for integrating host modules, tooling, and registry automation.

For OpenAI-compatible chat providers, see `docs/MELLOW_SDK.md` and
`starter_packages/mellow-sdk/`.

For hosted ecosystem scaffolds, see `docs/experimental/SDK_AND_HOSTED_ECOSYSTEM.md`.

## Python contract

Implement a class with:
- `name`
- `version`
- `register(host_registry)`

See `plugin_sdk/examples/echo_plugin.py`.
