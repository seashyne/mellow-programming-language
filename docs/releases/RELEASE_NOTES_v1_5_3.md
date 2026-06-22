# MellowLang v1.5.3 — Public Registry Pack

## Highlights
- Public registry URL: `https://mellow-public-registry.jirayut-wh.workers.dev`
- Pip-style install command: `mellow install <package>`
- Token-based publish flow: `mellow login --token <token>` then `mellow publish <dir>`
- Cloudflare deployment starter for Workers + R2 + D1
- Expanded registry API spec and production-oriented folder layout

## New commands
- `mellow install physics2d`
- `mellow search physics`
- `mellow publish ./physics2d --token <token>`
- `mellow login --token <token>`
- `mellow whoami`

## Notes
This pack ships the public-registry implementation and deployment scaffold, but does not host the registry for you. You still need to deploy the Worker and create the Cloudflare resources.
