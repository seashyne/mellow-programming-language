# Plugin SDK and Hosted Ecosystem

## Plugin SDK

The `plugin_sdk/` folder contains a Python host-plugin contract and examples. Plugins can expose commands, host modules, or registry automation.

## Hosted ecosystem

The `websites/` folder contains starter static sites for:
- docs site
- package website

The Cloudflare registry remains the API backend. The website starter pages can be deployed to Pages and pointed at the registry API.

## Recommended next step

- add namespace ownership enforcement in the registry
- add package provenance UI
- add agent tool execution sandboxing
