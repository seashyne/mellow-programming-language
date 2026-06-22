from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..common import _cli_line, _json_print, _lazy_attr, _prompt_yes_no

_PM = "mellowlang.package_manager"
pkg_init_package = _lazy_attr(_PM, "init_package")
pkg_list_installed = _lazy_attr(_PM, "list_installed")
pkg_publish_from_dir = _lazy_attr(_PM, "publish_from_dir")
pkg_install_package = _lazy_attr(_PM, "install_package")
pkg_build_package_archive = _lazy_attr(_PM, "build_package_archive")
pkg_search_remote = _lazy_attr(_PM, "search_remote")
pkg_package_info_remote = _lazy_attr(_PM, "package_info_remote")
pkg_publish_remote = _lazy_attr(_PM, "publish_remote")
pkg_install_remote = _lazy_attr(_PM, "install_remote")
pkg_login_remote = _lazy_attr(_PM, "login_remote")
pkg_login_with_token = _lazy_attr(_PM, "login_with_token")
pkg_whoami_remote = _lazy_attr(_PM, "whoami_remote")
pkg_clear_auth_token = _lazy_attr(_PM, "clear_auth_token")
pkg_set_registry = _lazy_attr(_PM, "set_registry")
pkg_get_registry_url = _lazy_attr(_PM, "get_registry_url")
pkg_seed_core_packages = _lazy_attr(_PM, "seed_core_packages")
pkg_uninstall_package = _lazy_attr(_PM, "uninstall_package")
pkg_update_packages = _lazy_attr(_PM, "update_packages")
pkg_resolve_project_runtime = _lazy_attr(_PM, "resolve_project_runtime")
pkg_add_dependency = _lazy_attr(_PM, "add_dependency")
pkg_remove_dependency = _lazy_attr(_PM, "remove_dependency")
pkg_interactive_pick_package = _lazy_attr(_PM, "interactive_pick_package")
pkg_diagnose_imports = _lazy_attr(_PM, "diagnose_imports")
pkg_package_creator = _lazy_attr(_PM, "package_creator")
pkg_author_profile_remote = _lazy_attr(_PM, "author_profile_remote")
pkg_package_signature_remote = _lazy_attr(_PM, "package_signature_remote")
pkg_package_signature_installed = _lazy_attr(_PM, "package_signature_installed")
pkg_check_trust_policy = _lazy_attr(_PM, "check_trust_policy")

def _prompt_choice(items: list[str], title: str = "Select package") -> str | None:
    if not items:
        return None
    _cli_line(title, kind="info")
    for i, item in enumerate(items, 1):
        print(f"  {i:>2}. {item}")
    if not sys.stdin.isatty():
        return items[0]
    try:
        raw = input("Choose number (Enter=1, q=cancel): ").strip()
    except EOFError:
        return items[0]
    if raw.lower() in {"q", "quit", "exit"}:
        return None
    if not raw:
        return items[0]
    try:
        idx = int(raw) - 1
    except Exception:
        return None
    return items[idx] if 0 <= idx < len(items) else None


def _package_versions_for_display(item: dict[str, Any]) -> list[str]:
    raw = item.get("versions")
    if isinstance(raw, dict):
        versions = [str(v) for v in raw.keys()]
    elif isinstance(raw, (list, tuple, set)):
        versions = [str(v) for v in raw]
    elif isinstance(raw, str) and raw.strip():
        versions = [raw.strip()]
    else:
        versions = []
    latest = str(item.get("latest") or "").strip()
    if latest and latest not in versions:
        versions.append(latest)
    return versions


def _print_package_install_result(res: dict[str, Any]) -> None:
    _cli_line(f"package installed: {res['name']}@{res['version']}", kind='ok')
    if res.get('entry'):
        print(f"entry   : {res['entry']}")
    print(f"creator : {pkg_package_creator(res)}")
    print(f"path    : {res['installed_to']}")
    if res.get('lockfile'):
        print(f"lockfile: {res['lockfile']}")
    if res.get('cache'):
        print(f"cache   : {res['cache']}")
    if res.get('alias'):
        print(f"alias   : {res['alias']}")


def _fmt_list(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(v) for v in value if str(v)) or "-"
    text = str(value or "").strip()
    return text or "-"


