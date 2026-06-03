# Mellow Plugin SDK

This SDK is a minimal contract for integrating host modules, tooling, and registry automation.

## Python contract

Implement a class with:
- `name`
- `version`
- `register(host_registry)`

See `plugin_sdk/examples/echo_plugin.py`.
