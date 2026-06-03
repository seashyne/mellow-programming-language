# Mellow 1.8.1 Hosted Runtime + Signed Policies

## Highlights
- Hosted runtime flow for agent packages via deployment manifests
- Real deployment bundle output with `deployment.json` and `run-hosted.cmd`
- Secret scopes for selective injection (`agent.run`, `tool.search.docs`, etc.)
- Signed capability policies with CLI sign/verify support

## New commands
- `mellow agent deploy my.agent --public-url https://example.com`
- `mellow agent serve --package my.agent --deployment-manifest .mellow/deploy/my_agent/deployment.json`
- `mellow agent secret set OPENAI_API_KEY sk-demo --scope agent.run --scope tool.search.docs`
- `mellow agent policy sign policies/capabilities.json --key secret --signer seash`
- `mellow agent policy verify policies/capabilities.json --key secret`

## Notes
- Hosted runtime is local/self-host oriented but uses a deployment manifest that can be adapted to a real hosting layer.
- Secret scope enforcement is backward compatible with legacy unscoped secrets (`*`).
