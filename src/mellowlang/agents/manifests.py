from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple


@dataclass
class ToolManifestEntry:
    name: str
    description: str = ''
    builtin: str | None = None
    policy: str = 'allow'
    defaults: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentPackage:
    root: Path
    name: str
    version: str
    model: str = 'rule-based'
    prompt_file: str = 'prompts/default.prompt'
    tool_manifest: str | None = None
    memory_path: str = '.mellow/agent_memory.jsonl'
    obs_path: str = '.mellow/agent_observability.jsonl'
    tags: List[str] = field(default_factory=list)
    dependencies: Dict[str, str] = field(default_factory=dict)
    capabilities_allow: List[str] = field(default_factory=list)
    capabilities_deny: List[str] = field(default_factory=list)
    secret_scopes: Dict[str, List[str]] = field(default_factory=dict)
    required_secrets: List[str] = field(default_factory=list)
    deployment: Dict[str, Any] = field(default_factory=dict)
    policy_file: str | None = None

    def prompt_path(self) -> Path:
        return (self.root / self.prompt_file).resolve()

    def tool_manifest_path(self) -> Path | None:
        if not self.tool_manifest:
            return None
        return (self.root / self.tool_manifest).resolve()


def _normalize_secret_scopes(raw: Dict[str, Any] | None) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for key, value in (raw or {}).items():
        if isinstance(value, list):
            out[str(key)] = [str(x) for x in value]
        elif isinstance(value, str):
            out[str(key)] = [s.strip() for s in value.split(',') if s.strip()]
    return out


def load_agent_package(path: str | Path) -> AgentPackage:
    root = Path(path)
    manifest_path = root / 'agent.toml'
    data = tomllib.loads(manifest_path.read_text(encoding='utf-8'))
    pkg = data.get('package', {})
    agent = data.get('agent', {})
    caps = data.get('capabilities', {}) or {}
    secrets = data.get('secrets', {}) or {}
    deploy = data.get('deployment', {}) or {}
    return AgentPackage(
        root=root.resolve(),
        name=str(pkg.get('name', root.name)),
        version=str(pkg.get('version', '0.1.0')),
        model=str(agent.get('model', 'rule-based')),
        prompt_file=str(agent.get('prompt_file', 'prompts/default.prompt')),
        tool_manifest=agent.get('tool_manifest'),
        memory_path=str(agent.get('memory_path', '.mellow/agent_memory.jsonl')),
        obs_path=str(agent.get('obs_path', '.mellow/agent_observability.jsonl')),
        tags=[str(x) for x in agent.get('tags', [])],
        dependencies={str(k): str(v) for k, v in (data.get('dependencies', {}) or {}).items()},
        capabilities_allow=[str(x) for x in (caps.get('allow') or [])],
        capabilities_deny=[str(x) for x in (caps.get('deny') or [])],
        secret_scopes=_normalize_secret_scopes(secrets.get('scopes')),
        required_secrets=[str(x) for x in (secrets.get('required') or [])],
        deployment=dict(deploy),
        policy_file=str(agent.get('policy_file')) if agent.get('policy_file') else None,
    )


def load_tool_manifest(path: str | Path) -> List[ToolManifestEntry]:
    p = Path(path)
    if p.suffix.lower() == '.json':
        data = json.loads(p.read_text(encoding='utf-8'))
    else:
        data = tomllib.loads(p.read_text(encoding='utf-8'))
    tools = data.get('tools', []) if isinstance(data, dict) else data
    out: List[ToolManifestEntry] = []
    for item in tools:
        if not isinstance(item, dict) or not item.get('name'):
            continue
        out.append(ToolManifestEntry(
            name=str(item['name']),
            description=str(item.get('description', '')),
            builtin=item.get('builtin'),
            policy=str(item.get('policy', 'allow')),
            defaults=dict(item.get('defaults', {})),
        ))
    return out


def parse_version_tuple(version: str) -> Tuple[int, int, int]:
    nums = [int(x) for x in re.findall(r"\d+", str(version))[:3]]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def compare_versions(a: str, b: str) -> int:
    av = parse_version_tuple(a)
    bv = parse_version_tuple(b)
    return (av > bv) - (av < bv)


def version_satisfies(version: str, constraint: str | None) -> bool:
    if not constraint or str(constraint).strip() in {'', '*'}:
        return True
    ver = parse_version_tuple(version)
    parts = [p.strip() for p in str(constraint).split(',') if p.strip()]
    for part in parts:
        if part.startswith('^'):
            base = parse_version_tuple(part[1:])
            upper = (base[0] + 1, 0, 0)
            if not (ver >= base and ver < upper):
                return False
        elif part.startswith('~'):
            base = parse_version_tuple(part[1:])
            upper = (base[0], base[1] + 1, 0)
            if not (ver >= base and ver < upper):
                return False
        elif part.startswith('>='):
            if ver < parse_version_tuple(part[2:]):
                return False
        elif part.startswith('<='):
            if ver > parse_version_tuple(part[2:]):
                return False
        elif part.startswith('>'):
            if ver <= parse_version_tuple(part[1:]):
                return False
        elif part.startswith('<'):
            if ver >= parse_version_tuple(part[1:]):
                return False
        elif part.startswith('=='):
            if ver != parse_version_tuple(part[2:]):
                return False
        else:
            if ver != parse_version_tuple(part):
                return False
    return True
