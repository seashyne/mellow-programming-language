
# Deployment Targets

Mellow 1.8.2 can emit target-specific deployment adapter scaffolds.

## Docker
Produces `Dockerfile` and `docker-compose.yml`.

## Cloudflare Workers
Produces `wrangler.toml` and `worker.js` scaffold handlers for `/health` and `/run`.

## Vercel
Produces `vercel.json` and `api/health.js` plus `api/run.js`.

## Control plane
Use `mellow agent control-plane` to inspect locally-registered hosted deployments.
