# MellowLang 1.8.9

## Added
- Queue backoff policies: fixed, exponential, jitter
- Worker concurrency for queue drains and background runners
- Persistent HTTP Job API at `/jobs` and `/jobs/<id>`
- Queue stats command and job API status

## Commands
```bash
mellow agent jobs submit --task "summarize docs" --backoff exponential --backoff-delay-ms 1000 --backoff-max-ms 30000
mellow agent jobs list
mellow agent jobs get <job_id>
mellow agent jobs serve --host 127.0.0.1 --port 8788
mellow agent queue run --workers 4
mellow agent queue stats
mellow agent runner start --queue-backed --workers 4
```
