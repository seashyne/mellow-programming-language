"""Where agent packages live on disk, and the name form every path uses."""

from __future__ import annotations

from pathlib import Path

from ... import package_manager as pm


AGENT_ROOT = Path('mellow_agent_packages')
AGENT_REGISTRY_ROOT = AGENT_ROOT / 'registry'
AGENT_INSTALLED_ROOT = AGENT_ROOT / 'installed'
AGENT_CACHE_ROOT = pm.CONFIG_HOME / 'cache' / 'agent_packages'
ARCHIVE_EXT = '.magent'
LOCKFILE_NAME = 'agent.lock'
REPRO_ZIP_TIMESTAMP = (2024, 1, 1, 0, 0, 0)


def _agent_cache_root() -> Path:
    return Path(pm.CONFIG_HOME) / 'cache' / 'agent_packages'


def ensure_agent_dirs() -> None:
    AGENT_REGISTRY_ROOT.mkdir(parents=True, exist_ok=True)
    AGENT_INSTALLED_ROOT.mkdir(parents=True, exist_ok=True)
    _agent_cache_root().mkdir(parents=True, exist_ok=True)
    pm.CONFIG_HOME.mkdir(parents=True, exist_ok=True)


def normalize_agent_name(name: str) -> str:
    return pm.normalize_name(name)