def _print_package_profile(res: dict[str, Any], author: str) -> int:
    if res.get('error') or not res.get('ok', True):
        _cli_line(str(res.get('error', 'profile lookup failed')), kind='error', file=sys.stderr)
        return 2
    items = res.get('items') or []
    _cli_line(f"Packages by {author}: {len(items)}", kind='info')
    for item in items:
        badges = _fmt_list(item.get('badges'))
        print(f"- {item.get('name')}  latest={item.get('latest') or '-'}  downloads={item.get('downloads', 0)}  badges={badges}")
        if item.get('description'):
            print(f"    {item.get('description')}")
        detail = []
        if item.get('license'):
            detail.append(f"license={item.get('license')}")
        if item.get('published_at'):
            detail.append(f"published_at={item.get('published_at')}")
        if item.get('keywords'):
            detail.append(f"keywords={_fmt_list(item.get('keywords'))}")
        if detail:
            print("    " + "  ".join(detail))
    return 0


def _print_package_verify(res: dict[str, Any], json_out: bool = False) -> int:
    if json_out:
        _json_print(res)
        return 0 if res.get('ok') else 1
    if res.get('error') or not res.get('ok', True):
        _cli_line(f"package verify failed: {res.get('error', 'verification failed')}", kind='error', file=sys.stderr)
        return 1
    _cli_line(f"package verified: {res.get('name')}@{res.get('version')}", kind='ok')
    print(f"creator   : {pkg_package_creator(res)}")
    print(f"sha256    : {res.get('sha256') or '-'}")
    print(f"signed    : {'yes' if res.get('signed') else 'no'}")
    print(f"verified  : {'yes' if res.get('verified') else 'no'}")
    print(f"trusted   : {'yes' if res.get('trusted') else 'no'}")
    if res.get('algorithm'):
        print(f"algorithm : {res.get('algorithm')}")
    if res.get('published_by'):
        print(f"published : {res.get('published_by')}" + (f" at {res.get('published_at')}" if res.get('published_at') else ""))
    if res.get('registry'):
        print(f"registry  : {res.get('registry')}")
    if res.get('installed_to'):
        print(f"path      : {res.get('installed_to')}")
    return 0


