"""Agent packages and the registry: init, lock, build, publish, install, graph, search, login, logout, whoami, and the secret store."""

from __future__ import annotations

import sys

from ...common import _cli_line, _json_print
from .deps import (
    pkg_get_registry_url, init_agent_package, build_agent_archive, publish_agent_from_dir,
    install_agent_package, search_agent_local, publish_agent_remote, install_agent_remote,
    search_agent_remote, agent_dependency_graph, generate_agent_lock, write_agent_lock,
    install_agent_with_lock, set_agent_auth_token, clear_agent_auth_token, agent_registry_whoami,
    set_secret, remove_secret, list_secrets,
)
from .support import _print_graph

def _cmd_agent_package_init(dir_path: str, name: str, force: bool, json_out: bool) -> int:
    try:
        root = init_agent_package(dir_path, name=name, force=force)
    except Exception as e:
        if json_out:
            _json_print({'ok': False, 'error': str(e)})
        else:
            _cli_line(f'agent package init failed: {e}', kind='error', file=sys.stderr)
        return 1
    payload = {'ok': True, 'dir': str(root), 'name': name}
    if json_out:
        _json_print(payload)
    else:
        _cli_line('Agent package created', kind='ok')
        print(f'Directory       : {root}')
        print(f'Name            : {name}')
    return 0

def _cmd_agent_package_lock(dir_path: str, json_out: bool = False) -> int:
    try:
        res = generate_agent_lock(dir_path)
        lock_path = write_agent_lock(dir_path, res['lock'])
        payload = {'ok': True, 'lockfile': str(lock_path), 'packages': len(res['lock'].get('packages') or [])}
    except Exception as e:
        payload = {'ok': False, 'error': str(e)}
    if json_out:
        _json_print(payload)
    else:
        if payload.get('ok'):
            _cli_line('Agent lockfile written', kind='ok')
            print(f"Lockfile        : {payload['lockfile']}")
            print(f"Packages pinned : {payload['packages']}")
        else:
            _cli_line(f"agent package lock failed: {payload.get('error')}", kind='error', file=sys.stderr)
    return 0 if payload.get('ok') else 1

def _cmd_agent_registry_login(registry: str | None, token: str, private: bool, json_out: bool = False) -> int:
    res = set_agent_auth_token((registry or pkg_get_registry_url()), token, private=private)
    if json_out:
        _json_print(res)
    else:
        _cli_line('Agent registry token saved', kind='ok')
        print(f"Registry        : {res['registry']}")
        print(f"Mode            : {'private' if private else 'read/publish'}")
    return 0

def _cmd_agent_registry_logout(registry: str | None, private: bool, json_out: bool = False) -> int:
    res = clear_agent_auth_token(registry, private=private)
    if json_out:
        _json_print(res)
    else:
        _cli_line('Agent registry token cleared', kind='ok')
        print(f"Registry        : {res['registry']}")
        print(f"Mode            : {'private' if private else 'read/publish'}")
    return 0

def _cmd_agent_registry_whoami(registry: str | None, json_out: bool = False) -> int:
    res = agent_registry_whoami(registry)
    if json_out:
        _json_print(res)
    else:
        _cli_line('Agent registry auth', kind='ok')
        print(f"Registry        : {res['registry']}")
        print(f"Read auth       : {res['read_auth']}")
        print(f"Private auth    : {res['private_auth']}")
        print(f"Config          : {res['config']}")
    return 0

def _cmd_agent_package_build(dir_path: str, out_path: str | None, signing_key: str | None = None, signer: str | None = None, write_lock: bool = False, json_out: bool = False) -> int:
    if isinstance(signing_key, bool) and signer is None and json_out is False:
        json_out = signing_key
        signing_key = None
    try:
        res = build_agent_archive(dir_path, out_path, signing_key=signing_key, signer=signer)
        lock_path = None
        if write_lock:
            lock_res = generate_agent_lock(dir_path)
            lock_path = write_agent_lock(dir_path, lock_res['lock'])
    except Exception as e:
        if json_out:
            _json_print({'ok': False, 'error': str(e)})
        else:
            _cli_line(f'agent package build failed: {e}', kind='error', file=sys.stderr)
        return 1
    if json_out:
        _json_print(res)
    else:
        _cli_line('Agent package archive built', kind='ok')
        print(f"Package         : {res['name']}@{res['version']}")
        print(f"Archive         : {res['archive']}")
        print(f"SHA256          : {res['sha256']}")
        print(f"Reproducible    : {res.get('reproducible', False)}")
        if write_lock and lock_path:
            print(f"Lockfile        : {lock_path}")
    return 0

