from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .manifests import load_agent_package

DEFAULT_RUNTIME = {
    'provider': 'local-http',
    'entrypoint': 'POST /run',
    'healthcheck': 'GET /health',
    'host': '127.0.0.1',
    'port': 8787,
}

SUPPORTED_TARGETS = ('local-http', 'docker', 'cloudflare-workers', 'vercel')


def _normalize_target(target: str | None) -> str:
    raw = str(target or 'local-http').strip().lower()
    aliases = {
        'local': 'local-http',
        'http': 'local-http',
        'cloudflare': 'cloudflare-workers',
        'workers': 'cloudflare-workers',
        'cf-workers': 'cloudflare-workers',
    }
    return aliases.get(raw, raw)


def build_deployment_manifest(ref: str | Path, *, public_url: str | None = None, host: str | None = None, port: int | None = None, target: str | None = None, control_plane: str | None = None) -> Dict[str, Any]:
    pkg = load_agent_package(ref)
    deploy = dict(DEFAULT_RUNTIME)
    deploy.update(pkg.deployment or {})
    normalized_target = _normalize_target(target or deploy.get('provider'))
    if normalized_target not in SUPPORTED_TARGETS:
        raise ValueError(f'unsupported deployment target: {normalized_target}')
    if public_url:
        deploy['public_url'] = public_url
    if host:
        deploy['host'] = host
    if port:
        deploy['port'] = int(port)
    if control_plane:
        deploy['control_plane'] = control_plane
    runtime = {
        'provider': normalized_target,
        'model': pkg.model,
        'entrypoint': 'POST ' + str(deploy.get('base_path', '/run')),
        'healthcheck': 'GET ' + str(deploy.get('health_path', '/health')),
        'public_url': deploy.get('public_url'),
        'host': deploy.get('host', '127.0.0.1'),
        'port': int(deploy.get('port', 8787)),
        'start_command': f"mellow agent serve --package {pkg.root} --deployment-manifest deployment.json",
    }
    if normalized_target == 'docker':
        runtime['image'] = deploy.get('image', f"mellow/{pkg.name.replace('.', '-')}:latest")
    elif normalized_target == 'cloudflare-workers':
        runtime['worker_name'] = deploy.get('worker_name', pkg.name.replace('.', '-'))
        runtime['compatibility_date'] = deploy.get('compatibility_date', '2026-03-15')
    elif normalized_target == 'vercel':
        runtime['project_name'] = deploy.get('project_name', pkg.name.replace('.', '-'))
        runtime['runtime_version'] = deploy.get('runtime_version', 'nodejs22.x')
    return {
        'manifest_version': 2,
        'package': {'name': pkg.name, 'version': pkg.version},
        'runtime': runtime,
        'security': {
            'capabilities': {
                'allow': list(pkg.capabilities_allow),
                'deny': list(pkg.capabilities_deny),
            },
            'required_secrets': list(pkg.required_secrets),
            'secret_scopes': dict(pkg.secret_scopes),
            'policy_file': pkg.policy_file,
        },
        'observability': {
            'memory_path': pkg.memory_path,
            'obs_path': pkg.obs_path,
        },
        'files': {
            'prompt_file': pkg.prompt_file,
            'tool_manifest': pkg.tool_manifest,
        },
        'control_plane': {
            'url': deploy.get('control_plane'),
            'deployment_id': f"{pkg.name}@{pkg.version}",
            'sync_endpoint': '/deployments/sync',
            'status_endpoint': '/deployments/status',
        },
    }


