# Mellow 1.8.4

- Added deployment health checks via `mellow agent control-plane health <ref>`.
- Added canary rollout support with `--canary-percent`.
- Added traffic split updates via `mellow agent control-plane traffic`.
- Added rollback command via `mellow agent control-plane rollback`.
- Extended local and remote control plane flows with rollout metadata.
