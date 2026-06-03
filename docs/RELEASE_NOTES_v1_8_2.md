
# Mellow 1.8.2

## Highlights
- Deployment targets: local-http, Docker, Cloudflare Workers, and Vercel.
- Adapter scaffolds emitted during `mellow agent deploy`.
- Remote hosted control plane state management.
- `mellow agent` now prints nested help when called without a subcommand.

## New commands
- `mellow agent deploy my.agent --target docker`
- `mellow agent deploy my.agent --target cloudflare-workers`
- `mellow agent deploy my.agent --target vercel`
- `mellow agent control-plane list`
- `mellow agent control-plane status <ref>`
- `mellow agent control-plane register deployment.json --bundle-dir .mellow/deploy/my_agent`