def _cmd_agent_package_publish(dir_path: str, online: bool, registry: str | None, token: str | None, signing_key: str | None = None, signer: str | None = None, private: bool = False, write_lock: bool = False, json_out: bool = False) -> int:
    if isinstance(signing_key, bool) and signer is None and json_out is False:
        json_out = signing_key
        signing_key = None
    try:
        if write_lock:
            lock_res = generate_agent_lock(dir_path)
            write_agent_lock(dir_path, lock_res['lock'])
        res = publish_agent_remote(dir_path, registry=registry, token=token, signing_key=signing_key, signer=signer, private=private) if online else publish_agent_from_dir(dir_path, signing_key=signing_key, signer=signer)
    except Exception as e:
        res = {'ok': False, 'error': str(e)}
    if json_out:
        _json_print(res)
    else:
        if res.get('ok', True) and not res.get('error'):
            _cli_line('Agent package published', kind='ok')
            print(f"Package         : {res.get('name')}@{res.get('version')}")
            print(f"Published to    : {res.get('published_to') or (registry or pkg_get_registry_url())}")
        else:
            _cli_line(f"agent package publish failed: {res.get('error')}", kind='error', file=sys.stderr)
            if res.get('hint'):
                _cli_line(str(res['hint']), kind='hint', file=sys.stderr)
    return 0 if res.get('ok', True) and not res.get('error') else 1

def _cmd_agent_package_install(name: str | None, version: str | None, online: bool, registry: str | None, target_dir: str | None, verify_key: str | None = None, lockfile: str | None = None, frozen: bool = False, private: bool = False, json_out: bool = False) -> int:
    if isinstance(verify_key, bool) and json_out is False:
        json_out = verify_key
        verify_key = None
    try:
        if lockfile:
            res = install_agent_with_lock(lockfile, target_dir=target_dir, verify_key=verify_key, frozen=frozen)
        else:
            if not name:
                raise ValueError('name is required unless --lockfile is provided')
            res = install_agent_remote(name, version=version, registry=registry, target_dir=target_dir, verify_key=verify_key, private=private) if online else install_agent_package(name, version=version, target_dir=target_dir, verify_key=verify_key)
    except Exception as e:
        res = {'ok': False, 'error': str(e)}
    if json_out:
        _json_print(res)
    else:
        if res.get('ok'):
            _cli_line('Agent package installed', kind='ok')
            print(f"Package         : {res.get('name')}@{res.get('version')}")
            print(f"Installed to    : {res.get('installed_to')}")
        else:
            _cli_line(f"agent package install failed: {res.get('error')}", kind='error', file=sys.stderr)
            if res.get('hint'):
                _cli_line(str(res['hint']), kind='hint', file=sys.stderr)
    return 0 if res.get('ok') else 1

def _cmd_agent_package_graph(ref: str, json_out: bool) -> int:
    try:
        res = agent_dependency_graph(ref)
    except Exception as e:
        res = {'ok': False, 'error': str(e)}
    if json_out:
        _json_print(res)
    else:
        if not res.get('ok'):
            _cli_line(f"agent package graph failed: {res.get('error')}", kind='error', file=sys.stderr)
            return 1
        _cli_line('Agent dependency graph', kind='ok')
        _print_graph(res['graph'])
    return 0 if res.get('ok') else 1

def _cmd_agent_package_search(query: str, online: bool, registry: str | None, private: bool = False, json_out: bool = False) -> int:
    if isinstance(private, bool) and private is True and json_out is False:
        # backward compatibility with older helper signature (..., json_out=True)
        json_out = True
        private = False
    try:
        res = search_agent_remote(query, registry=registry, private=private) if online else search_agent_local(query)
    except Exception as e:
        res = {'ok': False, 'error': str(e)}
    if json_out:
        _json_print(res)
    else:
        items = list(res.get('items') or [])
        if not res.get('ok', True):
            _cli_line(f"agent package search failed: {res.get('error')}", kind='error', file=sys.stderr)
            return 1
        _cli_line(f"Found {len(items)} agent package(s)", kind='ok')
        for item in items:
            print(f"- {item.get('name')}@{item.get('version', '?')} [{', '.join(item.get('tags') or [])}] model={item.get('model', 'rule-based')}")
    return 0

def _cmd_agent_secret(action: str, name: str | None, value: str | None, json_out: bool, scopes: list[str] | None = None, description: str | None = None) -> int:
    if action == 'set' and name is not None and value is not None:
        set_secret(name, value, scopes=scopes or ['*'], description=description)
        payload = {'ok': True, 'name': name, 'scopes': scopes or ['*']}
    elif action == 'remove' and name is not None:
        payload = {'ok': remove_secret(name), 'name': name}
    else:
        payload = {'ok': True, 'items': list_secrets()}
    if json_out:
        _json_print(payload)
    else:
        if 'items' in payload:
            _cli_line(f"Stored secrets: {len(payload['items'])}", kind='ok')
            for item in payload['items']:
                print(f"- {item['name']} = {item['masked']} scopes={','.join(item.get('scopes') or ['*'])}")
        elif payload.get('ok'):
            _cli_line(f"Secret {action} ok: {name}", kind='ok')
        else:
            _cli_line(f"Secret {action} failed: {name}", kind='error', file=sys.stderr)
    return 0 if payload.get('ok') else 1