def _write_target_adapter(target: str, manifest: Dict[str, Any], out_dir: Path) -> Dict[str, str]:
    pkg = manifest['package']
    files: Dict[str, str] = {}
    if target == 'docker':
        dockerfile = out_dir / 'Dockerfile'
        dockerfile.write_text(
            "FROM python:3.12-slim\n"
            "WORKDIR /app\n"
            "COPY package /app/package\n"
            "COPY deployment.json /app/deployment.json\n"
            "RUN pip install mellowlang || true\n"
            "EXPOSE 8787\n"
            "CMD [\"mellow\", \"agent\", \"serve\", \"--package\", \"/app/package\", \"--deployment-manifest\", \"/app/deployment.json\"]\n",
            encoding='utf-8',
        )
        compose = out_dir / 'docker-compose.yml'
        compose.write_text(
            f"services:\n  {pkg['name'].replace('.', '-')}:\n    build: .\n    ports:\n      - \"{manifest['runtime']['port']}:8787\"\n",
            encoding='utf-8',
        )
        files['dockerfile'] = str(dockerfile)
        files['compose'] = str(compose)
    elif target == 'cloudflare-workers':
        wr = out_dir / 'wrangler.toml'
        wr.write_text(
            f"name = \"{manifest['runtime'].get('worker_name')}\"\nmain = \"worker.js\"\ncompatibility_date = \"{manifest['runtime'].get('compatibility_date')}\"\n",
            encoding='utf-8',
        )
        worker = out_dir / 'worker.js'
        worker.write_text(
            "export default {\n"
            "  async fetch(request) {\n"
            "    const url = new URL(request.url);\n"
            "    if (url.pathname === '/health') return new Response(JSON.stringify({ok:true,provider:'cloudflare-workers'}), {headers:{'content-type':'application/json'}});\n"
            "    if (url.pathname === '/run' && request.method === 'POST') {\n"
            "      const body = await request.json().catch(() => ({}));\n"
            "      return new Response(JSON.stringify({ok:true,task:body.task||'demo task',provider:'cloudflare-workers',note:'adapter scaffold'}), {headers:{'content-type':'application/json'}});\n"
            "    }\n"
            "    return new Response('Not found', {status:404});\n"
            "  }\n"
            "};\n",
            encoding='utf-8',
        )
        files['wrangler'] = str(wr)
        files['worker'] = str(worker)
    elif target == 'vercel':
        vjson = out_dir / 'vercel.json'
        vjson.write_text(json.dumps({
            'version': 2,
            'functions': {'api/run.js': {'runtime': manifest['runtime'].get('runtime_version', 'nodejs22.x')}},
            'routes': [
                {'src': '/health', 'dest': '/api/health.js'},
                {'src': '/run', 'methods': ['POST'], 'dest': '/api/run.js'},
            ],
        }, indent=2) + '\n', encoding='utf-8')
        api = out_dir / 'api'
        api.mkdir(exist_ok=True)
        (api / 'health.js').write_text("export default function handler(req, res) { res.status(200).json({ ok: true, provider: 'vercel' }); }\n", encoding='utf-8')
        (api / 'run.js').write_text("export default async function handler(req, res) { const body = req.body || {}; res.status(200).json({ ok: true, task: body.task || 'demo task', provider: 'vercel', note: 'adapter scaffold' }); }\n", encoding='utf-8')
        files['vercel'] = str(vjson)
        files['api'] = str(api)
    return files


def write_deployment_bundle(ref: str | Path, out_dir: str | Path, *, public_url: str | None = None, host: str | None = None, port: int | None = None, target: str | None = None, control_plane: str | None = None) -> Dict[str, Any]:
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_deployment_manifest(ref, public_url=public_url, host=host, port=port, target=target, control_plane=control_plane)
    manifest_path = target_dir / 'deployment.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pkg_dir = target_dir / 'package'
    pkg_dir.mkdir(exist_ok=True)
    start_script = target_dir / 'run-hosted.cmd'
    start_script.write_text(
        '@echo off\n'
        f'mellow agent serve --package "{Path(ref).resolve()}" --deployment-manifest "{manifest_path.resolve()}"\n',
        encoding='utf-8'
    )
    adapters = _write_target_adapter(manifest['runtime']['provider'], manifest, target_dir)
    return {'ok': True, 'manifest_path': str(manifest_path), 'manifest': manifest, 'start_script': str(start_script), 'adapters': adapters}


def load_deployment_manifest(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding='utf-8'))