def _cmd_pkg(ns: argparse.Namespace) -> int:
    pkg_cmd = getattr(ns, 'pkg_cmd', None)
    if pkg_cmd == 'init':
        man = pkg_init_package(ns.dir, name=ns.name, entry=ns.entry, author=getattr(ns, 'author', None))
        print(f"[OK] package initialized: {Path(ns.dir).resolve()}")
        print(json.dumps(man, ensure_ascii=False, indent=2))
        return 0
    if pkg_cmd == 'publish':
        res = pkg_publish_remote(ns.dir, registry=ns.registry, token=getattr(ns, 'token', None)) if getattr(ns, 'online', False) else pkg_publish_from_dir(ns.dir)
        if res.get('error') or not res.get('ok', True):
            _cli_line(str(res.get('error', 'publish failed')), kind='error', file=sys.stderr)
            if res.get('detail'):
                _cli_line(str(res['detail']), kind='hint', file=sys.stderr)
            return 2
        _cli_line(f"package published: {res['name']}@{res['version']}", kind='ok')
        print(f"creator : {pkg_package_creator(res)}")
        print(res.get('published_to') or pkg_get_registry_url(ns.registry))
        return 0
    if pkg_cmd == 'install':
        res = pkg_install_remote(ns.name, version=ns.version, registry=ns.registry, project_dir=getattr(ns, 'project_dir', None), with_deps=not getattr(ns, 'no_deps', False)) if getattr(ns, 'online', False) else pkg_install_package(ns.name, version=ns.version)
        if 'error' in res:
            _cli_line(str(res['error']), kind='error', file=sys.stderr)
            if res.get('suggestions'):
                _cli_line('Try: ' + ', '.join(res.get('suggestions', [])[:5]), kind='hint', file=sys.stderr)
            return 2
        _print_package_install_result(res)
        return 0
    if pkg_cmd == 'search':
        res = pkg_search_remote(ns.query, registry=ns.registry)
        if res.get('error'):
            _cli_line(str(res['error']), kind='error', file=sys.stderr)
            return 2
        items = res.get('items', [])
        if not items:
            _cli_line(f"No packages found for '{ns.query}'.", kind='warn')
            return 0
        _cli_line(f"Found {len(items)} package(s) for '{ns.query}'", kind='info')
        for item in items:
            versions = ','.join(_package_versions_for_display(item))
            badges = _fmt_list(item.get('badges'))
            print(f"- {item['name']}  latest={item.get('latest') or '-'}  creator={pkg_package_creator(item)}  downloads={item.get('downloads', 0)}  badges={badges}  versions={versions or '-'}")
            if item.get('description'):
                print(f"    {item['description']}")
        if getattr(ns, 'interactive', False):
            picked = _prompt_choice([str(item.get('name')) for item in items[:10]], title='Interactive search results')
            if picked:
                _cli_line(f"selected: {picked}", kind='ok')
                action = 'install'
                if _prompt_yes_no('Add to current project instead of a plain install?', default=False):
                    action = 'add'
                if _prompt_yes_no(f"Run `mellow {action} {picked}` now?", default=True):
                    follow = pkg_add_dependency(picked, project_dir='.', registry=ns.registry) if action == 'add' else pkg_install_remote(picked, registry=ns.registry, project_dir='.')
                    if not follow.get('ok'):
                        _cli_line(str(follow.get('error', f'{action} failed')), kind='error', file=sys.stderr)
                        if follow.get('suggestions'):
                            _cli_line('Try: ' + ', '.join(follow.get('suggestions', [])[:5]), kind='hint', file=sys.stderr)
                        return 2
                    _cli_line(f"package {action}ed: {follow.get('name', picked)}@{follow.get('version', follow.get('spec', 'latest'))}", kind='ok')
                    if follow.get('alias'):
                        _cli_line(f"alias: {follow.get('alias')}", kind='hint')
        return 0
    if pkg_cmd == 'info':
        res = pkg_package_info_remote(ns.name, registry=ns.registry)
        if res.get('error') or not res.get('ok', True):
            _cli_line(str(res.get('error', 'package info failed')), kind='error', file=sys.stderr)
            if res.get('suggestions'):
                _cli_line('Try: ' + ', '.join(res.get('suggestions', [])[:5]), kind='hint', file=sys.stderr)
            return 2
        versions = _package_versions_for_display(res)
        name = res.get('name') or ns.name
        print(f"name       : {name}")
        print(f"latest     : {res.get('latest') or '-'}")
        if res.get('selected') and res.get('selected') != res.get('latest'):
            print(f"selected   : {res.get('selected')}")
        print(f"versions   : {', '.join(versions) if versions else '-'}")
        print(f"creator    : {pkg_package_creator(res)}")
        print(f"downloads  : {res.get('downloads', 0)}")
        if res.get('badges'):
            print(f"badges     : {_fmt_list(res.get('badges'))}")
        if res.get('license'):
            print(f"license    : {res.get('license')}")
        if res.get('keywords'):
            print(f"keywords   : {_fmt_list(res.get('keywords'))}")
        if res.get('published_at'):
            print(f"published  : {res.get('published_by') or '-'} at {res.get('published_at')}")
        if res.get('entry'):
            print(f"entry      : {res.get('entry')}")
        if res.get('description'):
            print(f"description: {res.get('description')}")
        if res.get('registry'):
            print(f"registry   : {res.get('registry')}")
        print(f"install    : mellow install {name}")
        return 0
    if pkg_cmd in {'profile', 'author'}:
        res = pkg_author_profile_remote(ns.author, registry=ns.registry)
        return _print_package_profile(res, ns.author)
    if pkg_cmd in {'verify', 'signature'}:
        res = pkg_package_signature_installed(ns.name, project_dir=getattr(ns, 'project_dir', None)) if getattr(ns, 'installed', False) else pkg_package_signature_remote(ns.name, registry=ns.registry)
        policy = pkg_check_trust_policy(res, strict=getattr(ns, 'strict', False))
        res["trusted"] = policy.get("trusted", False)
        res["trusted_authors"] = policy.get("trusted_authors", [])
        if not policy.get("ok"):
            res["ok"] = False
            res["error"] = policy.get("error")
        return _print_package_verify(res, json_out=getattr(ns, 'json', False))
    if pkg_cmd == 'login':
        if getattr(ns, 'token', None):
            res = pkg_login_with_token(ns.token, registry=ns.registry)
        else:
            if not getattr(ns, 'username', None) or not getattr(ns, 'password', None):
                print('usage: mellow pkg login --token <token> | --username <u> --password <p>')
                return 2
            res = pkg_login_remote(ns.username, ns.password, registry=ns.registry)
        if not res.get('ok'):
            print(f"error: {res.get('error', 'login failed')}")
            if res.get('detail'):
                print(res.get('detail'))
            if res.get('hint'):
                print(f"hint: {res.get('hint')}")
            return 2
        print(f"[OK] logged in as {res.get('username')} -> {res.get('registry')}")
        return 0
    if pkg_cmd == 'whoami':
        res = pkg_whoami_remote(registry=ns.registry)
        if not res.get('ok'):
            print(f"error: {res.get('error', 'not logged in')}")
            return 2
        print(f"username: {res.get('username')}")
        print(f"scopes  : {', '.join(res.get('scopes', []))}")
        return 0
    if pkg_cmd == 'registry':
        res = pkg_set_registry(ns.url)
        print(f"[OK] default registry: {res['registry']}")
        return 0
    if pkg_cmd == 'logout':
        from ...package_manager import clear_auth_token as pkg_clear_auth_token
        res = pkg_clear_auth_token(registry=ns.registry)
        print(f"[OK] logged out from {res['registry']}")
        return 0
    if pkg_cmd == 'list':
        rows = pkg_list_installed()
        if not rows:
            print('No packages installed.')
            return 0
        for row in rows:
            print(f"- {row['name']}@{row['version']} by {pkg_package_creator(row)} -> {row['install_path']}")
        return 0
    if pkg_cmd == 'build':
        res = pkg_build_package_archive(ns.dir, out_path=ns.out)
        print(f"[OK] package archive built: {res['archive']}")
        print(f"sha256: {res['sha256']}")
        return 0
    if pkg_cmd == 'seed-core':
        res = pkg_seed_core_packages(ns.dir, publish_local=getattr(ns, 'publish_local', False))
        print(f"[OK] core starter packages generated: {res['root']}")
        for item in res.get('items', []):
            print(f"- {item['name']} -> {item['dir']}")
        if res.get('published_local'):
            print('Published generated packages into the local registry.')
        return 0
    if pkg_cmd == 'resolve-runtime':
        res = pkg_resolve_project_runtime(ns.dir, registry=ns.registry, strict=getattr(ns, 'strict', False))
        if not res.get('ok'):
            print(f"error: {res.get('error', 'runtime resolution failed')}")
            return 2
        print(f"[OK] runtime map written: {res['runtime_map']}")
        if res.get('auto_added'):
            print('auto-added: ' + ', '.join(f"{k} ({v})" for k, v in res.get('auto_added', {}).items()))
        if res.get('missing'):
            print('missing: ' + ', '.join(res['missing']))
            if res.get('suggestions'):
                for key, vals in (res.get('suggestions') or {}).items():
                    if vals:
                        print(f"  {key} -> {', '.join(vals[:5])}")
        return 0
    if pkg_cmd == 'update':
        res = pkg_update_packages(
            getattr(ns, 'name', None),
            registry=ns.registry,
            project_dir=getattr(ns, 'project_dir', '.'),
            with_deps=not getattr(ns, 'no_deps', False),
            check=getattr(ns, 'check', False),
            all_packages=getattr(ns, 'all_packages', False),
        )
        if not res.get('ok'):
            print(f"error: {res.get('error', 'update failed')}")
            return 2
        if getattr(ns, 'check', False):
            print(f"[OK] update check: {res.get('update_count', 0)} update(s) available")
            for item in res.get('items', []):
                marker = 'UPDATE' if item.get('needs_update') else 'OK'
                print(f"- [{marker}] {item.get('name')} {item.get('current') or '-'} -> {item.get('latest') or '-'}")
            return 0
        for item in res.get('plan', []):
            if item.get('needs_update'):
                print(f"- planned: {item.get('name')} {item.get('current') or '-'} -> {item.get('latest') or '-'}")
        print(f"[OK] dependencies updated: {res.get('count', 0)}")
        for item in res.get('updated', []):
            print(f"- {item.get('name')}@{item.get('version')}")
        if res.get('lockfile'):
            print(f"lockfile: {res.get('lockfile')}")
        return 0
    if pkg_cmd == 'uninstall':
        res = pkg_uninstall_package(ns.name, project_dir=getattr(ns, 'project_dir', '.'))
        if not res.get('ok'):
            print(f"error: {res.get('error', 'uninstall failed')}")
            return 2
        print(f"[OK] package removed: {res['name']}")
        return 0
    if pkg_cmd == 'add':
        pick_name = ns.name
        if getattr(ns, 'interactive', False):
            auto = pkg_interactive_pick_package(ns.name, registry=ns.registry)
            if auto.get('interactive'):
                chosen = _prompt_choice([str(i.get('name')) for i in auto.get('items', [])], title='Namespace suggestions')
                if not chosen:
                    print('cancelled')
                    return 2
                pick_name = chosen
            elif auto.get('selected'):
                pick_name = str(auto.get('selected'))
        res = pkg_add_dependency(pick_name, spec=getattr(ns, 'version', None), project_dir=getattr(ns, 'project_dir', '.'), registry=ns.registry, with_deps=not getattr(ns, 'no_deps', False), alias=getattr(ns, 'alias', None), interactive=getattr(ns, 'interactive', False))
        if not res.get('ok') and not res.get('name'):
            _cli_line(str(res.get('error', 'add failed')), kind='error', file=sys.stderr)
            if res.get('suggestions'):
                _cli_line('Try: ' + ', '.join(res.get('suggestions', [])[:5]), kind='hint', file=sys.stderr)
            if res.get('hint'):
                _cli_line(str(res.get('hint')), kind='hint', file=sys.stderr)
            return 2
        _cli_line(f"dependency added: {res.get('added', ns.name)} ({res.get('spec')})", kind='ok')
        if res.get('alias'):
            _cli_line(f"alias: {res['alias']}", kind='hint')
        if res.get('alias_suggestions'):
            _cli_line('alias suggestions: ' + ', '.join(res.get('alias_suggestions', [])[:5]), kind='hint')
        if res.get('aliases_file'):
            print(f"aliases: {res['aliases_file']}")
        if res.get('cache'):
            print(f"cache: {res['cache']}")
        if res.get('suggestions'):
            _cli_line('autocomplete: ' + ', '.join(res.get('suggestions', [])[:5]), kind='hint')
        return 0
    if pkg_cmd == 'remove':
        res = pkg_remove_dependency(ns.name, project_dir=getattr(ns, 'project_dir', '.'))
        if not res.get('ok'):
            _cli_line(str(res.get('error', 'remove failed')), kind='error', file=sys.stderr)
            return 2
        _cli_line(f"dependency removed: {ns.name}", kind='ok')
        if res.get('removed_alias'):
            _cli_line(f"alias removed: {res['removed_alias']}", kind='hint')
        return 0

    if pkg_cmd == 'diagnose-imports':
        res = pkg_diagnose_imports(ns.dir, registry=ns.registry)
        if not res.get('ok'):
            print(f"error: {res.get('error', 'diagnostics failed')}")
            return 2
        for row in res.get('rows', []):
            line = f"- {row.get('import')} -> {row.get('resolved')} [{row.get('status')}]"
            if row.get('alias'):
                line += f" alias={row.get('alias')}"
            print(line)
            if row.get('detail'):
                print(f"  {row.get('detail')}")
            sugg = (res.get('suggestions') or {}).get(row.get('import'))
            if sugg:
                print('  suggestions: ' + ', '.join(sugg[:5]))
        if res.get('missing'):
            print('missing imports: ' + ', '.join(res.get('missing', [])))
            return 2
        print('[OK] import diagnostics ok')
        return 0
    if pkg_cmd == 'serve':
        from ...registry.server import run_registry_server
        run_registry_server(ns.host, ns.port, ns.data_dir)
        return 0
    print('usage: mellow pkg <init|publish|install|add|remove|search|info|login|whoami|registry|list|build|seed-core|sync-imports|resolve-runtime|diagnose-imports|update|uninstall|serve> ...')
    return 2
