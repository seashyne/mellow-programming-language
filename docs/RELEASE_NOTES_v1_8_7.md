# Mellow 1.8.7

- event triggers
- webhook jobs
- queue-backed runners

## New CLI

```bash
mellow agent trigger add --name doc-sync --event docs.updated --task "summarize docs"
mellow agent trigger emit docs.updated --payload "{\"repo\":\"mellow\"}"
mellow agent webhook add --name inbound --event webhook.received --task "handle webhook"
mellow agent webhook receive inbound --token <token> --payload "{\"kind\":\"push\"}"
mellow agent queue list
mellow agent queue run --limit 10
mellow agent runner start --queue-backed --interval-s 1 --iterations 5
```
