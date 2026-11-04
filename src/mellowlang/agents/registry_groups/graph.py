"""Resolve a package's dependency graph against the local registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Set

from ..manifests import version_satisfies

from .catalog import agent_manifest_dict, list_local_agent_versions
from .integrity import _read_manifest_json
from .layout import AGENT_REGISTRY_ROOT, ensure_agent_dirs, normalize_agent_name


def _collect_graph_local(name: str, version: str | None = None, _seen: Set[str] | None = None) -> Dict[str, Any]:
    ensure_agent_dirs()
    _seen = _seen or set()
    base_name = normalize_agent_name(name)
    versions = list_local_agent_versions(base_name)
    if not versions:
        return {'name': base_name, 'error': 'not found', 'dependencies': []}
    chosen = version or versions[-1]
    key = f'{base_name}@{chosen}'
    if key in _seen:
        return {'name': base_name, 'version': chosen, 'cycle': True, 'dependencies': []}
    _seen.add(key)
    mpath = AGENT_REGISTRY_ROOT / base_name / chosen / 'agent-manifest.json'
    data = _read_manifest_json(mpath)
    deps = []
    for dep_name, constraint in (data.get('dependencies') or {}).items():
        dep_versions = list_local_agent_versions(dep_name)
        match = None
        for cand in reversed(dep_versions):
            if version_satisfies(cand, constraint):
                match = cand
                break
        node = _collect_graph_local(dep_name, match, _seen) if match else {'name': dep_name, 'constraint': constraint, 'error': 'unsatisfied', 'dependencies': []}
        node['constraint'] = constraint
        deps.append(node)
    return {'name': base_name, 'version': chosen, 'dependencies': deps}


def agent_dependency_graph(name_or_dir: str) -> Dict[str, Any]:
    p = Path(name_or_dir)
    if p.exists():
        manifest = agent_manifest_dict(p)
        root = {'name': manifest['name'], 'version': manifest['version'], 'dependencies': []}
        for dep_name, constraint in (manifest.get('dependencies') or {}).items():
            root['dependencies'].append(_collect_graph_local(dep_name, None, set()) | {'constraint': constraint})
        return {'ok': True, 'graph': root}
    return {'ok': True, 'graph': _collect_graph_local(name_or_dir)}
