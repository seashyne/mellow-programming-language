# Mellow 1.8.3 — Real remote control plane API + deployment sync + rollout/revision management

Highlights:
- remote control plane HTTP API integration
- deployment sync flow
- revision tracking per hosted deployment
- rollout promotion between revisions
- deploy command can sync directly to a control plane

New commands:
- `mellow agent control-plane sync <manifest> --bundle-dir <dir> --control-plane <url>`
- `mellow agent control-plane revisions <ref> [--control-plane <url>]`
- `mellow agent control-plane rollout <ref> --revision N [--control-plane <url>]`

Remote endpoints used:
- `POST /deployments/sync`
- `GET /deployments`
- `GET /deployments/status?ref=...`
- `GET /deployments/revisions?ref=...`
- `POST /deployments/rollout`
