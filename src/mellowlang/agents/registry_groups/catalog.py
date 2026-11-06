"""What the local registry already holds: a package's manifest, its versions,
and a search over it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..manifests import load_agent_package

from .layout import AGENT_REGISTRY_ROOT, ensure_agent_dirs, normalize_agent_name


def agent_manifest_dict(package_dir: str | Path) -> Dict[str, Any]:
    pkg = load_agent_package(package_dir)
    return {
        'name': pkg.name,
        'version': pkg.version,
        'model': pkg.model,
        'prompt_file': pkg.prompt_file,
        'tool_manifest': pkg.tool_manifest,
        'memory_path': pkg.memory_path,
        'obs_path': pkg.obs_path,
        'tags': list(pkg.tags),
        'dependencies': dict(pkg.dependencies),
    }


def list_local_agent_versions(name: str) -> List[str]:
    pkg_dir = AGENT_REGISTRY_ROOT / normalize_agent_name(name)
    if not pkg_dir.exists():
        return []
    return sorted([p.name for p in pkg_dir.iterdir() if p.is_dir()])


def search_agent_local(query: str) -> Dict[str, Any]:
    ensure_agent_dirs()
    q = (query or '').strip().lower()
    items: List[Dict[str, Any]] = []
    for manifest_path in sorted(AGENT_REGISTRY_ROOT.glob('*/ */agent-manifest.json'.replace(' ', ''))):
        try:
            data = json.loads(manifest_path.read_text(encoding='utf-8'))
        except Exception:
            continue
        hay = ' '.join([
            str(data.get('name', '')),
            str(data.get('model', '')),
            ' '.join(data.get('tags', []) or []),
        ]).lower()
        if not q or q in hay:
            data['registry'] = 'local'
            items.append(data)
    return {'ok': True, 'query': query, 'items': items[:20]}
