"""Which registry a command talks to, and the token it talks with."""

from __future__ import annotations

from typing import Any, Dict

from ... import package_manager as pm


def get_agent_registry_url(explicit: str | None = None) -> str:
    cfg = pm.load_config()
    return (explicit or cfg.get('agent_registry') or pm.get_registry_url()).rstrip('/')


def get_agent_auth_token(registry: str | None = None, *, private: bool = False) -> str | None:
    reg = get_agent_registry_url(registry)
    env_names = ['MELLOW_AGENT_PRIVATE_TOKEN', 'MELLOW_AGENT_TOKEN', 'MELLOW_PUBLISH_TOKEN', 'MELLOW_REGISTRY_TOKEN'] if private else ['MELLOW_AGENT_TOKEN', 'MELLOW_AGENT_READ_TOKEN', 'MELLOW_PUBLISH_TOKEN', 'MELLOW_REGISTRY_TOKEN']
    for name in env_names:
        value = pm.os.environ.get(name)
        if value:
            return value
    cfg = pm.load_config()
    key = 'agent_private_auth' if private else 'agent_auth'
    return ((cfg.get(key) or {}).get(reg)) or ((cfg.get('auth') or {}).get(reg))


def set_agent_auth_token(registry: str, token: str, *, private: bool = False) -> Dict[str, Any]:
    cfg = pm.load_config()
    key = 'agent_private_auth' if private else 'agent_auth'
    cfg.setdefault(key, {})[registry.rstrip('/')] = token
    if 'agent_registry' not in cfg:
        cfg['agent_registry'] = registry.rstrip('/')
    pm.save_config(cfg)
    return {'ok': True, 'registry': registry.rstrip('/'), 'private': private, 'saved_to': str(pm.CONFIG_FILE)}


def clear_agent_auth_token(registry: str | None = None, *, private: bool = False) -> Dict[str, Any]:
    reg = get_agent_registry_url(registry)
    cfg = pm.load_config()
    key = 'agent_private_auth' if private else 'agent_auth'
    cfg.setdefault(key, {}).pop(reg, None)
    pm.save_config(cfg)
    return {'ok': True, 'registry': reg, 'private': private, 'saved_to': str(pm.CONFIG_FILE)}


def agent_registry_whoami(registry: str | None = None) -> Dict[str, Any]:
    reg = get_agent_registry_url(registry)
    read_token = get_agent_auth_token(reg, private=False)
    private_token = get_agent_auth_token(reg, private=True)
    return {
        'ok': True,
        'registry': reg,
        'read_auth': bool(read_token),
        'private_auth': bool(private_token),
        'config': str(pm.CONFIG_FILE),
    }
