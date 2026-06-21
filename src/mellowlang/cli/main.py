from __future__ import annotations

import argparse
import ast as py_ast
import difflib
import json
import re
import os
import shutil
import sys
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, List

from .. import __version__
from ..lint import lint_source, format_source
from ..compiler import Compiler, CompiledProgram
from ..vm import MellowVM, RunConfig
from .common import (
    _cli_line,
    _find_project_root,
    _json_print,
    _lazy_attr,
    _looks_like_script_path,
    _print_pretty_error,
    _prog,
    _prompt_yes_no,
    _read_text,
    _start_lsp,
)
from .commands.system import (
    _cmd_ask,
    _cmd_assistant,
    _cmd_bench,
    _cmd_completion,
    _cmd_config,
    _cmd_doctor,
    _cmd_explain,
    _cmd_guide,
    _cmd_modules,
    _cmd_native_build,
    _cmd_native_doctor,
    _cmd_native_status,
    _cmd_release_gate,
    _cmd_security_audit,
    _cmd_status,
)
from .ux import (
    CLI_ALIASES,
    MODERN_CMDS,
    format_guide as _format_guide,
    modern_help_text as _modern_help_text,
    quick_help_text as _quick_help_text,
    suggest_command as _suggest_command,
)
from .parser import _build_modern_parser



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
pkg_set_registry = _lazy_attr(_PM, "set_registry")
pkg_get_registry_url = _lazy_attr(_PM, "get_registry_url")
pkg_seed_core_packages = _lazy_attr(_PM, "seed_core_packages")
pkg_sync_imports = _lazy_attr(_PM, "sync_imports")
pkg_uninstall_package = _lazy_attr(_PM, "uninstall_package")
pkg_update_remote = _lazy_attr(_PM, "update_remote")
pkg_resolve_project_runtime = _lazy_attr(_PM, "resolve_project_runtime")
pkg_add_dependency = _lazy_attr(_PM, "add_dependency")
pkg_remove_dependency = _lazy_attr(_PM, "remove_dependency")
pkg_auto_fetch_for_run = _lazy_attr(_PM, "auto_fetch_for_run")
pkg_load_config = _lazy_attr(_PM, "load_config")
pkg_save_config = _lazy_attr(_PM, "save_config")
pkg_config_file_path = _lazy_attr(_PM, "config_file_path")
pkg_cache_root_path = _lazy_attr(_PM, "cache_root_path")
pkg_interactive_pick_package = _lazy_attr(_PM, "interactive_pick_package")
pkg_diagnose_imports = _lazy_attr(_PM, "diagnose_imports")
pkg_suggest_aliases_for_package = _lazy_attr(_PM, "suggest_aliases_for_package")
pkg_scaffold_project = _lazy_attr(_PM, "scaffold_project")
pkg_ensure_project_starter_packages = _lazy_attr(_PM, "ensure_project_starter_packages")
pkg_package_creator = _lazy_attr(_PM, "package_creator")
pkg_author_profile_remote = _lazy_attr(_PM, "author_profile_remote")
pkg_package_signature_remote = _lazy_attr(_PM, "package_signature_remote")
pkg_package_signature_installed = _lazy_attr(_PM, "package_signature_installed")
pkg_update_packages = _lazy_attr(_PM, "update_packages")
pkg_trust_author = _lazy_attr(_PM, "trust_author")
pkg_trusted_authors = _lazy_attr(_PM, "trusted_authors")
pkg_check_trust_policy = _lazy_attr(_PM, "check_trust_policy")

serve_playground = _lazy_attr("mellowlang.playground", "serve_playground")
build_static_playground = _lazy_attr("mellowlang.playground", "build_static_playground")
native_vm_status = _lazy_attr("mellowlang.native_vm", "native_vm_status")
build_native_vm = _lazy_attr("mellowlang.native_vm", "build_native_vm")
standalone_runtime_status = _lazy_attr("mellowlang.standalone_runtime", "standalone_runtime_status")
build_standalone_runtime = _lazy_attr("mellowlang.standalone_runtime", "build_standalone_runtime")
compile_standalone_image = _lazy_attr("mellowlang.standalone_runtime", "compile_standalone_image")
standalone_run_image = _lazy_attr("mellowlang.standalone_runtime", "standalone_run_image")
parse_window_file = _lazy_attr("mellowlang.desktop_host", "parse_window_file")
launch_window = _lazy_attr("mellowlang.desktop_host", "launch_window")
desktop_status = _lazy_attr("mellowlang.desktop_host", "desktop_status")
build_desktop_bundle = _lazy_attr("mellowlang.desktop_host", "build_desktop_bundle")
parse_mmg_file = _lazy_attr("mellowlang.mmg_runtime", "parse_mmg_file")
launch_mmg = _lazy_attr("mellowlang.mmg_runtime", "launch_mmg")
mmg_status = _lazy_attr("mellowlang.mmg_runtime", "mmg_status")
mmg_gpu_status = _lazy_attr("mellowlang.mmg_gpu_runtime", "mmg_gpu_status")
build_mmg_gpu_backend = _lazy_attr("mellowlang.mmg_gpu_runtime", "build_mmg_gpu_backend")
export_mmg_gpu_commands = _lazy_attr("mellowlang.mmg_gpu_runtime", "export_mmg_gpu_commands")
run_mmg_gpu_native = _lazy_attr("mellowlang.mmg_gpu_runtime", "run_mmg_gpu_native")
sm_encode_file = _lazy_attr("mellowlang.sm_codec", "encode_file")
sm_decode_file = _lazy_attr("mellowlang.sm_codec", "decode_file")
sm_inspect_file = _lazy_attr("mellowlang.sm_codec", "inspect_file")
encode_video_to_melv = _lazy_attr("mellowlang.melv_codec", "encode_video_to_melv")
decode_melv_to_video = _lazy_attr("mellowlang.melv_codec", "decode_melv_to_video")
inspect_melv = _lazy_attr("mellowlang.melv_codec", "inspect_melv")
extract_melv_frames = _lazy_attr("mellowlang.melv_codec", "extract_melv_frames")

_AG = "mellowlang.agents"
AgentRuntime = _lazy_attr(_AG, "AgentRuntime")
MemoryStore = _lazy_attr(_AG, "MemoryStore")
ObservationLog = _lazy_attr(_AG, "ObservationLog")
PolicyEngine = _lazy_attr(_AG, "PolicyEngine")
SimpleRAGIndex = _lazy_attr(_AG, "SimpleRAGIndex")
Workflow = _lazy_attr(_AG, "Workflow")
WorkflowRunner = _lazy_attr(_AG, "WorkflowRunner")
WorkflowStep = _lazy_attr(_AG, "WorkflowStep")
builtin_tool_registry = _lazy_attr(_AG, "builtin_tool_registry")
resolve_model_adapter = _lazy_attr(_AG, "resolve_model_adapter")
render_prompt_file = _lazy_attr(_AG, "render_prompt_file")
load_tool_manifest = _lazy_attr(_AG, "load_tool_manifest")
load_agent_package = _lazy_attr(_AG, "load_agent_package")
init_agent_package = _lazy_attr(_AG, "init_agent_package")
apply_tool_manifest = _lazy_attr(_AG, "apply_tool_manifest")
build_agent_archive = _lazy_attr(_AG, "build_agent_archive")
publish_agent_from_dir = _lazy_attr(_AG, "publish_agent_from_dir")
install_agent_package = _lazy_attr(_AG, "install_agent_package")
search_agent_local = _lazy_attr(_AG, "search_agent_local")
publish_agent_remote = _lazy_attr(_AG, "publish_agent_remote")
install_agent_remote = _lazy_attr(_AG, "install_agent_remote")
search_agent_remote = _lazy_attr(_AG, "search_agent_remote")
load_installed_agent = _lazy_attr(_AG, "load_installed_agent")
agent_dependency_graph = _lazy_attr(_AG, "agent_dependency_graph")
generate_agent_lock = _lazy_attr(_AG, "generate_agent_lock")
write_agent_lock = _lazy_attr(_AG, "write_agent_lock")
install_agent_with_lock = _lazy_attr(_AG, "install_agent_with_lock")
set_agent_auth_token = _lazy_attr(_AG, "set_agent_auth_token")
clear_agent_auth_token = _lazy_attr(_AG, "clear_agent_auth_token")
agent_registry_whoami = _lazy_attr(_AG, "agent_registry_whoami")
SandboxConfig = _lazy_attr(_AG, "SandboxConfig")
set_secret = _lazy_attr(_AG, "set_secret")
remove_secret = _lazy_attr(_AG, "remove_secret")
list_secrets = _lazy_attr(_AG, "list_secrets")
resolve_secret_env = _lazy_attr(_AG, "resolve_secret_env")
read_observation_file = _lazy_attr(_AG, "read_observation_file")
load_signed_policy = _lazy_attr(_AG, "load_signed_policy")
build_deployment_manifest = _lazy_attr(_AG, "build_deployment_manifest")
load_deployment_manifest = _lazy_attr(_AG, "load_deployment_manifest")
write_deployment_bundle = _lazy_attr(_AG, "write_deployment_bundle")
sign_capability_policy = _lazy_attr(_AG, "sign_capability_policy")
register_deployment = _lazy_attr(_AG, "register_deployment")
list_deployments = _lazy_attr(_AG, "list_deployments")
get_deployment_status = _lazy_attr(_AG, "get_deployment_status")
sync_deployment = _lazy_attr(_AG, "sync_deployment")
list_revisions = _lazy_attr(_AG, "list_revisions")
rollout_revision = _lazy_attr(_AG, "rollout_revision")
run_health_check = _lazy_attr(_AG, "run_health_check")
update_traffic_split = _lazy_attr(_AG, "update_traffic_split")
rollback_deployment = _lazy_attr(_AG, "rollback_deployment")
record_deployment_metrics = _lazy_attr(_AG, "record_deployment_metrics")
get_deployment_metrics = _lazy_attr(_AG, "get_deployment_metrics")
get_autoscaling_signals = _lazy_attr(_AG, "get_autoscaling_signals")
set_alert_rules = _lazy_attr(_AG, "set_alert_rules")
evaluate_alerts = _lazy_attr(_AG, "evaluate_alerts")
add_job = _lazy_attr(_AG, "add_job")
agent_list_jobs = _lazy_attr(_AG, "list_jobs")
run_due_jobs = _lazy_attr(_AG, "run_due_jobs")
run_background_runner = _lazy_attr(_AG, "run_background_runner")
read_runner_status = _lazy_attr(_AG, "read_runner_status")
add_trigger = _lazy_attr(_AG, "add_trigger")
list_triggers = _lazy_attr(_AG, "list_triggers")
emit_event = _lazy_attr(_AG, "emit_event")
add_webhook = _lazy_attr(_AG, "add_webhook")
list_webhooks = _lazy_attr(_AG, "list_webhooks")
receive_webhook = _lazy_attr(_AG, "receive_webhook")
submit_job = _lazy_attr(_AG, "submit_job")
get_queue_item = _lazy_attr(_AG, "get_queue_item")
list_queue = _lazy_attr(_AG, "list_queue")
drain_queue = _lazy_attr(_AG, "drain_queue")
list_dead_letter = _lazy_attr(_AG, "list_dead_letter")
retry_queue_item = _lazy_attr(_AG, "retry_queue_item")
read_queue_log = _lazy_attr(_AG, "read_queue_log")
queue_stats = _lazy_attr(_AG, "queue_stats")
start_webhook_server = _lazy_attr(_AG, "start_webhook_server")
read_webhook_server_status = _lazy_attr(_AG, "read_webhook_server_status")
read_job_api_status = _lazy_attr(_AG, "read_job_api_status")


# ============================================================
# CLI policy
# - Commands use the explicit subcommand interface.
# ----------------------------


def _cmd_pack(entry: str, out_path: str, include: list[str], name: str, version: str) -> int:
    """Create a portable bundle for game/mod distribution."""
    import json, os, zipfile, time
    entry_p = Path(entry).resolve()
    if not entry_p.exists():
        print(f"error: entry not found: {entry_p}")
        return 2

    root_dir = entry_p.parent
    out_p = Path(out_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": name,
        "version": version,
        "entry": entry_p.name,
        "created_utc": int(time.time()),
    }

    def _add(z: zipfile.ZipFile, p: Path, arc_prefix: str = ""):
        p = p.resolve()
        if p.is_dir():
            for sub in p.rglob("*"):
                if sub.is_file():
                    rel = sub.relative_to(root_dir)
                    z.write(sub, arcname=str(Path(arc_prefix) / rel))
        else:
            rel = p.relative_to(root_dir) if root_dir in p.parents else p.name
            z.write(p, arcname=str(Path(arc_prefix) / rel))

    with zipfile.ZipFile(out_p, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # entry script
        _add(z, entry_p)
        # common folders
        for folder in ("libs", "assets"):
            fp = root_dir / folder
            if fp.exists():
                _add(z, fp)
        # extras
        for ex in include or []:
            ep = (root_dir / ex).resolve() if not Path(ex).is_absolute() else Path(ex).resolve()
            if ep.exists():
                _add(z, ep)
        # manifest
        z.writestr("mellow.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    print(f"[OK] packaged: {out_p}")
    return 0

def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _to_plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    return value


def _format_ir_text(program: Any) -> str:
    lines: list[str] = []
    instructions = getattr(program, 'instructions', []) or []
    for idx, ins in enumerate(instructions):
        args = ', '.join(repr(a) for a in getattr(ins, 'args', ()) or ())
        loc = f" @ {getattr(ins, 'line', 0)}:{getattr(ins, 'col', 1)}"
        lines.append(f"{idx:04d}  {getattr(ins, 'op', '?')}" + (f" {args}" if args else '') + loc)
    funcs = getattr(program, 'functions', {}) or {}
    if funcs:
        lines.append('')
        lines.append('[functions]')
        for name, meta in funcs.items():
            lines.append(f"- {name}: entry={meta.entry_label} params={meta.params} kind={meta.kind}")
    events = getattr(program, 'events', {}) or {}
    if events:
        lines.append('')
        lines.append('[events]')
        for name, meta in events.items():
            lines.append(f"- {name}: entry={meta.entry_label} params={meta.params} kind={meta.kind}")
    return '\n'.join(lines)


def _format_cfg_text(cfg: Any) -> str:
    lines: list[str] = []
    lines.append(f"entry: {getattr(cfg, 'entry_label', 'entry')}")
    for block in getattr(cfg, 'blocks', []) or []:
        lines.append('')
        lines.append(f"[{getattr(block, 'label', '?')}] id={getattr(block, 'id', '?')} span={getattr(block, 'start', '?')}..{getattr(block, 'end', '?')}")
        preds = ', '.join(getattr(block, 'predecessors', []) or []) or '-'
        succs = ', '.join(getattr(block, 'successors', []) or []) or '-'
        lines.append(f"  preds: {preds}")
        lines.append(f"  succs: {succs}")
        for idx, ins in enumerate(getattr(block, 'instructions', []) or []):
            args = ', '.join(repr(a) for a in getattr(ins, 'args', ()) or ())
            loc = f" @ {getattr(ins, 'line', 0)}:{getattr(ins, 'col', 1)}"
            lines.append(f"    {idx:02d}  {getattr(ins, 'op', '?')}" + (f" {args}" if args else '') + loc)
    return '\n'.join(lines)


def _emit_dump(title: str, payload: Any, fmt: str) -> None:
    print(f"=== {title} ===")
    if fmt == 'json':
        print(json.dumps(_to_plain(payload), ensure_ascii=False, indent=2))
    else:
        if title.startswith('AST'):
            print(json.dumps(_to_plain(payload), ensure_ascii=False, indent=2))
        elif hasattr(payload, 'blocks'):
            print(_format_cfg_text(payload))
        elif hasattr(payload, 'instructions'):
            print(_format_ir_text(payload))
        else:
            print(json.dumps(_to_plain(payload), ensure_ascii=False, indent=2))
    print()


def _cmd_compile(file: str, target: str, out_path: str | None, *, dump_ast: bool = False, dump_ir: bool = False, dump_ir_optimized: bool = False, dump_cfg: bool = False, dump_cfg_optimized: bool = False, dump_dom: bool = False, dump_dom_optimized: bool = False, dump_def_use: bool = False, dump_def_use_optimized: bool = False, dump_ssa: bool = False, dump_ssa_optimized: bool = False, dump_format: str = 'text', optimize: bool = True) -> int:
    p = Path(file)
    if not p.exists():
        print(f"error: path not found: {p}")
        return 2
    src = _read_text(p)
    if target == "python":
        from ..fast_compiler import PyTranspiler
        py_src = PyTranspiler().transpile(src.splitlines(), filename=str(p))
        out = Path(out_path) if out_path else p.with_suffix('.generated.py')
        out.write_text(py_src, encoding='utf-8')
        print(f"[OK] compiled to Python: {out}")
        return 0
    prog = Compiler().compile(src, filename=str(p), optimize=optimize)
    out = Path(out_path) if out_path else p.with_suffix('.mellowc.json')
    if dump_ast and getattr(prog, 'ast', None) is not None:
        _emit_dump('AST', prog.ast, dump_format)
    if dump_ir and getattr(prog, 'ir', None) is not None:
        _emit_dump('IR', prog.ir, dump_format)
    if dump_cfg and getattr(prog, 'cfg', None) is not None:
        _emit_dump('CFG', prog.cfg, dump_format)
    if dump_dom and getattr(prog, 'dominator_tree', None) is not None:
        _emit_dump('Dominator Tree', prog.dominator_tree, dump_format)
    if dump_def_use and getattr(prog, 'def_use', None) is not None:
        _emit_dump('Def-Use', prog.def_use, dump_format)
    if dump_ssa and getattr(prog, 'ssa_program', None) is not None:
        _emit_dump('SSA', prog.ssa_program, dump_format)
    if dump_ir_optimized and getattr(prog, 'optimized_ir', None) is not None:
        _emit_dump('IR Optimized', prog.optimized_ir, dump_format)
    if dump_cfg_optimized and getattr(prog, 'optimized_cfg', None) is not None:
        _emit_dump('CFG Optimized', prog.optimized_cfg, dump_format)
    if dump_dom_optimized and getattr(prog, 'optimized_dominator_tree', None) is not None:
        _emit_dump('Dominator Tree Optimized', prog.optimized_dominator_tree, dump_format)
    if dump_def_use_optimized and getattr(prog, 'optimized_def_use', None) is not None:
        _emit_dump('Def-Use Optimized', prog.optimized_def_use, dump_format)
    if dump_ssa_optimized and getattr(prog, 'optimized_ssa_program', None) is not None:
        _emit_dump('SSA Optimized', prog.optimized_ssa_program, dump_format)
    if (dump_ir_optimized or dump_cfg_optimized or dump_ssa_optimized) and getattr(prog, 'optimization', None) is not None:
        _emit_dump('Optimization Summary', prog.optimization, dump_format)

    payload = {
        'filename': prog.filename,
        'pipeline': getattr(prog, 'pipeline', 'bytecode'),
        'bytecode': prog.bytecode,
        'func_table': prog.func_table or {},
        'event_table': prog.event_table or {},
        'cfg': _to_plain(getattr(prog, 'cfg', None)),
        'optimized_cfg': _to_plain(getattr(prog, 'optimized_cfg', None)),
        'optimization': _to_plain(getattr(prog, 'optimization', None)),
        'dominator_tree': _to_plain(getattr(prog, 'dominator_tree', None)),
        'optimized_dominator_tree': _to_plain(getattr(prog, 'optimized_dominator_tree', None)),
        'def_use': _to_plain(getattr(prog, 'def_use', None)),
        'optimized_def_use': _to_plain(getattr(prog, 'optimized_def_use', None)),
        'ssa_program': _to_plain(getattr(prog, 'ssa_program', None)),
        'optimized_ssa_program': _to_plain(getattr(prog, 'optimized_ssa_program', None)),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"[OK] compiled to bytecode: {out}")
    return 0




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
        from ..package_manager import clear_auth_token as pkg_clear_auth_token
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
        from ..registry.server import run_registry_server
        run_registry_server(ns.host, ns.port, ns.data_dir)
        return 0
    print('usage: mellow pkg <init|publish|install|add|remove|search|info|login|whoami|registry|list|build|seed-core|sync-imports|resolve-runtime|diagnose-imports|update|uninstall|serve> ...')
    return 2


def _cmd_check(file: str, json_out: bool) -> int:
    """
    Check mode:
      - First, attempt to compile (catches SYNTAX errors with code frame)
      - Then, run lints; print code-frame per issue
    """
    p = Path(file)
    if not p.exists():
        err = {"ok": False, "error": f"path not found: {p}"}
        if json_out:
            _json_print(err)
        else:
            print(f"error: {err['error']}")
        return 2

    # Directory mode: check all *.mellow files (recursive).
    if p.is_dir():
        targets = sorted(p.rglob("*.mellow"))
        if not targets:
            if json_out:
                _json_print({"ok": True, "checked": 0, "errors": 0})
            else:
                print("OK ok (no .mellow files found)")
            return 0

        errors = 0
        checked = 0
        for t in targets:
            checked += 1
            rc = _cmd_check(str(t), json_out=json_out)
            if rc != 0:
                errors += 1
        if json_out:
            _json_print({"ok": errors == 0, "checked": checked, "errors": errors})
        else:
            if errors == 0:
                print(f"\nOK ok ({checked} file(s))")
            else:
                print(f"\nERR {errors} error(s) in {checked} file(s)")
        return 0 if errors == 0 else 1

    src = _read_text(p)
    lines = src.splitlines(True)

    # 1) Syntax check via compiler (best signal)
    try:
        Compiler().compile(src, filename=str(p))
    except Exception as e:
        if json_out:
            _json_print({"ok": False, "error": str(e)})
        else:
            _print_pretty_error(e, filename=str(p), source_lines=lines)
        return 1

    # 2) Lint/style issues (non-fatal but should be visible)
    issues = lint_source(src)
    if json_out:
        _json_print({
            "ok": len(issues) == 0,
            "file": str(p),
            "issues": [asdict(it) if hasattr(it, "__dict__") else {"message": str(it)} for it in issues],
        })
        return 0 if not issues else 1

    if not issues:
        print("OK ok")
        return 0

    # Print code-frame per issue (Frinds-style)
    for it in issues:
        kind = getattr(it, "kind", "LINT").upper()
        msg = getattr(it, "message", str(it))
        ln = getattr(it, "line", None)
        col = getattr(it, "col", None)

        # fabricate an error-like object compatible with _print_pretty_error
        class _IssueErr(Exception):
            pass
        ee = _IssueErr(msg)
        setattr(ee, "error_type", kind)
        setattr(ee, "message", msg)
        setattr(ee, "filename", str(p))
        setattr(ee, "line_num", ln)
        setattr(ee, "col", col)
        _print_pretty_error(ee, filename=str(p), source_lines=lines)

    return 1
def _cmd_fmt(files: List[str], write: bool, check: bool) -> int:
    changed = 0
    for f in files:
        p = Path(f)
        if p.is_dir():
            for sub in p.rglob("*.mellow"):
                changed += _fmt_one(sub, write, check)
        else:
            changed += _fmt_one(p, write, check)
    return 0 if (not check or changed == 0) else 1

def _fmt_one(p: Path, write: bool, check: bool) -> int:
    if not p.exists():
        print(f"skip: {p} (not found)")
        return 0
    src = _read_text(p)
    out = format_source(src)
    if out == src:
        return 0
    if check:
        print(f"would format: {p}")
        return 1
    if write:
        p.write_text(out, encoding="utf-8")
        print(f"formatted: {p}")
        return 1
    sys.stdout.write(out)
    return 1

def _cmd_init(dest_dir: str, force: bool) -> int:
    dest = Path(dest_dir).resolve()
    template = Path(__file__).resolve().parents[2] / "project_template"
    if not template.exists():
        print("error: project_template not found.")
        return 2
    if dest.exists() and any(dest.iterdir()) and not force:
        print("error: destination not empty. Use --force.")
        return 2
    if dest.exists() and force:
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, dest, dirs_exist_ok=True)
    print(f"[OK] created project: {dest}")
    return 0


def _cmd_new(dest_dir: str, force: bool, *, with_core: bool = True, preset: str = "starter") -> int:
    res = pkg_scaffold_project(dest_dir, force=force, with_core=with_core, preset=preset)
    if not res.get("ok"):
        print(f"error: {res.get('error', 'project scaffold failed')}")
        return 2
    print(f"[OK] created project: {res['project_dir']}")
    print(f"[OK] manifest: {res['manifest']}")
    print(f"[OK] preset: {res.get('preset', 'starter')}")
    if res.get('preload'):
        installed = []
        for item in res.get('preload', {}).get('installed', []):
            name = item.get('name')
            version = item.get('version')
            row = f"{name}@{version}" if version else str(name)
            if row not in installed:
                installed.append(row)
        if installed:
            print("[OK] starter packages: " + ", ".join(installed))
        runtime = (res.get('preload') or {}).get('runtime') or {}
        if runtime.get('runtime_map'):
            print(f"[OK] runtime map: {runtime['runtime_map']}")
    return 0


def _cmd_mmg_status(json_out: bool = False) -> int:
    payload = mmg_status()
    payload["native"] = mmg_gpu_status()
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"mmg runtime: {payload['engine']}")
        print(f"backend: {payload['backend']}")
        print(f"platform: {payload['platform']}")
        print(f"display available: {payload['display_available']}")
        print(payload['note'])
        native = payload['native']
        print(f"native backend: {native['backend']}")
        print(f"native binary exists: {native['binary_exists']}")
        print(f"sdl2 dev: {native['sdl2_dev']}")
    return 0


def _cmd_mmg_run(file: str, dump_spec: bool = False) -> int:
    spec = parse_mmg_file(file)
    if dump_spec:
        print(json.dumps(spec, indent=2, ensure_ascii=False))
        return 0
    return int(launch_mmg(spec) or 0)


def _cmd_mmg_build_native(json_out: bool = False) -> int:
    status = mmg_gpu_status()
    try:
        engine = build_mmg_gpu_backend()
        payload = {**status, "built": True, "engine_path": str(engine)}
    except Exception as exc:
        payload = {**status, "built": False, "error": str(exc)}
        if json_out:
            _json_print(payload)
            return 1
        _cli_line(f"native MMG build failed: {exc}", kind="error")
        _cli_line("tip: install SDL2 development libraries and CMake on the target machine.", kind="hint")
        return 1
    if json_out:
        _json_print(payload)
    else:
        _cli_line(f"native MMG engine built: {payload['engine_path']}", kind="ok")
    return 0


def _cmd_mmg_export_native(file: str, out: str) -> int:
    spec = parse_mmg_file(file)
    path = export_mmg_gpu_commands(spec, out)
    _cli_line(f"exported native MMG scene: {path}", kind="ok")
    return 0


def _cmd_mmg_run_native(file: str, build_if_missing: bool = False, keep_scene: bool = False, scene_out: str | None = None) -> int:
    return int(run_mmg_gpu_native(file, build_if_missing=build_if_missing, keep_scene=keep_scene, scene_out=scene_out) or 0)


def _cmd_sm_pack(input_path: str, out_path: str | None, json_out: bool) -> int:
    payload = sm_encode_file(input_path, out_path)
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"packed {payload['input']} -> {payload['output']} ({payload['ratio']:.2%})")
    return 0


def _cmd_sm_unpack(input_path: str, out_path: str | None, json_out: bool) -> int:
    payload = sm_decode_file(input_path, out_path)
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"unpacked {payload['input']} -> {payload['output']}")
    return 0


def _cmd_sm_inspect(input_path: str, json_out: bool) -> int:
    payload = sm_inspect_file(input_path)
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f".sm codec: {payload['codec']}")
        print(f"dictionary entries: {payload['dictionary_entries']}")
        print(f"original size: {payload['original_size']}")
        print(f"compressed size: {payload['compressed_size']}")
    return 0


def _cmd_melv_encode(input_path: str, out_path: str, fps: float | None, max_frames: int | None, json_out: bool) -> int:
    payload = encode_video_to_melv(input_path, out_path, fps=fps, max_frames=max_frames)
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"encoded {payload['input']} -> {payload['output']} ({payload['frames']} frames)")
    return 0


def _cmd_melv_decode(input_path: str, out_path: str, json_out: bool) -> int:
    payload = decode_melv_to_video(input_path, out_path)
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"decoded {payload['input']} -> {payload['output']} ({payload['frames']} frames)")
    return 0


def _cmd_melv_extract(input_path: str, out_dir: str, json_out: bool) -> int:
    payload = extract_melv_frames(input_path, out_dir)
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"extracted {payload['frames']} frames to {payload['output']}")
    return 0


def _cmd_melv_inspect(input_path: str, json_out: bool) -> int:
    payload = inspect_melv(input_path)
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f".melv codec: {payload['codec']}")
        print(f"size: {payload['width']}x{payload['height']} @ {payload['fps']} fps")
        print(f"frames: {payload['frames']}")
    return 0


def _cmd_desktop_status(json_out: bool = False) -> int:
    payload = desktop_status()
    if json_out:
        _json_print(payload)
    else:
        print(f"desktop host: {payload['engine']}")
        print("supported: " + ", ".join(payload.get('supported') or []))
        print("platforms: " + ", ".join(payload.get('cross_platform') or []))
        print(f"builder: {payload.get('builder')}")
    return 0


def _cmd_desktop_build(file: str, out: str, name: str | None, *, onefile: bool, console: bool, json_out: bool) -> int:
    payload = build_desktop_bundle(file, out_dir=out, name=name, onefile=onefile, windowed=not console)
    if json_out:
        _json_print(payload)
    else:
        print(f"bundle: {payload['name']}")
        print(f"entry: {payload['entry']}")
        print(f"out: {payload['out_dir']}")
        print(f"builder: {payload['builder']}")
        print(f"spec: {payload['spec_file']}")
        if payload.get('note'):
            print(payload['note'])
        elif payload.get('built'):
            print('build completed')
    return 0


def _cmd_desktop_run(file: str, dump_spec: bool = False) -> int:
    spec = parse_window_file(file)
    if dump_spec:
        print(json.dumps(spec, ensure_ascii=False, indent=2))
        return 0
    return int(launch_window(spec) or 0)

def _cmd_run(file: str, *, json_out: bool, engine: str, record_path: str | None, replay_path: str | None,
             seed: int | None, global_seed: int | None, allow_ask: bool, no_wait: bool,
             allow_storage: bool, storage_dir: str | None, allow_unsafe_fs: bool,
             max_steps: int | None, max_ms: int | None, syscall_budget: int | None,
             profile: bool,
             trace: bool = False, step: bool = False, break_lines: str | None = None,
             watch: str | None = None, ai_timeline: str | None = None,
             color: bool = False, no_color: bool = False, registry: str | None = None, no_resolve: bool = False,
             sandbox_profile: str = "default", allow_data_write: bool = False,
             data_max_batch_size: int | None = None, data_max_query_rows: int | None = None,
             data_max_record_bytes: int | None = None, data_max_open_streams: int | None = None,
             native_required: bool = False) -> int:
    p = Path(file)

    # Secure save system default (dev-friendly). In project mode this becomes deny-by-default.
    allow_save: bool = True
    sandbox_profile = str(sandbox_profile or "default").strip().lower()
    if sandbox_profile == "finance":
        allow_ask = False
        no_wait = True
        allow_storage = False
        allow_save = False
        allow_unsafe_fs = False
        if max_steps is None:
            max_steps = 100_000
        if syscall_budget is None:
            syscall_budget = 100
    elif sandbox_profile == "data":
        allow_ask = False
        no_wait = True
        allow_save = False
        allow_unsafe_fs = False
        if max_steps is None:
            max_steps = 1_000_000
        if max_ms is None:
            max_ms = 30_000
        if syscall_budget is None:
            syscall_budget = 10_000
        if data_max_batch_size is None:
            data_max_batch_size = 1_000
        if data_max_query_rows is None:
            data_max_query_rows = 5_000

    # --- Project mode auto-detect (v1.4.5 standard) ---
    project_root: Path | None = None
    manifest_path: Path | None = None
    manifest_data: dict[str, Any] = {}

    if p.exists() and p.is_dir():
        # Running a directory: treat it as project root if it has mellow.json
        if (p / "mellow.json").exists():
            project_root = p.resolve()
    else:
        # Running a file: search parents for mellow.json
        project_root = _find_project_root(p)

    if project_root is None:
        # Also try CWD (useful when running relative files)
        project_root = _find_project_root(Path.cwd())

    runtime_root = project_root or (p.parent if p.exists() and p.is_file() else Path.cwd())
    runtime_map = None
    rr: dict[str, Any] | None = None
    if not no_resolve:
        try:
            rr = pkg_auto_fetch_for_run(p if p.exists() else runtime_root, registry=registry, strict=False)
            runtime_map = rr.get("runtime_map")
            if rr.get("installed"):
                installed_rows = [f"{item.get('name')}@{item.get('version')}" for item in rr.get('installed', [])]
                _cli_line('auto-installed missing packages: ' + ', '.join(installed_rows), kind='ok')
            if rr.get("auto_added"):
                auto_added_rows = [f"{k} ({v})" for k, v in (rr.get('auto_added') or {}).items()]
                _cli_line('added to manifest: ' + ', '.join(auto_added_rows), kind='hint')
        except Exception:
            runtime_map = None

    if project_root is not None:
        manifest_path = project_root / "mellow.json"
        try:
            manifest_data = json.loads(_read_text(manifest_path))
        except Exception:
            manifest_data = {}

    project_mode = bool(project_root is not None and bool(manifest_data))

    # If directory run: resolve entry
    if p.exists() and p.is_dir() and project_mode:
        entry = str(manifest_data.get("entry", "main.mellow"))
        p = (project_root / entry).resolve()

    # Apply manifest defaults if not explicitly provided
    if project_mode:
        if global_seed is None and manifest_data.get("global_seed") is not None:
            try:
                global_seed = int(manifest_data.get("global_seed"))
            except Exception:
                pass

        # permissions can be list[str] (preferred) or dict (compatibility input)
        perms = manifest_data.get("permissions")
        if isinstance(perms, dict):
            if not allow_ask and perms.get("allow_ask") is True:
                allow_ask = True
            if perms.get("allow_wait") is False:
                no_wait = True
            if perms.get("allow_storage") is False:
                allow_storage = False
            # Secure save system (v1.3.4)
            allow_save = True
            if perms.get("allow_save") is False:
                allow_save = False
            if storage_dir is None and perms.get("storage_dir"):
                storage_dir = str(perms.get("storage_dir"))
        else:
            allow_save = True

    if not p.exists():
        err = {"ok": False, "error": f"file not found: {p}"}
        if json_out:
            _json_print(err)
        else:
            print(f"error: {err['error']}")
        return 2

    
    src = _read_text(p)

    # error color policy is currently handled by runtime; here we only ensure ANSI support isn't forced wrongly.
    # (kept for CLI compatibility)
    use_color = True if color else (False if no_color else None)

    # v1.4.9: fast engine (compile-to-Python) shortcut
    if engine == "fast":
        try:
            from .fast_compiler import FastRunner as _FastRunner
        except ImportError:
            from ..fast_compiler import FastRunner as _FastRunner
        _fr = _FastRunner(capture_output=False)
        try:
            _fr.run(src, filename=str(p))
        except SystemExit:
            pass
        except Exception as _fe:
            print(f"error: {_fe}", file=sys.stderr)
            return 1
        return 0

    try:
        comp = Compiler()
        program = comp.compile(src, filename=str(p))

        vm = MellowVM()
        # Dev standard: if no project manifest, default storage_dir to CWD (like Python/Lua)
        if not project_mode and storage_dir is None:
            storage_dir = "."

        # Project standard: parse sandbox_root + fs permissions
        sandbox_root = None
        fs_read_allow: str | None = None
        fs_write_allow: str | None = None
        save_slots_max: int | None = None
        save_bytes_max: int | None = None
        # Networking (v1.3.5)
        allow_net: bool = False
        net_http_allow: str | None = None
        net_ws_allow: str | None = None
        net_max_bytes: int | None = None
        net_timeout_s: float | None = None
        interop_allow: str | None = None
        if project_mode:
            sandbox_root = str(manifest_data.get("sandbox_root") or manifest_data.get("sandbox") or "saves")
            perms = manifest_data.get("permissions")
            read_roots: list[str] = []
            write_roots: list[str] = []
            interop_items: list[str] = []
            # Secure save system perms
            allow_save = False
            if isinstance(perms, list):
                http_allow: list[str] = []
                ws_allow: list[str] = []
                for item in perms:
                    if not isinstance(item, str):
                        continue
                    t = item.strip()
                    if t == 'save' or t == 'save:true':
                        allow_save = True
                    elif t == 'save:false':
                        allow_save = False
                    elif t.startswith('save.max_slots:'):
                        try:
                            save_slots_max = int(t.split(':', 1)[1])
                        except Exception:
                            pass
                    elif t.startswith('save.max_bytes:'):
                        try:
                            save_bytes_max = int(t.split(':', 1)[1])
                        except Exception:
                            pass
                    # Networking perms
                    if t == 'net' or t == 'net:true':
                        allow_net = True
                    elif t == 'net:false':
                        allow_net = False
                    elif t.startswith('net.http:'):
                        http_allow.append(t.split(':', 1)[1])
                        allow_net = True
                    elif t.startswith('net.ws:'):
                        ws_allow.append(t.split(':', 1)[1])
                        allow_net = True
                    elif t.startswith('net.max_bytes:'):
                        try:
                            net_max_bytes = int(t.split(':', 1)[1])
                        except Exception:
                            pass
                    elif t.startswith('net.timeout_s:'):
                        try:
                            net_timeout_s = float(t.split(':', 1)[1])
                        except Exception:
                            pass
                    elif t.startswith('interop:'):
                        interop_name = t.split(':', 1)[1].strip()
                        if interop_name:
                            interop_items.append(interop_name)
                    if t.startswith("fs.read:"):
                        read_roots.append(t.split(":", 1)[1])
                    elif t.startswith("fs.write:"):
                        write_roots.append(t.split(":", 1)[1])
                    elif t.startswith("fs.rw:"):
                        r = t.split(":", 1)[1]
                        read_roots.append(r)
                        write_roots.append(r)
            elif isinstance(perms, dict):
                # compatibility input
                allow_save = bool(perms.get('allow_save', True))
                allow_net = bool(perms.get('allow_net', False))
                try:
                    if perms.get('net_max_bytes') is not None:
                        net_max_bytes = int(perms.get('net_max_bytes'))
                except Exception:
                    pass
                try:
                    if perms.get('net_timeout_s') is not None:
                        net_timeout_s = float(perms.get('net_timeout_s'))
                except Exception:
                    pass
                if perms.get('net_http_allow'):
                    net_http_allow = str(perms.get('net_http_allow'))
                if perms.get('net_ws_allow'):
                    net_ws_allow = str(perms.get('net_ws_allow'))
                raw_interop = perms.get('interop') or perms.get('interop_allow')
                if isinstance(raw_interop, list):
                    interop_allow = ",".join(str(item).strip() for item in raw_interop if str(item).strip())
                elif isinstance(raw_interop, str):
                    interop_allow = raw_interop
                try:
                    if perms.get('save_slots_max') is not None:
                        save_slots_max = int(perms.get('save_slots_max'))
                except Exception:
                    pass
                try:
                    if perms.get('save_bytes_max') is not None:
                        save_bytes_max = int(perms.get('save_bytes_max'))
                except Exception:
                    pass
            fs_read_allow = ",".join(read_roots) if read_roots else None
            fs_write_allow = ",".join(write_roots) if write_roots else None
            if isinstance(perms, list):
                net_http_allow = ",".join(http_allow) if http_allow else None
                net_ws_allow = ",".join(ws_allow) if ws_allow else None
                interop_allow = ",".join(interop_items) if interop_items else None

        if sandbox_profile == "finance":
            allow_ask = False
            no_wait = True
            allow_storage = False
            allow_save = False
            allow_net = False
            net_http_allow = None
            net_ws_allow = None
            allow_unsafe_fs = False
            allow_data_write = False
        elif sandbox_profile == "data":
            allow_ask = False
            no_wait = True
            allow_save = False
            allow_net = False
            net_http_allow = None
            net_ws_allow = None
            allow_unsafe_fs = False

        cfg = RunConfig(
            seed=seed,
            global_seed=global_seed,
            record_path=record_path,
            replay_path=replay_path,
            engine=str(engine),
            native_allow_fallback=not bool(native_required),
            native_require=bool(native_required),
            allow_ask=allow_ask,
            allow_wait=not no_wait,
            allow_storage=allow_storage,
            allow_save=allow_save,
            storage_dir=storage_dir,
            allow_unsafe_fs=bool(allow_unsafe_fs),
            project_mode=project_mode,
            project_root=str(project_root) if project_mode and project_root else None,
            sandbox_root=str(sandbox_root) if sandbox_root else None,
            fs_read_allow=fs_read_allow,
            fs_write_allow=fs_write_allow,
            allow_net=allow_net,
            net_http_allow=net_http_allow,
            net_ws_allow=net_ws_allow,
            net_max_bytes=net_max_bytes,
            net_timeout_s=net_timeout_s,
            interop_allow=interop_allow,
            save_slots_max=save_slots_max,
            save_bytes_max=save_bytes_max,
            max_steps=max_steps,
            max_ms=max_ms,
            syscall_budget=syscall_budget,
            data_max_batch_size=data_max_batch_size,
            data_max_open_streams=data_max_open_streams,
            data_max_record_bytes=data_max_record_bytes,
            data_max_query_rows=data_max_query_rows,
            allow_data_write=allow_data_write,
            profile=profile,
            trace=trace,
            step=step,
            break_lines=break_lines,
            watch=watch,
            ai_timeline=ai_timeline,
        )

        result = vm.run(program, config=cfg)
        if json_out:
            _json_print({"ok": True, "result": result})
        return 0
    except Exception as e:
        if json_out:
            _json_print({"ok": False, "error": str(e)})
        else:
            _print_pretty_error(e, filename=str(p), source_lines=src.splitlines(True), use_color=use_color)
        return 1

def _iter_test_files(root: Path, pattern: str) -> list[Path]:
    if root.is_file():
        return [root]
    out: list[Path] = []
    for p in sorted(root.rglob(pattern)):
        if p.is_file():
            out.append(p)
    return out

def _run_one_script(path: Path, *, engine: str, native_required: bool = False) -> dict[str, Any]:
    import io
    import contextlib

    src = _read_text(path)
    comp = Compiler()
    program = comp.compile(src, filename=str(path))
    vm = MellowVM()
    cfg = RunConfig(
        engine=engine,
        native_allow_fallback=not bool(native_required),
        native_require=bool(native_required),
    )

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            result = vm.run(program, config=cfg)
        return {"ok": True, "stdout": buf_out.getvalue(), "stderr": buf_err.getvalue(), "result": result}
    except Exception as e:
        return {"ok": False, "stdout": buf_out.getvalue(), "stderr": buf_err.getvalue(), "error": str(e), "type": e.__class__.__name__}


def _golden_output_for(path: Path) -> str | None:
    candidates = [
        path.with_suffix(path.suffix + ".out"),
        path.with_suffix(".out"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return None


def _cmd_test(path: str, *, engine: str, pattern: str, json_out: bool, native_required: bool = False) -> int:
    root = Path(path)
    files = _iter_test_files(root, pattern)
    if not files:
        if json_out:
            _json_print({"ok": False, "error": f"no test files found in {root} (pattern={pattern})"})
        else:
            print(f"no test files found in {root} (pattern={pattern})")
        return 2

    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    def compare(a: dict[str, Any], b: dict[str, Any]) -> tuple[bool, str]:
        keys = ("ok", "stdout", "stderr")
        for k in keys:
            if a.get(k) != b.get(k):
                return False, f"{k} mismatch"
        if a.get("ok"):
            if a.get("result") != b.get("result"):
                return False, "result mismatch"
        else:
            if a.get("error") != b.get("error"):
                return False, "error mismatch"
        return True, "ok"

    for f in files:
        golden = _golden_output_for(f)
        if engine == "dual":
            r_py = _run_one_script(f, engine="py")
            r_c = _run_one_script(f, engine="c", native_required=native_required)
            same, why = compare(r_py, r_c)
            ok = same
            if ok and golden is not None and r_py.get("stdout") != golden:
                ok = False
                why = "golden stdout mismatch"
            rec = {"file": str(f), "ok": ok, "why": why, "py": r_py, "c": r_c}
            if golden is not None:
                rec["golden"] = str(f.with_suffix(f.suffix + ".out") if f.with_suffix(f.suffix + ".out").exists() else f.with_suffix(".out"))
        else:
            r = _run_one_script(f, engine=engine, native_required=(native_required and engine == "c"))
            ok = bool(r.get("ok"))
            why = "ok"
            if ok and golden is not None and r.get("stdout") != golden:
                ok = False
                why = "golden stdout mismatch"
            rec = {"file": str(f), "ok": ok, "why": why, "run": r}
            if golden is not None:
                rec["golden"] = str(f.with_suffix(f.suffix + ".out") if f.with_suffix(f.suffix + ".out").exists() else f.with_suffix(".out"))
        results.append(rec)
        if ok:
            passed += 1
            if not json_out:
                print(f"[PASS] {f}")
        else:
            failed += 1
            if not json_out:
                print(f"[FAIL] {f}")
                if engine == "dual":
                    print(f"  reason: {rec.get('why')}")
                    print(f"  py: {rec['py'].get('error') or rec['py'].get('result')}")
                    print(f"  c : {rec['c'].get('error') or rec['c'].get('result')}")
                else:
                    print(f"  reason: {rec.get('why')}")
                    if rec['run'].get('error'):
                        print(f"  {rec['run'].get('error')}")
    out = {"ok": failed == 0, "passed": passed, "failed": failed, "results": results}
    if json_out:
        _json_print(out)
    return 0 if failed == 0 else 1

def _cmd_replay(file: str, *, replay_path: str, engine: str, json_out: bool) -> int:
    return _cmd_run(
        file,
        json_out=json_out,
        engine=engine,
        record_path=None,
        replay_path=replay_path,
        seed=None,
        global_seed=None,
        allow_ask=False,
        no_wait=False,
        allow_storage=True,
        storage_dir=None,
        allow_unsafe_fs=False,
        max_steps=None,
        max_ms=None,
        syscall_budget=None,
        profile=False,
        trace=False,
        step=False,
        break_lines=None,
        watch=None,
        ai_timeline=None,
        color=False,
        no_color=False,
        registry=None,
        no_resolve=False,
        sandbox_profile="default",
        allow_data_write=False,
        data_max_batch_size=None,
        data_max_query_rows=None,
        data_max_record_bytes=None,
        data_max_open_streams=None,
        native_required=False,
    )


def _cmd_record(
    file: str,
    *,
    record_path: str,
    engine: str,
    seed: int | None,
    global_seed: int | None,
    json_out: bool,
) -> int:
    return _cmd_run(
        file,
        json_out=json_out,
        engine=engine,
        record_path=record_path,
        replay_path=None,
        seed=seed,
        global_seed=global_seed,
        allow_ask=False,
        no_wait=False,
        allow_storage=True,
        storage_dir=None,
        allow_unsafe_fs=False,
        max_steps=None,
        max_ms=None,
        syscall_budget=None,
        profile=False,
        trace=False,
        step=False,
        break_lines=None,
        watch=None,
        ai_timeline=None,
        color=False,
        no_color=False,
        registry=None,
        no_resolve=False,
        sandbox_profile="default",
        allow_data_write=False,
        data_max_batch_size=None,
        data_max_query_rows=None,
        data_max_record_bytes=None,
        data_max_open_streams=None,
        native_required=False,
    )


def _cmd_diff(a: str, b: str, *, json_out: bool) -> int:
    import json
    def load(path: str) -> list[dict[str, Any]]:
        out = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
    la = load(a)
    lb = load(b)
    n = min(len(la), len(lb))
    first = None
    for i in range(n):
        if la[i] != lb[i]:
            first = {"index": i, "a": la[i], "b": lb[i]}
            break
    if first is None and len(la) != len(lb):
        first = {"index": n, "a": la[n] if len(la) > n else None, "b": lb[n] if len(lb) > n else None, "note": "length mismatch"}
    ok = first is None
    out = {"ok": ok, "first_diff": first, "len_a": len(la), "len_b": len(lb)}
    if json_out:
        _json_print(out)
    else:
        if ok:
            print("logs are identical")
        else:
            print(f"first difference at index {first['index']}")
    return 0 if ok else 1


# ----------------------------
# Main
# ----------------------------

def _load_rag_index(rag_file: str | None) -> SimpleRAGIndex:
    texts = [
        "Mellow 1.7 ships an AI-native agent runtime with tools, memory, workflows, and retrieval.",
        "Structured output lets agents return machine-readable objects for apps and automation.",
        "Policies gate tool usage and observability logs capture every major decision.",
        "Model abstraction keeps the runtime provider-agnostic so local or hosted adapters can fit later.",
    ]
    if rag_file and Path(rag_file).exists():
        raw = Path(rag_file).read_text(encoding='utf-8', errors='replace')
        extra = [part.strip() for part in raw.splitlines() if part.strip()]
        if extra:
            texts.extend(extra)
    return SimpleRAGIndex.from_texts(texts)



def _make_agent_runtime(model_name: str, memory_path: str, obs_path: str, allow_tools: list[str] | None = None, deny_tools: list[str] | None = None, rag_file: str | None = None, tool_manifest: str | None = None, *, sandbox: bool = False, allow_caps: list[str] | None = None, deny_caps: list[str] | None = None, secrets: list[str] | None = None, secret_scopes: dict[str, list[str]] | None = None, signed_policy: dict[str, Any] | None = None) -> AgentRuntime:
    tools = builtin_tool_registry()
    if tool_manifest and Path(tool_manifest).exists():
        tools = apply_tool_manifest(tools, load_tool_manifest(tool_manifest))
    sandbox_cfg = SandboxConfig.from_flags(enabled=sandbox, allowed_secrets=secrets or [])
    return AgentRuntime(
        model=resolve_model_adapter(model_name),
        memory=MemoryStore(memory_path),
        tools=tools,
        policy=PolicyEngine(allowed_tools=allow_tools or [], denied_tools=deny_tools or [], allowed_capabilities=allow_caps or [], denied_capabilities=deny_caps or [], sandbox=sandbox_cfg, signed_policy=signed_policy),
        rag=_load_rag_index(rag_file),
        obs=ObservationLog(obs_path),
        sandbox=sandbox_cfg,
        secret_names=secrets or [],
        secret_scopes=secret_scopes or {},
    )


def _agent_prompt_context(task: str, runtime: AgentRuntime, package_name: str | None = None) -> dict[str, Any]:
    context = runtime.build_context(task)
    context.update({
        'task': task,
        'package_name': package_name or 'adhoc.agent',
        'tools': runtime.tools.describe(),
    })
    return context


def _run_agent_package(package_dir: str, task: str, *, json_out: bool, sandbox: bool = False, allow_caps: list[str] | None = None, deny_caps: list[str] | None = None, secrets: list[str] | None = None, timeout_ms: int | None = None, debug: bool = False, policy_file: str | None = None, policy_key: str | None = None) -> int:
    package_dir = _resolve_agent_package_ref(package_dir)
    package = load_agent_package(package_dir)
    signed_policy = None
    effective_policy_file = policy_file or (str((package.root / package.policy_file).resolve()) if package.policy_file else None)
    if effective_policy_file and Path(effective_policy_file).exists():
        signed_policy = load_signed_policy(effective_policy_file, verify_key=policy_key) if policy_key else load_signed_policy(effective_policy_file)
    effective_allow = list(dict.fromkeys((allow_caps or []) + list(package.capabilities_allow)))
    effective_deny = list(dict.fromkeys((deny_caps or []) + list(package.capabilities_deny)))
    effective_secrets = list(dict.fromkeys((secrets or []) + list(package.required_secrets)))
    runtime = _make_agent_runtime(package.model, str((package.root / package.memory_path).resolve()), str((package.root / package.obs_path).resolve()), rag_file=None, tool_manifest=str(package.tool_manifest_path()) if package.tool_manifest_path() else None, sandbox=sandbox, allow_caps=effective_allow, deny_caps=effective_deny, secrets=effective_secrets, secret_scopes=package.secret_scopes, signed_policy=signed_policy)
    prompt = render_prompt_file(package.prompt_path(), _agent_prompt_context(task, runtime, package.name))
    result = runtime.run(task, structured_mode='auto', prompt_text=prompt, timeout_ms=timeout_ms, debug=debug)
    payload = {
        'ok': True,
        'package': package.name,
        'version': package.version,
        'task': task,
        'prompt': prompt,
        'answer': result.answer,
        'structured': result.structured,
        'tool_calls': result.tool_calls,
        'required_secrets': package.required_secrets,
        'secret_scopes': package.secret_scopes,
        'policy_file': effective_policy_file,
    }
    if json_out:
        _json_print(payload)
    else:
        _cli_line(f'Agent package executed: {package.name}', kind='ok')
        print(f'Package         : {package.name}@{package.version}')
        print(f'Prompt file     : {package.prompt_file}')
        print(f'Policy file     : {effective_policy_file or "-"}')
        print(f'Answer          : {result.answer}')
        print(f'Tool calls      : {len(result.tool_calls)}')
    return 0


def _cmd_agent_run(task: str, model: str, memory_path: str, obs_path: str, tools: list[str], allow_tools: list[str], deny_tools: list[str], rag_file: str | None, prompt_file: str | None = None, tool_manifest: str | None = None, package: str | None = None, structured: str = 'auto', json_out: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, deny_caps: list[str] | None = None, secrets: list[str] | None = None, timeout_ms: int | None = None, debug: bool = False, policy_file: str | None = None, policy_key: str | None = None) -> int:
    if prompt_file in {'auto', 'text'} and isinstance(tool_manifest, bool) and package is None and structured == 'auto' and json_out is False:
        structured = str(prompt_file)
        json_out = bool(tool_manifest)
        prompt_file = None
        tool_manifest = None
    if package:
        return _run_agent_package(package, task, json_out=json_out, sandbox=sandbox, allow_caps=allow_caps, deny_caps=deny_caps, secrets=secrets, timeout_ms=timeout_ms, debug=debug, policy_file=policy_file, policy_key=policy_key)
    signed_policy = None
    if policy_file and Path(policy_file).exists():
        signed_policy = load_signed_policy(policy_file, verify_key=policy_key) if policy_key else load_signed_policy(policy_file)
    effective_allow_tools = list(dict.fromkeys((allow_tools or []) + (tools or [])))
    runtime = _make_agent_runtime(model, memory_path, obs_path, effective_allow_tools, deny_tools, rag_file, tool_manifest, sandbox=sandbox, allow_caps=allow_caps, deny_caps=deny_caps, secrets=secrets, signed_policy=signed_policy)
    auto_tool = tools[0] if tools else None
    prompt = render_prompt_file(prompt_file, _agent_prompt_context(task, runtime)) if prompt_file else None
    try:
        result = runtime.run(task, structured_mode=structured, auto_tool=auto_tool, prompt_text=prompt, timeout_ms=timeout_ms, debug=debug)
    except Exception as e:
        if json_out:
            _json_print({'ok': False, 'error': str(e)})
        else:
            _cli_line(f'agent run failed: {e}', kind='error', file=sys.stderr)
        return 1
    payload = {
        'ok': True,
        'task': result.task,
        'answer': result.answer,
        'structured': result.structured,
        'memory_hits': result.memory_hits,
        'tool_calls': result.tool_calls,
        'rag_hits': result.rag_hits,
        'observations': result.observations,
        'prompt': prompt,
        'tool_manifest': tool_manifest,
        'debug': result.debug,
        'policy_file': policy_file,
    }
    if json_out:
        _json_print(payload)
    else:
        _cli_line('Mellow 1.8.1 Hosted Agent Platform run', kind='ok')
        print(f'Model           : {model}')
        print(f'Task            : {task}')
        if prompt:
            print(f'Prompt DSL      : {prompt_file}')
        if tool_manifest:
            print(f'Tool manifest   : {tool_manifest}')
        if policy_file:
            print(f'Policy file     : {policy_file}')
        print(f'Answer          : {result.answer}')
        print('Structured      : ' + json.dumps(result.structured, ensure_ascii=False))
        print(f'Memory hits     : {len(result.memory_hits)}')
        print(f'RAG hits        : {len(result.rag_hits)}')
        print(f'Tool calls      : {len(result.tool_calls)}')
        print(f'Observability   : {obs_path}')
        print(f"Run ID          : {result.debug.get('run_id')}")
        if debug:
            print('Debug           : ' + json.dumps(result.debug, ensure_ascii=False))
    return 0


def _cmd_agent_workflow(task: str, model: str, memory_path: str, obs_path: str, rag_file: str | None, package: str | None = None, json_out: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, deny_caps: list[str] | None = None, secrets: list[str] | None = None, retries: int = 1, timeout_ms: int = 2000, parallel: bool = False, debug: bool = False, policy_file: str | None = None, policy_key: str | None = None) -> int:
    if isinstance(package, bool) and json_out is False:
        json_out = package
        package = None
    if package:
        return _run_agent_package(package, task, json_out=json_out, sandbox=sandbox, allow_caps=allow_caps, deny_caps=deny_caps, secrets=secrets, timeout_ms=timeout_ms, debug=debug, policy_file=policy_file, policy_key=policy_key)
    signed_policy = None
    if policy_file and Path(policy_file).exists():
        signed_policy = load_signed_policy(policy_file, verify_key=policy_key) if policy_key else load_signed_policy(policy_file)
    runtime = _make_agent_runtime(model, memory_path, obs_path, ['search.docs', 'time.now'], [], rag_file, sandbox=sandbox, allow_caps=allow_caps, deny_caps=deny_caps, secrets=secrets, signed_policy=signed_policy)
    steps = [
        WorkflowStep('recall-memory', 'memory', retries=retries, timeout_ms=timeout_ms),
        WorkflowStep('retrieve-context', 'rag', retries=retries, timeout_ms=timeout_ms),
    ]
    if parallel:
        steps.append(WorkflowStep('parallel-context', 'parallel', {'steps': [
            {'name': 'search-docs', 'kind': 'tool', 'payload': {'tool': 'search.docs', 'input': {'query': task}}, 'retries': retries, 'timeout_ms': timeout_ms},
            {'name': 'stamp-time', 'kind': 'tool', 'payload': {'tool': 'time.now', 'input': {}}, 'retries': retries, 'timeout_ms': timeout_ms},
        ]}, retries=retries, timeout_ms=timeout_ms))
    else:
        steps.extend([
            WorkflowStep('search-docs', 'tool', {'tool': 'search.docs', 'input': {'query': task}}, retries=retries, timeout_ms=timeout_ms),
            WorkflowStep('stamp-time', 'tool', {'tool': 'time.now', 'input': {}}, retries=retries, timeout_ms=timeout_ms),
        ])
    steps.append(WorkflowStep('generate-answer', 'model', retries=retries, timeout_ms=timeout_ms))
    wf = Workflow(name='default-agent-workflow', steps=steps)
    runner = WorkflowRunner(runtime)
    result = runner.run(wf, task)
    if json_out:
        _json_print({'ok': True, **result, 'debug': runtime.obs.summary(), 'policy_file': policy_file})
    else:
        _cli_line('Mellow workflow executed', kind='ok')
        print(f'Workflow        : {result["workflow"]}')
        if policy_file:
            print(f'Policy file     : {policy_file}')
        for step in result['steps']:
            print(f"- {step['step']} [{step['kind']}] -> {json.dumps(step, ensure_ascii=False)}")
        if debug:
            print('Debug           : ' + json.dumps(runtime.obs.summary(), ensure_ascii=False))
    return 0


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




def _print_graph(node: dict[str, Any], indent: int = 0) -> None:
    prefix = '  ' * indent + '- '
    label = f"{node.get('name')}@{node.get('version', '?')}"
    if node.get('constraint'):
        label += f" ({node['constraint']})"
    if node.get('error'):
        label += f" ERROR={node['error']}"
    if node.get('cycle'):
        label += ' [cycle]'
    print(prefix + label)
    for child in node.get('dependencies') or []:
        _print_graph(child, indent + 1)


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


def _resolve_agent_package_ref(package_or_dir: str) -> str:
    p = Path(package_or_dir)
    if p.exists():
        return str(p)
    installed = load_installed_agent(package_or_dir)
    if installed:
        return str(installed.root)
    return package_or_dir


def _cmd_agent_prompt(path: str, task: str, json_out: bool) -> int:
    runtime = _make_agent_runtime('rule-based', '.mellow/agent_memory.jsonl', '.mellow/agent_observability.jsonl')
    rendered = render_prompt_file(path, _agent_prompt_context(task, runtime))
    if json_out:
        _json_print({'ok': True, 'path': path, 'task': task, 'rendered': rendered})
    else:
        print(rendered)
    return 0


def _cmd_agent_trace(path: str, json_out: bool) -> int:
    events = read_observation_file(path)
    summary = {'count': len(events), 'kinds': {}, 'run_ids': sorted({e.get('run_id') for e in events if e.get('run_id')})}
    for evt in events:
        kind = str(evt.get('kind', 'unknown'))
        summary['kinds'][kind] = summary['kinds'].get(kind, 0) + 1
    if json_out:
        _json_print({'ok': True, 'summary': summary, 'events': events[-20:]})
    else:
        _cli_line(f"Trace loaded: {len(events)} event(s)", kind='ok')
        print('Kinds           : ' + json.dumps(summary['kinds'], ensure_ascii=False))
        if summary['run_ids']:
            print('Run IDs         : ' + ', '.join(summary['run_ids']))
    return 0


def _cmd_agent_preview(ref: str, json_out: bool) -> int:
    pkg = load_agent_package(_resolve_agent_package_ref(ref))
    payload = {
        'ok': True,
        'name': pkg.name,
        'version': pkg.version,
        'model': pkg.model,
        'prompt_file': pkg.prompt_file,
        'tool_manifest': pkg.tool_manifest,
        'tags': pkg.tags,
        'dependencies': pkg.dependencies,
    }
    if json_out:
        _json_print(payload)
    else:
        _cli_line(f"Agent preview: {pkg.name}", kind='ok')
        for key, value in payload.items():
            if key != 'ok':
                print(f"{key:15}: {json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}")
    return 0


def _cmd_agent_prompt_debug(path: str, task: str, json_out: bool) -> int:
    runtime = _make_agent_runtime('rule-based', '.mellow/agent_memory.jsonl', '.mellow/agent_observability.jsonl')
    context = _agent_prompt_context(task, runtime)
    rendered = render_prompt_file(path, context)
    payload = {'ok': True, 'path': path, 'task': task, 'variables': sorted(context.keys()), 'rendered': rendered}
    if json_out:
        _json_print(payload)
    else:
        _cli_line('Prompt debug', kind='ok')
        print('Variables       : ' + ', '.join(payload['variables']))
        print(rendered)
    return 0


def _cmd_playground(host: str, port: int, build_only: bool, out: str, json_out: bool) -> int:
    target = build_static_playground(out)
    payload = {
        "ok": True,
        "path": str(target.resolve()),
        "url": None if build_only else f"http://{host}:{port}/",
        "served": not build_only,
        "host": host,
        "port": int(port),
    }
    if build_only:
        if json_out:
            _json_print(payload)
        else:
            _cli_line(f"Playground assets written to {target}", kind="ok")
        return 0

    server = serve_playground(host=host, port=port)
    if json_out:
        _json_print(payload)
        return 0
    _cli_line(f"Mellow Playground serving at {payload['url']}", kind='ok')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _cmd_agent_playground(out: str, serve: bool, port: int, json_out: bool) -> int:
    build_only = not bool(serve)
    return _cmd_playground("127.0.0.1", port, build_only, str(Path(out).parent), json_out)


def _cmd_agent_serve(package: str | None, host: str, port: int, json_out: bool, deployment_manifest: str | None = None) -> int:
    manifest = load_deployment_manifest(deployment_manifest) if deployment_manifest else None
    effective_host = str((manifest or {}).get('runtime', {}).get('host', host))
    effective_port = int((manifest or {}).get('runtime', {}).get('port', port))
    effective_package = package
    if manifest and not effective_package:
        candidate = (Path(deployment_manifest).parent / 'package').resolve()
        if candidate.exists():
            effective_package = str(candidate)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            health_path = str((manifest or {}).get('runtime', {}).get('healthcheck', 'GET /health')).split(' ', 1)[-1]
            if self.path == health_path:
                body = json.dumps({'ok': True, 'provider': (manifest or {}).get('runtime', {}).get('provider', 'local-http')}).encode('utf-8')
                self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404); self.end_headers()

        def do_POST(self):
            run_path = str((manifest or {}).get('runtime', {}).get('entrypoint', 'POST /run')).split(' ', 1)[-1]
            if self.path != run_path:
                self.send_response(404); self.end_headers(); return
            length = int(self.headers.get('Content-Length', '0') or '0')
            raw = self.rfile.read(length) if length else b'{}'
            try:
                data = json.loads(raw.decode('utf-8'))
            except Exception:
                data = {}
            task = str(data.get('task', 'demo task'))
            if effective_package:
                payload = {'ok': _run_agent_package(effective_package, task, json_out=True) == 0, 'task': task, 'deployment_manifest': deployment_manifest}
            else:
                runtime = _make_agent_runtime('rule-based', '.mellow/agent_memory.jsonl', '.mellow/agent_observability.jsonl')
                res = runtime.run(task)
                payload = {'ok': True, 'task': task, 'answer': res.answer, 'deployment_manifest': deployment_manifest}
            body = json.dumps(payload).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            return

    if json_out:
        _json_print({'ok': True, 'host': effective_host, 'port': effective_port, 'package': effective_package, 'deployment_manifest': deployment_manifest})
        return 0
    _cli_line(f'Hosted agent server listening on http://{effective_host}:{effective_port}', kind='ok')
    server = ThreadingHTTPServer((effective_host, effective_port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _cmd_agent_marketplace(query: str, online: bool, registry: str | None, json_out: bool) -> int:
    res = search_agent_remote(query, registry=registry) if online else search_agent_local(query)
    payload = {'ok': True, 'query': query, 'items': list(res.get('items') or []), 'source': 'remote' if online else 'local'}
    if json_out:
        _json_print(payload)
    else:
        _cli_line(f"Marketplace results ({payload['source']})", kind='ok')
        for item in payload['items']:
            print(f"- {item.get('name')}@{item.get('version', '?')} :: model={item.get('model', 'rule-based')} tags={','.join(item.get('tags') or [])}")
    return 0


def _cmd_agent_deploy(ref: str, out: str, json_out: bool, public_url: str | None = None, host: str | None = None, port: int | None = None, target: str | None = None, control_plane: str | None = None) -> int:
    pkg_root = _resolve_agent_package_ref(ref)
    pkg = load_agent_package(pkg_root)
    out_dir = Path(out) / pkg.name.replace('.', '_')
    bundle = write_deployment_bundle(pkg_root, out_dir, public_url=public_url, host=host, port=port, target=target, control_plane=control_plane)
    reg = sync_deployment(bundle['manifest'], out_dir, control_plane=control_plane, manifest_path=bundle['manifest_path']) if control_plane else register_deployment(bundle['manifest'], out_dir, manifest_path=bundle['manifest_path'])
    payload = {'ok': True, 'out_dir': str(out_dir.resolve()), 'manifest': bundle['manifest'], 'manifest_path': bundle['manifest_path'], 'start_script': bundle['start_script'], 'adapters': bundle.get('adapters', {}), 'deployment': reg.get('deployment'), 'revision': reg.get('revision'), 'remote': reg.get('remote', False)}
    if json_out:
        _json_print(payload)
    else:
        _cli_line(f"Deployment bundle written to {out_dir}", kind='ok')
        print(f"Manifest        : {bundle['manifest_path']}")
        print(f"Start script    : {bundle['start_script']}")
        print(f"Target          : {bundle['manifest']['runtime']['provider']}")
        if bundle.get('adapters'):
            print(f"Adapters        : {json.dumps(bundle['adapters'], ensure_ascii=False)}")
        if reg.get('deployment'):
            print(f"Deployment ID   : {reg['deployment']['id']}")
        if reg.get('revision'):
            print(f"Revision        : {reg['revision']['revision']}")
        if reg.get('remote'):
            print('Control plane   : remote sync completed')
    return 0


def _cmd_agent_control_plane(action: str, ref: str | None, manifest: str | None, bundle_dir: str, control_plane: str | None, json_out: bool, token: str | None = None, revision: int | None = None, revision_notes: str | None = None, canary_percent: int | None = None, stable_percent: int | None = None, canary_split: int | None = None, rules_file: str | None = None, metrics: dict[str, Any] | None = None) -> int:
    if action == 'register' and manifest:
        payload = register_deployment(load_deployment_manifest(manifest), bundle_dir, control_plane=control_plane, manifest_path=manifest, revision_notes=revision_notes)
    elif action == 'sync' and manifest:
        payload = sync_deployment(load_deployment_manifest(manifest), bundle_dir, control_plane=control_plane, api_token=token, manifest_path=manifest, revision_notes=revision_notes)
    elif action == 'status' and ref:
        payload = get_deployment_status(ref, control_plane=control_plane, api_token=token)
    elif action == 'revisions' and ref:
        payload = list_revisions(ref, control_plane=control_plane, api_token=token)
    elif action == 'rollout' and ref and revision is not None:
        payload = rollout_revision(ref, revision, control_plane=control_plane, api_token=token, canary_percent=canary_percent)
    elif action == 'health' and ref:
        payload = run_health_check(ref, control_plane=control_plane, api_token=token)
    elif action == 'traffic' and ref and stable_percent is not None and canary_split is not None:
        payload = update_traffic_split(ref, stable_percent, canary_split, control_plane=control_plane, api_token=token)
    elif action == 'rollback' and ref:
        payload = rollback_deployment(ref, control_plane=control_plane, api_token=token, revision=revision)
    elif action == 'metrics' and ref:
        clean_metrics = {k: v for k, v in (metrics or {}).items() if v is not None}
        payload = record_deployment_metrics(ref, clean_metrics, control_plane=control_plane, api_token=token) if clean_metrics else get_deployment_metrics(ref, control_plane=control_plane, api_token=token)
    elif action == 'signals' and ref:
        payload = get_autoscaling_signals(ref, control_plane=control_plane, api_token=token)
    elif action == 'alert-rules' and ref:
        if rules_file:
            raw = json.loads(Path(rules_file).read_text(encoding='utf-8'))
            rules = raw.get('rules') if isinstance(raw, dict) else raw
            payload = set_alert_rules(ref, list(rules or []), control_plane=control_plane, api_token=token)
        else:
            status = get_deployment_status(ref, control_plane=control_plane, api_token=token)
            if status.get('ok'):
                dep = status['deployment']
                payload = {'ok': True, 'deployment': dep, 'rules': list(dep.get('alert_rules') or []), 'alerts': dep.get('alerts') or {'status': 'ok', 'count': 0}}
            else:
                payload = status
    elif action == 'alerts' and ref:
        payload = evaluate_alerts(ref, control_plane=control_plane, api_token=token)
    else:
        payload = list_deployments(control_plane=control_plane, api_token=token)
    if json_out:
        _json_print(payload)
    else:
        if action == 'status' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Hosted deployment: {dep['id']}", kind='ok')
            print(f"Package         : {dep['package']['name']}@{dep['package']['version']}")
            print(f"Provider        : {dep['provider']}")
            print(f"Status          : {dep['status']}")
            print(f"Current rev     : {dep.get('current_revision')}")
            print(f"Latest rev      : {dep.get('latest_revision')}")
            if dep.get('traffic_split'):
                print(f"Traffic split   : {json.dumps(dep.get('traffic_split'), ensure_ascii=False)}")
            if dep.get('health'):
                print(f"Health          : {json.dumps(dep.get('health'), ensure_ascii=False)}")
            print(f"Bundle dir      : {dep['bundle_dir']}")
        elif action == 'revisions' and payload.get('ok'):
            _cli_line(f"Revisions: {payload.get('count', 0)}", kind='ok')
            if payload.get('traffic_split'):
                print('Traffic split   : ' + json.dumps(payload.get('traffic_split'), ensure_ascii=False))
            for item in payload.get('items') or []:
                marker = '*' if int(item.get('revision', 0)) == int(payload.get('current_revision') or 0) else ' '
                print(f"{marker} rev {item['revision']} :: status={item.get('status')} created={item.get('created_at')} notes={item.get('notes') or ''}")
        elif action == 'health' and payload.get('ok'):
            _cli_line(f"Health check ok for {payload['deployment']['package']['name']}", kind='ok')
            print('Health          : ' + json.dumps(payload.get('health'), ensure_ascii=False))
        elif action == 'traffic' and payload.get('ok'):
            _cli_line(f"Traffic updated for {payload['deployment']['package']['name']}", kind='ok')
            print('Traffic split   : ' + json.dumps(payload.get('traffic_split'), ensure_ascii=False))
        elif action == 'rollout' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Rolled out revision {payload['revision']['revision']} for {dep['package']['name']}", kind='ok')
            print(f"Deployment ID   : {dep['id']}")
            print(f"Current rev     : {dep.get('current_revision')}")
            print(f"Status          : {dep.get('status')}")
            if dep.get('traffic_split'):
                print('Traffic split   : ' + json.dumps(dep.get('traffic_split'), ensure_ascii=False))
        elif action == 'rollback' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Rolled back deployment {dep['package']['name']}", kind='ok')
            print(f"Deployment ID   : {dep['id']}")
            print(f"Current rev     : {dep.get('current_revision')}")
            print(f"Status          : {dep.get('status')}")
        elif action == 'metrics' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Metrics for {dep['package']['name']}", kind='ok')
            print('Metrics         : ' + json.dumps(payload.get('metrics'), ensure_ascii=False))
            if payload.get('autoscaling'):
                print('Autoscaling     : ' + json.dumps(payload.get('autoscaling'), ensure_ascii=False))
            if payload.get('alerts'):
                print('Alerts          : ' + json.dumps(payload.get('alerts'), ensure_ascii=False))
        elif action == 'signals' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Autoscaling signals for {dep['package']['name']}", kind='ok')
            print('Signals         : ' + json.dumps(payload.get('autoscaling'), ensure_ascii=False))
        elif action == 'alert-rules' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Alert rules for {dep['package']['name']}", kind='ok')
            print('Rules           : ' + json.dumps(payload.get('rules') or [], ensure_ascii=False))
            print('Alerts          : ' + json.dumps(payload.get('alerts') or {'status': 'ok', 'count': 0}, ensure_ascii=False))
        elif action == 'alerts' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Alert evaluation for {dep['package']['name']}", kind='ok')
            print('Alerts          : ' + json.dumps(payload.get('alerts'), ensure_ascii=False))
            if payload.get('rules') is not None:
                print('Rules           : ' + json.dumps(payload.get('rules'), ensure_ascii=False))
        elif action in ('status','revisions','rollout','health','traffic','rollback','metrics','signals','alert-rules','alerts'):
            _cli_line(payload.get('error', f'{action} failed'), kind='error', file=sys.stderr)
        else:
            items = payload.get('items') or ([payload.get('deployment')] if payload.get('deployment') else [])
            _cli_line(f"Hosted deployments: {len(items)}", kind='ok')
            for item in items:
                print(f"- {item['id']} :: {item['package']['name']}@{item['package']['version']} [{item['provider']}] status={item['status']} current_rev={item.get('current_revision')}")
    return 0 if payload.get('ok') else 1


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


def _cmd_agent_demo(json_out: bool) -> int:
    payload = {
        'version': '1.8.5',
        'focus': {
            'hosted_runtime': 5,
            'deployment_targets': 5,
            'deployment_manifests': 5,
            'remote_control_plane': 5,
            'deployment_health_checks': 5,
            'traffic_split_rollouts': 5,
            'rollback_management': 5,
            'secret_scopes': 5,
            'signed_capability_policies': 5,
            'observability': 4,
            'developer_platform': 4,
        },
        'commands': [
            'mellow agent deploy my.agent --target docker --public-url https://example.com',
            'mellow agent serve --package my.agent --deployment-manifest .mellow/deploy/my_agent/deployment.json',
            'mellow agent secret set OPENAI_API_KEY sk-demo --scope agent.run --scope tool.search.docs',
            'mellow agent run --task "..." --policy-file policies/capabilities.json --policy-key secret',
        ],
    }
    if json_out:
        _json_print(payload)
    else:
        _cli_line('Mellow 1.8.5 Deployment Metrics Platform', kind='ok')
        for key, stars in payload['focus'].items():
            print(f"- {key:26} : {'⭐' * stars}")
        print('Commands:')
        for cmd in payload['commands']:
            print(f'  {cmd}')
    return 0


def _cmd_agent_policy_sign(path: str, key: str, signer: str | None, json_out: bool) -> int:
    p = Path(path)
    payload = sign_capability_policy(json.loads(p.read_text(encoding='utf-8')), key, signer=signer)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
    res = {'ok': True, 'path': str(p), 'signed_by': signer}
    if json_out:
        _json_print(res)
    else:
        _cli_line(f'Capability policy signed: {p}', kind='ok')
    return 0


def _cmd_agent_policy_verify(path: str, key: str, json_out: bool) -> int:
    try:
        payload = load_signed_policy(path, verify_key=key)
        res = {'ok': True, 'path': str(path), 'signed_by': payload.get('signed_by')}
    except Exception as e:
        res = {'ok': False, 'path': str(path), 'error': str(e)}
    if json_out:
        _json_print(res)
    else:
        if res.get('ok'):
            _cli_line(f'Capability policy verified: {path}', kind='ok')
        else:
            _cli_line(f"Capability policy verify failed: {res.get('error')}", kind='error', file=sys.stderr)
    return 0 if res.get('ok') else 1


def _cmd_agent_inspect_log(path: str, json_out: bool) -> int:
    p = Path(path)
    if not p.exists():
        if json_out:
            _json_print({'ok': False, 'error': f'log not found: {path}'})
        else:
            _cli_line(f'log not found: {path}', kind='error', file=sys.stderr)
        return 2
    events = read_observation_file(path)
    payload = {'ok': True, 'count': len(events), 'events': events[-20:]}
    if json_out:
        _json_print(payload)
    else:
        _cli_line(f'Loaded {len(events)} observability event(s)', kind='ok')
        for evt in events[-10:]:
            print(f"- {evt.get('kind')} :: {json.dumps(evt.get('payload', {}), ensure_ascii=False)}")
    return 0


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    prog = _prog()

    if not argv or argv in (["-h"], ["--help"]):
        print(_quick_help_text(prog))
        return 0

    if argv and argv[0] in CLI_ALIASES:
        argv = [CLI_ALIASES[argv[0]], *argv[1:]]

    if argv and _looks_like_script_path(argv[0]):
        _cli_line("direct script mode has been removed", kind="error", file=sys.stderr)
        _cli_line(f"Use `mellow run {argv[0]}`.", kind="hint", file=sys.stderr)
        return 2

    if argv and argv[0] not in MODERN_CMDS and not argv[0].startswith('-'):
        suggestion = _suggest_command(argv[0])
        if suggestion:
            _cli_line(f"unknown command '{argv[0]}'", kind='error', file=sys.stderr)
            _cli_line(f"Did you mean `mellow {suggestion}`?", kind='hint', file=sys.stderr)
            return 2

    # mode selection
    if argv and argv[0] in MODERN_CMDS:
        p = _build_modern_parser()
        ns = p.parse_args(argv)
        cmd = getattr(ns, "cmd", None)

        # help
        if cmd in (None, "help"):
            if getattr(ns, "full", False):
                p.print_help()
            elif getattr(ns, "topic", None):
                print(_format_guide(ns.topic, _prog()))
            else:
                print(_modern_help_text(_prog()))
            return 0

        # dispatch
        if cmd == "guide":
            return _cmd_guide(getattr(ns, "topic", None), getattr(ns, "json", False), getattr(ns, "list", False))
        if cmd == "ask":
            return _cmd_ask(getattr(ns, "question", []), getattr(ns, "json", False))
        if cmd == "modules":
            return _cmd_modules(ns.json)
        if cmd == "check":
            return _cmd_check(ns.file, ns.json)
        if cmd == "doctor":
            return _cmd_doctor(ns.json, getattr(ns, "strict", False))
        if cmd == "status":
            return _cmd_status(getattr(ns, "json", False), getattr(ns, "strict", False))
        if cmd == "config":
            return _cmd_config(getattr(ns, "config_cmd", None) or "list", getattr(ns, "key", None), getattr(ns, "value", None), getattr(ns, "json", False))
        if cmd == "completion":
            return _cmd_completion(ns.shell)
        if cmd == "bench":
            return _cmd_bench(getattr(ns, "rounds", 5), getattr(ns, "json", False))
        if cmd == "security":
            if getattr(ns, "security_cmd", None) == "audit":
                return _cmd_security_audit(not getattr(ns, "no_packages", False), getattr(ns, "strict", False), getattr(ns, "json", False))
            p.print_help()
            return 2
        if cmd == "release-gate":
            return _cmd_release_gate(getattr(ns, "rounds", 3), getattr(ns, "json", False))
        if cmd == "explain":
            return _cmd_explain(ns.error_id, ns.json)
        if cmd == "assistant":
            return _cmd_assistant(ns.file, ns.mode, ns.json)
        if cmd == "agent":
            if ns.agent_cmd == "run":
                return _cmd_agent_run(ns.task, ns.model, ns.memory, ns.obs, ns.tools, ns.allow_tools, ns.deny_tools, ns.rag_file, getattr(ns, 'prompt_file', None), getattr(ns, 'tool_manifest', None), getattr(ns, 'package', None), ns.structured, ns.json, getattr(ns, 'sandbox', False), getattr(ns, 'allow_caps', []), getattr(ns, 'deny_caps', []), getattr(ns, 'secrets', []), getattr(ns, 'timeout_ms', None), getattr(ns, 'debug', False), getattr(ns, 'policy_file', None), getattr(ns, 'policy_key', None))
            if ns.agent_cmd == "workflow":
                return _cmd_agent_workflow(ns.task, ns.model, ns.memory, ns.obs, ns.rag_file, getattr(ns, 'package', None), ns.json, getattr(ns, 'sandbox', False), getattr(ns, 'allow_caps', []), getattr(ns, 'deny_caps', []), getattr(ns, 'secrets', []), getattr(ns, 'retries', 1), getattr(ns, 'timeout_ms', 2000), getattr(ns, 'parallel', False), getattr(ns, 'debug', False), getattr(ns, 'policy_file', None), getattr(ns, 'policy_key', None))
            if ns.agent_cmd == "demo":
                return _cmd_agent_demo(ns.json)
            if ns.agent_cmd == "inspect-log":
                return _cmd_agent_inspect_log(ns.path, ns.json)
            if ns.agent_cmd == "trace":
                return _cmd_agent_trace(ns.path, ns.json)
            if ns.agent_cmd == "preview":
                return _cmd_agent_preview(ns.ref, ns.json)
            if ns.agent_cmd == "prompt-debug":
                return _cmd_agent_prompt_debug(ns.path, ns.task, ns.json)
            if ns.agent_cmd == "playground":
                return _cmd_agent_playground(ns.out, ns.serve, ns.port, ns.json)
            if ns.agent_cmd == "serve":
                return _cmd_agent_serve(getattr(ns, 'package', None), ns.host, ns.port, ns.json, getattr(ns, 'deployment_manifest', None))
            if ns.agent_cmd == "marketplace":
                return _cmd_agent_marketplace(ns.query, getattr(ns, 'online', False), getattr(ns, 'registry', None), ns.json)
            if ns.agent_cmd == "deploy":
                return _cmd_agent_deploy(ns.ref, ns.out, ns.json, getattr(ns, 'public_url', None), getattr(ns, 'host', None), getattr(ns, 'port', None), getattr(ns, 'target', None), getattr(ns, 'control_plane', None))
            if ns.agent_cmd == "control-plane":
                return _cmd_agent_control_plane(getattr(ns, 'agent_cp_cmd', 'list') or 'list', getattr(ns, 'ref', None), getattr(ns, 'manifest', None), getattr(ns, 'bundle_dir', '.'), getattr(ns, 'control_plane', None), getattr(ns, 'json', False), getattr(ns, 'token', None), getattr(ns, 'revision', None), getattr(ns, 'revision_notes', None), getattr(ns, 'canary_percent', None), getattr(ns, 'stable', None), getattr(ns, 'canary', None), getattr(ns, 'file', None), {'cpu': getattr(ns, 'cpu', None), 'memory': getattr(ns, 'memory', None), 'rps': getattr(ns, 'rps', None), 'p95_ms': getattr(ns, 'p95_ms', None), 'error_rate': getattr(ns, 'error_rate', None), 'replicas': getattr(ns, 'replicas', None), 'queued_requests': getattr(ns, 'queued_requests', None), 'in_flight': getattr(ns, 'in_flight', None)})
            if ns.agent_cmd == "secret":
                return _cmd_agent_secret(getattr(ns, 'agent_secret_cmd', 'list') or 'list', getattr(ns, 'name', None), getattr(ns, 'value', None), getattr(ns, 'json', False), getattr(ns, 'scopes', None), getattr(ns, 'description', None))
            if ns.agent_cmd == "schedule":
                return _cmd_agent_schedule(getattr(ns, 'agent_sched_cmd', 'list') or 'list', name=getattr(ns, 'name', None), cron=getattr(ns, 'cron', None), task=getattr(ns, 'task', None), kind=getattr(ns, 'kind', 'run'), package=getattr(ns, 'package', None), model=getattr(ns, 'model', 'rule-based'), memory=getattr(ns, 'memory', ' .mellow/agent_memory.jsonl').strip(), obs=getattr(ns, 'obs', ' .mellow/agent_observability.jsonl').strip(), rag_file=getattr(ns, 'rag_file', None), retries=getattr(ns, 'retries', 1), timeout_ms=getattr(ns, 'timeout_ms', None), parallel=getattr(ns, 'parallel', False), sandbox=getattr(ns, 'sandbox', False), allow_caps=getattr(ns, 'allow_caps', []), secrets=getattr(ns, 'secrets', []), backoff=_build_backoff(getattr(ns, 'backoff', None), getattr(ns, 'backoff_delay_ms', None), getattr(ns, 'backoff_max_ms', None)), json_out=getattr(ns, 'json', False))
            if ns.agent_cmd == "runner":
                return _cmd_agent_runner(getattr(ns, 'agent_runner_cmd', 'status') or 'status', interval_s=getattr(ns, 'interval_s', 1.0), iterations=getattr(ns, 'iterations', 1), queue_backed=getattr(ns, 'queue_backed', False), queue_limit=getattr(ns, 'queue_limit', None), workers=getattr(ns, 'workers', 1), json_out=getattr(ns, 'json', False))
            if ns.agent_cmd == "trigger":
                return _cmd_agent_trigger(getattr(ns, 'agent_trigger_cmd', 'list') or 'list', name=getattr(ns, 'name', None), event=getattr(ns, 'event', None), task=getattr(ns, 'task', None), kind=getattr(ns, 'kind', 'run'), package=getattr(ns, 'package', None), model=getattr(ns, 'model', 'rule-based'), memory=getattr(ns, 'memory', ' .mellow/agent_memory.jsonl').strip(), obs=getattr(ns, 'obs', ' .mellow/agent_observability.jsonl').strip(), rag_file=getattr(ns, 'rag_file', None), retries=getattr(ns, 'retries', 1), timeout_ms=getattr(ns, 'timeout_ms', None), parallel=getattr(ns, 'parallel', False), sandbox=getattr(ns, 'sandbox', False), allow_caps=getattr(ns, 'allow_caps', []), secrets=getattr(ns, 'secrets', []), filters=getattr(ns, 'filters', []), payload=getattr(ns, 'payload', None), backoff=_build_backoff(getattr(ns, 'backoff', None), getattr(ns, 'backoff_delay_ms', None), getattr(ns, 'backoff_max_ms', None)), json_out=getattr(ns, 'json', False))
            if ns.agent_cmd == "webhook":
                return _cmd_agent_webhook(getattr(ns, 'agent_webhook_cmd', 'list') or 'list', name=getattr(ns, 'name', None), event=getattr(ns, 'event', None), task=getattr(ns, 'task', None), token=getattr(ns, 'token', None), kind=getattr(ns, 'kind', 'run'), package=getattr(ns, 'package', None), model=getattr(ns, 'model', 'rule-based'), memory=getattr(ns, 'memory', ' .mellow/agent_memory.jsonl').strip(), obs=getattr(ns, 'obs', ' .mellow/agent_observability.jsonl').strip(), rag_file=getattr(ns, 'rag_file', None), retries=getattr(ns, 'retries', 1), timeout_ms=getattr(ns, 'timeout_ms', None), parallel=getattr(ns, 'parallel', False), sandbox=getattr(ns, 'sandbox', False), allow_caps=getattr(ns, 'allow_caps', []), secrets=getattr(ns, 'secrets', []), payload=getattr(ns, 'payload', None), host=getattr(ns, 'host', '127.0.0.1'), port=getattr(ns, 'port', 8788), token_header=getattr(ns, 'token_header', 'X-Mellow-Webhook-Token'), enable_job_api=not getattr(ns, 'no_job_api', False), backoff=_build_backoff(getattr(ns, 'backoff', None), getattr(ns, 'backoff_delay_ms', None), getattr(ns, 'backoff_max_ms', None)), json_out=getattr(ns, 'json', False))
            if ns.agent_cmd == "queue":
                return _cmd_agent_queue(getattr(ns, 'agent_queue_cmd', 'list') or 'list', limit=getattr(ns, 'limit', None), item_id=getattr(ns, 'item_id', None), workers=getattr(ns, 'workers', 1), json_out=getattr(ns, 'json', False))
            if ns.agent_cmd == "jobs":
                return _cmd_agent_jobs(getattr(ns, 'agent_jobs_cmd', 'list') or 'list', task=getattr(ns, 'task', None), name=getattr(ns, 'name', None), kind=getattr(ns, 'kind', 'run'), package=getattr(ns, 'package', None), model=getattr(ns, 'model', 'rule-based'), memory=getattr(ns, 'memory', '.mellow/agent_memory.jsonl'), obs=getattr(ns, 'obs', '.mellow/agent_observability.jsonl'), rag_file=getattr(ns, 'rag_file', None), retries=getattr(ns, 'retries', 1), timeout_ms=getattr(ns, 'timeout_ms', None), parallel=getattr(ns, 'parallel', False), sandbox=getattr(ns, 'sandbox', False), allow_caps=getattr(ns, 'allow_caps', []), secrets=getattr(ns, 'secrets', []), payload=getattr(ns, 'payload', None), host=getattr(ns, 'host', '127.0.0.1'), port=getattr(ns, 'port', 8788), job_id=getattr(ns, 'job_id', None), backoff=_build_backoff(getattr(ns, 'backoff', None), getattr(ns, 'backoff_delay_ms', None), getattr(ns, 'backoff_max_ms', None)), json_out=getattr(ns, 'json', False))
            if ns.agent_cmd == "package":
                if ns.agent_pkg_cmd == 'init':
                    return _cmd_agent_package_init(ns.dir, ns.name, ns.force, getattr(ns, 'json', False))
                if ns.agent_pkg_cmd == 'run':
                    return _run_agent_package(ns.dir, ns.task, json_out=ns.json)
                if ns.agent_pkg_cmd == 'build':
                    return _cmd_agent_package_build(ns.dir, getattr(ns, 'out', None), getattr(ns, 'signing_key', None), getattr(ns, 'signer', None), getattr(ns, 'lock', False), getattr(ns, 'json', False))
                if ns.agent_pkg_cmd == 'publish':
                    return _cmd_agent_package_publish(ns.dir, getattr(ns, 'online', False), getattr(ns, 'registry', None), getattr(ns, 'token', None), getattr(ns, 'signing_key', None), getattr(ns, 'signer', None), getattr(ns, 'private', False), getattr(ns, 'lock', False), getattr(ns, 'json', False))
                if ns.agent_pkg_cmd == 'install':
                    return _cmd_agent_package_install(getattr(ns, 'name', None), getattr(ns, 'version', None), getattr(ns, 'online', False), getattr(ns, 'registry', None), getattr(ns, 'target_dir', None), getattr(ns, 'verify_key', None), getattr(ns, 'lockfile', None), getattr(ns, 'frozen', False), getattr(ns, 'private', False), getattr(ns, 'json', False))
                if ns.agent_pkg_cmd == 'search':
                    return _cmd_agent_package_search(ns.query, getattr(ns, 'online', False), getattr(ns, 'registry', None), getattr(ns, 'private', False), getattr(ns, 'json', False))
                if ns.agent_pkg_cmd == 'graph':
                    return _cmd_agent_package_graph(ns.ref, getattr(ns, 'json', False))
                if ns.agent_pkg_cmd == 'lock':
                    return _cmd_agent_package_lock(ns.dir, getattr(ns, 'json', False))
            if ns.agent_cmd == "policy":
                if ns.agent_policy_cmd == 'sign':
                    return _cmd_agent_policy_sign(ns.path, ns.key, getattr(ns, 'signer', None), getattr(ns, 'json', False))
                if ns.agent_policy_cmd == 'verify':
                    return _cmd_agent_policy_verify(ns.path, ns.key, getattr(ns, 'json', False))
            if ns.agent_cmd == "registry":
                if ns.agent_reg_cmd == 'login':
                    return _cmd_agent_registry_login(getattr(ns, 'registry', None), ns.token, getattr(ns, 'private', False), getattr(ns, 'json', False))
                if ns.agent_reg_cmd == 'logout':
                    return _cmd_agent_registry_logout(getattr(ns, 'registry', None), getattr(ns, 'private', False), getattr(ns, 'json', False))
                if ns.agent_reg_cmd == 'whoami':
                    return _cmd_agent_registry_whoami(getattr(ns, 'registry', None), getattr(ns, 'json', False))
            if ns.agent_cmd == "prompt":
                return _cmd_agent_prompt(ns.path, ns.task, ns.json)
            p.print_help()
            return 2
        if cmd == "compile":
            return _cmd_compile(ns.file, ns.target, ns.out, dump_ast=getattr(ns, "dump_ast", False), dump_ir=getattr(ns, "dump_ir", False), dump_ir_optimized=getattr(ns, "dump_ir_optimized", False), dump_cfg=getattr(ns, "dump_cfg", False), dump_cfg_optimized=getattr(ns, "dump_cfg_optimized", False), dump_dom=getattr(ns, "dump_dom", False), dump_dom_optimized=getattr(ns, "dump_dom_optimized", False), dump_def_use=getattr(ns, "dump_def_use", False), dump_def_use_optimized=getattr(ns, "dump_def_use_optimized", False), dump_ssa=getattr(ns, "dump_ssa", False), dump_ssa_optimized=getattr(ns, "dump_ssa_optimized", False), dump_format=getattr(ns, "dump_format", "text"), optimize=(not getattr(ns, "no_optimize", False)))
        if cmd == "playground":
            return _cmd_playground(getattr(ns, "host", "127.0.0.1"), getattr(ns, "port", 8765), getattr(ns, "build_only", False), getattr(ns, "out", ".mellow/playground"), getattr(ns, "json", False))
        if cmd == "native":
            subcmd = getattr(ns, "native_cmd", None) or "status"
            if subcmd == "status":
                return _cmd_native_status(getattr(ns, "json", False))
            if subcmd == "build":
                return _cmd_native_build(getattr(ns, "json", False))
            if subcmd == "doctor":
                return _cmd_native_doctor(getattr(ns, "json", False))
        if cmd == "standalone":
            subcmd = getattr(ns, "standalone_cmd", None) or "status"
            if subcmd == "status":
                return _cmd_standalone_status(getattr(ns, "json", False))
            if subcmd == "build":
                return _cmd_standalone_build(getattr(ns, "json", False), getattr(ns, "build_dir", None))
            if subcmd == "doctor":
                return _cmd_standalone_doctor(getattr(ns, "json", False))
            if subcmd == "compile":
                return _cmd_standalone_compile(getattr(ns, "input"), getattr(ns, "out", None), getattr(ns, "json", False), not getattr(ns, "no_optimize", False))
            if subcmd == "run":
                return _cmd_standalone_run(getattr(ns, "image"), getattr(ns, "binary", None), getattr(ns, "json", False))
            return 2
        if cmd == "install":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="install", name=ns.name, version=ns.version, online=True, registry=ns.registry, no_deps=ns.no_deps, project_dir=ns.project_dir))
        if cmd == "add":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="add", name=ns.name, version=ns.version, registry=ns.registry, no_deps=ns.no_deps, project_dir=ns.project_dir, alias=getattr(ns, "alias", None), interactive=getattr(ns, "interactive", False)))
        if cmd == "remove":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="remove", name=ns.name, project_dir=ns.project_dir))
        if cmd == "diagnose-imports":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="diagnose-imports", dir=ns.dir, registry=ns.registry))
        if cmd == "search":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="search", query=ns.query, registry=ns.registry, interactive=getattr(ns, 'interactive', False)))
        if cmd == "info":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="info", name=ns.name, registry=ns.registry))
        if cmd in {"profile", "author"}:
            return _cmd_pkg(argparse.Namespace(pkg_cmd="profile", author=ns.author, registry=ns.registry))
        if cmd in {"verify", "signature"}:
            return _cmd_pkg(argparse.Namespace(pkg_cmd="verify", name=ns.name, registry=ns.registry, installed=getattr(ns, "installed", False), project_dir=getattr(ns, "project_dir", None), strict=getattr(ns, "strict", False), json=getattr(ns, "json", False)))
        if cmd == "trust":
            if getattr(ns, "list", False) or not getattr(ns, "author", None):
                authors = pkg_trusted_authors()
                _cli_line(f"trusted creators: {len(authors)}", kind="info")
                for author in authors:
                    print(f"- {author}")
                return 0
            res = pkg_trust_author(ns.author, remove=getattr(ns, "remove", False))
            if not res.get("ok"):
                _cli_line(str(res.get("error", "trust policy update failed")), kind="error", file=sys.stderr)
                return 2
            action = "removed from trust policy" if getattr(ns, "remove", False) else "trusted"
            _cli_line(f"{ns.author}: {action}", kind="ok")
            print(f"config    : {res.get('saved_to')}")
            return 0
        if cmd == "publish":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="publish", dir=ns.dir, online=True, registry=ns.registry, token=ns.token))
        if cmd == "seed-core":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="seed-core", dir=ns.dir, publish_local=ns.publish_local))
        if cmd == "sync-imports":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="sync-imports", dir=ns.dir, registry=ns.registry))
        if cmd == "resolve-runtime":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="resolve-runtime", dir=ns.dir, registry=ns.registry, strict=getattr(ns, 'strict', False)))
        if cmd == "update":
            return _cmd_pkg(argparse.Namespace(
                pkg_cmd="update",
                name=getattr(ns, "name", None),
                registry=ns.registry,
                project_dir=ns.project_dir,
                check=getattr(ns, "check", False),
                all_packages=getattr(ns, "all_packages", False),
                no_deps=getattr(ns, "no_deps", False),
            ))
        if cmd == "uninstall":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="uninstall", name=ns.name, project_dir=ns.project_dir))
        if cmd == "login":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="login", token=getattr(ns, 'token', None), username=getattr(ns, 'username', None), password=getattr(ns, 'password', None), registry=ns.registry))
        if cmd == "whoami":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="whoami", registry=ns.registry))
        if cmd == "registry":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="registry", url=ns.url))
        if cmd == "logout":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="logout", registry=ns.registry))
        if cmd == "pkg":
            return _cmd_pkg(ns)
        if cmd == "fmt":
            return _cmd_fmt(ns.files, ns.write, ns.check)
        if cmd == "init":
            return _cmd_init(ns.dir, ns.force)
        if cmd == "new":
            return _cmd_new(ns.dir, ns.force, with_core=not getattr(ns, "no_core", False), preset=getattr(ns, "preset", "starter"))
        if cmd == "desktop":
            subcmd = getattr(ns, "desktop_cmd", None)
            if subcmd == "run":
                return _cmd_desktop_run(ns.file, dump_spec=getattr(ns, "dump_spec", False))
            if subcmd == "status":
                return _cmd_desktop_status(getattr(ns, "json", False))
            p.print_help()
            return 2
        if cmd == "mmg":
            subcmd = getattr(ns, "mmg_cmd", None)
            if subcmd == "run":
                return _cmd_mmg_run(ns.file, dump_spec=getattr(ns, "dump_spec", False))
            if subcmd == "run-native":
                return _cmd_mmg_run_native(ns.file, build_if_missing=getattr(ns, "build_if_missing", False), keep_scene=getattr(ns, "keep_scene", False), scene_out=getattr(ns, "scene_out", None))
            if subcmd == "export-native":
                return _cmd_mmg_export_native(ns.file, ns.out)
            if subcmd == "build-native":
                return _cmd_mmg_build_native(getattr(ns, "json", False))
            if subcmd == "status":
                return _cmd_mmg_status(getattr(ns, "json", False))
            p.print_help()
            return 2
        if cmd == "sm":
            subcmd = getattr(ns, "sm_cmd", None)
            if subcmd == "pack":
                return _cmd_sm_pack(ns.input, getattr(ns, "out", None), getattr(ns, "json", False))
            if subcmd == "unpack":
                return _cmd_sm_unpack(ns.input, getattr(ns, "out", None), getattr(ns, "json", False))
            if subcmd == "inspect":
                return _cmd_sm_inspect(ns.input, getattr(ns, "json", False))
            p.print_help()
            return 2
        if cmd == "melv":
            subcmd = getattr(ns, "melv_cmd", None)
            if subcmd == "encode":
                return _cmd_melv_encode(ns.input, ns.out, getattr(ns, "fps", None), getattr(ns, "max_frames", None), getattr(ns, "json", False))
            if subcmd == "decode":
                return _cmd_melv_decode(ns.input, ns.out, getattr(ns, "json", False))
            if subcmd == "extract":
                return _cmd_melv_extract(ns.input, ns.out, getattr(ns, "json", False))
            if subcmd == "inspect":
                return _cmd_melv_inspect(ns.input, getattr(ns, "json", False))
            p.print_help()
            return 2
        if cmd == "lsp":
            show_banner = False if getattr(ns, "no_banner", False) else None
            return int(_start_lsp(show_banner=show_banner) or 0)
        if cmd == "pack":
            return _cmd_pack(ns.entry, ns.out, ns.include, ns.name, ns.version)
        if cmd == "run":
            return _cmd_run(
                ns.file,
                json_out=ns.json,
                engine=getattr(ns, "engine", "c"),
                record_path=getattr(ns, "record_path", None),
                replay_path=getattr(ns, "replay_path", None),
                seed=getattr(ns, "seed", None),
                global_seed=getattr(ns, "global_seed", None),
                allow_ask=getattr(ns, "allow_ask", False),
                no_wait=getattr(ns, "no_wait", False),
                allow_storage=not getattr(ns, "no_storage", False),
                storage_dir=getattr(ns, "storage_dir", None),
                allow_unsafe_fs=getattr(ns, "unsafe_fs", False),
                max_steps=getattr(ns, "max_steps", None),
                max_ms=getattr(ns, "max_ms", None),
                syscall_budget=getattr(ns, "syscall_budget", None),
                profile=getattr(ns, "profile", False),
                trace=getattr(ns, "trace", False),
                step=getattr(ns, "step", False),
                break_lines=getattr(ns, "break_lines", None),
                watch=getattr(ns, "watch", None),
                ai_timeline=getattr(ns, "ai_timeline", None),
                color=False,
                no_color=False,
                registry=getattr(ns, "registry", None),
                no_resolve=getattr(ns, "no_resolve", False),
                sandbox_profile=getattr(ns, "sandbox_profile", "default"),
                allow_data_write=getattr(ns, "data_write", False),
                data_max_batch_size=getattr(ns, "data_batch_size", None),
                data_max_query_rows=getattr(ns, "data_max_rows", None),
                data_max_record_bytes=getattr(ns, "data_max_record_bytes", None),
                data_max_open_streams=getattr(ns, "data_max_streams", None),
                native_required=getattr(ns, "native_required", False),
            )
        if cmd == "test":
            return _cmd_test(
                ns.path,
                engine=getattr(ns, "engine", "auto"),
                pattern=getattr(ns, "pattern", None),
                json_out=ns.json,
                native_required=getattr(ns, "native_required", False),
            )
        if cmd == "record":
            record_path = getattr(ns, "record_path", None) or getattr(ns, "output", None)
            if not record_path:
                _cli_line("record needs an output log path, e.g. `mellow record app.mellow replay.jsonl`", kind="error", file=sys.stderr)
                return 2
            return _cmd_record(
                ns.file,
                record_path=record_path,
                engine=getattr(ns, "engine", "auto"),
                seed=getattr(ns, "seed", None),
                global_seed=getattr(ns, "global_seed", None),
                json_out=ns.json,
            )
        if cmd == "replay":
            replay_path = getattr(ns, "replay_path", None) or getattr(ns, "input", None)
            if not replay_path:
                _cli_line("replay needs a log path, e.g. `mellow replay app.mellow replay.jsonl`", kind="error", file=sys.stderr)
                return 2
            return _cmd_replay(
                ns.file,
                replay_path=replay_path,
                engine=getattr(ns, "engine", "auto"),
                json_out=ns.json,
            )
        if cmd == "diff":
            return _cmd_diff(ns.a, ns.b, json_out=ns.json)

        # unknown / future command
        p.print_help()
        return 2



    _cli_line("a command is required", kind="error", file=sys.stderr)
    _cli_line("Run `mellow help` to see available commands.", kind="hint", file=sys.stderr)
    return 2


def _scheduled_job_callback(job: dict[str, Any]) -> dict[str, Any]:
    if str(job.get('kind') or 'run') == 'workflow':
        runtime = _make_agent_runtime(str(job.get('model') or 'rule-based'), str(job.get('memory') or '.mellow/agent_memory.jsonl'), str(job.get('obs') or '.mellow/agent_observability.jsonl'), ['search.docs', 'time.now'], [], job.get('rag_file'), sandbox=bool(job.get('sandbox')), allow_caps=list(job.get('allow_caps') or []), secrets=list(job.get('secrets') or []))
        steps = [
            WorkflowStep('recall-memory', 'memory', retries=int(job.get('retries') or 0), timeout_ms=job.get('timeout_ms')),
            WorkflowStep('retrieve-context', 'rag', retries=int(job.get('retries') or 0), timeout_ms=job.get('timeout_ms')),
        ]
        if job.get('parallel'):
            steps.append(WorkflowStep('parallel-context', 'parallel', {'steps': [
                {'name': 'search-docs', 'kind': 'tool', 'payload': {'tool': 'search.docs', 'input': {'query': job['task']}}, 'retries': int(job.get('retries') or 0), 'timeout_ms': job.get('timeout_ms')},
                {'name': 'stamp-time', 'kind': 'tool', 'payload': {'tool': 'time.now', 'input': {}}, 'retries': int(job.get('retries') or 0), 'timeout_ms': job.get('timeout_ms')},
            ]}, retries=int(job.get('retries') or 0), timeout_ms=job.get('timeout_ms')))
        else:
            steps.append(WorkflowStep('search-docs', 'tool', {'tool': 'search.docs', 'input': {'query': job['task']}}, retries=int(job.get('retries') or 0), timeout_ms=job.get('timeout_ms')))
        steps.append(WorkflowStep('generate-answer', 'model', retries=int(job.get('retries') or 0), timeout_ms=job.get('timeout_ms')))
        result = WorkflowRunner(runtime).run(Workflow(name=f"scheduled-{job['name']}", steps=steps), str(job['task']))
        return {'ok': True, 'kind': 'workflow', 'workflow': result}
    if job.get('package'):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = _run_agent_package(str(job['package']), str(job['task']), json_out=True, sandbox=bool(job.get('sandbox')), allow_caps=list(job.get('allow_caps') or []), secrets=list(job.get('secrets') or []), timeout_ms=job.get('timeout_ms'))
        raw = buf.getvalue().strip()
        try:
            payload = json.loads(raw.splitlines()[-1]) if raw else {'ok': code == 0}
        except Exception:
            payload = {'ok': code == 0, 'raw': raw}
        return payload
    runtime = _make_agent_runtime(str(job.get('model') or 'rule-based'), str(job.get('memory') or '.mellow/agent_memory.jsonl'), str(job.get('obs') or '.mellow/agent_observability.jsonl'), [], [], job.get('rag_file'), sandbox=bool(job.get('sandbox')), allow_caps=list(job.get('allow_caps') or []), secrets=list(job.get('secrets') or []))
    result = runtime.run(str(job['task']), timeout_ms=job.get('timeout_ms'))
    return {'ok': True, 'kind': 'run', 'answer': result.answer, 'structured': result.structured, 'run_id': result.debug.get('run_id')}


def _cmd_agent_schedule(action: str, *, name: str | None = None, cron: str | None = None, task: str | None = None, kind: str = 'run', package: str | None = None, model: str = 'rule-based', memory: str = '.mellow/agent_memory.jsonl', obs: str = '.mellow/agent_observability.jsonl', rag_file: str | None = None, retries: int = 1, timeout_ms: int | None = None, parallel: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, secrets: list[str] | None = None, backoff: dict[str, Any] | None = None, json_out: bool = False) -> int:
    if action == 'add':
        payload = add_job(str(name), str(cron), str(task), kind=kind, package=package, model=model, memory=memory, obs=obs, rag_file=rag_file, retries=retries, timeout_ms=timeout_ms, parallel=parallel, sandbox=sandbox, allow_caps=allow_caps, secrets=secrets, backoff=backoff)
    elif action == 'run-due':
        payload = run_due_jobs(callback=_scheduled_job_callback)
    else:
        payload = agent_list_jobs()
    if json_out:
        _json_print(payload)
    else:
        if action == 'add' and payload.get('ok'):
            job = payload['job']
            _cli_line('Scheduled agent job created', kind='ok')
            print(f"Job ID          : {job['id']}")
            print(f"Name            : {job['name']}")
            print(f"Cron            : {job['schedule']}")
            print(f"Next run        : {job['next_run']}")
        elif action == 'run-due' and payload.get('ok'):
            _cli_line(f"Executed {payload.get('count', 0)} scheduled job(s)", kind='ok')
            for item in payload.get('items') or []:
                print(f"- {item['name']} -> {json.dumps(item.get('result'), ensure_ascii=False)}")
        else:
            _cli_line(f"Scheduled jobs: {payload.get('count', 0)}", kind='ok')
            for item in payload.get('items') or []:
                print(f"- {item['name']} [{item['kind']}] cron={item['schedule']} next={item.get('next_run')} runs={item.get('run_count', 0)}")
    return 0 if payload.get('ok') else 1


def _parse_jsonish(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {"value": data}
    except Exception:
        return {"raw": value}


def _parse_filters(values: list[str] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in values or []:
        raw = str(item)
        if '=' in raw:
            k, v = raw.split('=', 1)
            out[k.strip()] = v.strip()
    return out


def _build_backoff(strategy: str | None, delay_ms: int | None, max_ms: int | None) -> dict[str, Any]:
    return {
        'strategy': str(strategy or 'fixed'),
        'initial_delay_ms': max(0, int(delay_ms or 0)),
        'max_delay_ms': max(0, int(max_ms or delay_ms or 0)),
    }


def _cmd_agent_trigger(action: str, *, name: str | None = None, event: str | None = None, task: str | None = None, kind: str = 'run', package: str | None = None, model: str = 'rule-based', memory: str = '.mellow/agent_memory.jsonl', obs: str = '.mellow/agent_observability.jsonl', rag_file: str | None = None, retries: int = 1, timeout_ms: int | None = None, parallel: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, secrets: list[str] | None = None, filters: list[str] | None = None, payload: str | None = None, backoff: dict[str, Any] | None = None, json_out: bool = False) -> int:
    if action == 'add':
        data = add_trigger(str(name), str(event), str(task), kind=kind, package=package, model=model, memory=memory, obs=obs, rag_file=rag_file, retries=retries, timeout_ms=timeout_ms, parallel=parallel, sandbox=sandbox, allow_caps=allow_caps, secrets=secrets, filters=_parse_filters(filters), backoff=backoff)
    elif action == 'emit':
        data = emit_event(str(event), _parse_jsonish(payload))
    else:
        data = list_triggers()
    if json_out:
        _json_print(data)
    else:
        if action == 'add' and data.get('ok'):
            trig = data['trigger']
            _cli_line('Event trigger created', kind='ok')
            print(f"Trigger ID       : {trig['id']}")
            print(f"Name             : {trig['name']}")
            print(f"Event            : {trig['event']}")
        elif action == 'emit' and data.get('ok'):
            _cli_line(f"Queued {data.get('matched', 0)} job(s) for event {data.get('event')}", kind='ok')
        else:
            _cli_line(f"Event triggers: {data.get('count', 0)}", kind='ok')
            for item in data.get('items') or []:
                print(f"- {item['name']} event={item['event']} kind={item['kind']} runs={item.get('run_count', 0)}")
    return 0 if data.get('ok') else 1


def _cmd_agent_webhook(action: str, *, name: str | None = None, event: str | None = None, task: str | None = None, token: str | None = None, kind: str = 'run', package: str | None = None, model: str = 'rule-based', memory: str = '.mellow/agent_memory.jsonl', obs: str = '.mellow/agent_observability.jsonl', rag_file: str | None = None, retries: int = 1, timeout_ms: int | None = None, parallel: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, secrets: list[str] | None = None, payload: str | None = None, host: str = '127.0.0.1', port: int = 8788, token_header: str = 'X-Mellow-Webhook-Token', enable_job_api: bool = True, backoff: dict[str, Any] | None = None, json_out: bool = False) -> int:
    if action == 'add':
        data = add_webhook(str(name), str(event), token=token, task=str(task), kind=kind, package=package, model=model, memory=memory, obs=obs, rag_file=rag_file, retries=retries, timeout_ms=timeout_ms, parallel=parallel, sandbox=sandbox, allow_caps=allow_caps, secrets=secrets, backoff=backoff)
    elif action == 'receive':
        data = receive_webhook(str(name), _parse_jsonish(payload), token=token)
    elif action == 'serve':
        data = start_webhook_server(host=host, port=port, token_header=token_header, enable_job_api=enable_job_api)
    elif action == 'status':
        data = read_webhook_server_status()
    else:
        data = list_webhooks()
    if json_out:
        _json_print(data)
    else:
        if action == 'add' and data.get('ok'):
            hook = data.get('webhook') or {}
            _cli_line('Webhook job created', kind='ok')
            print(f"Name             : {hook.get('name')}")
            print(f"Event            : {hook.get('event')}")
            print(f"Token            : {hook.get('token')}")
        elif action == 'receive' and data.get('ok'):
            _cli_line(f"Webhook accepted, queued {data.get('matched', 0)} job(s)", kind='ok')
        elif action == 'serve' and data.get('ok'):
            _cli_line(f"Webhook server stopped: {data.get('url')}", kind='ok')
        elif action == 'status' and data.get('ok'):
            _cli_line('Webhook server status', kind='ok')
            print('Status          : ' + json.dumps(data, ensure_ascii=False))
        else:
            _cli_line(f"Webhooks: {data.get('count', 0)}", kind='ok')
            for item in data.get('items') or []:
                print(f"- {item['name']} event={item['event']} token={item['token']}")
    return 0 if data.get('ok') else 1


def _cmd_agent_queue(action: str, *, limit: int | None = None, item_id: str | None = None, workers: int = 1, json_out: bool = False) -> int:
    if action == 'run':
        data = drain_queue(limit=limit, callback=_scheduled_job_callback, workers=workers)
    elif action == 'stats':
        data = queue_stats()
    elif action == 'dead-letter':
        data = list_dead_letter()
    elif action == 'retry':
        data = retry_queue_item(str(item_id))
    elif action == 'log':
        data = read_queue_log(limit=limit or 50)
    else:
        data = list_queue()
    if json_out:
        _json_print(data)
    else:
        if action == 'run' and data.get('ok'):
            _cli_line(f"Processed {data.get('count', 0)} queued job(s)", kind='ok')
        elif action == 'stats' and data.get('ok'):
            _cli_line('Queue stats', kind='ok')
            print('Status          : ' + json.dumps(data, ensure_ascii=False))
        elif action == 'dead-letter' and data.get('ok'):
            _cli_line(f"Dead-letter items: {data.get('count', 0)}", kind='ok')
            for item in data.get('items') or []:
                print(f"- {item['id']} name={item.get('name')} error={item.get('last_error')}")
        elif action == 'retry' and data.get('ok'):
            _cli_line(f"Requeued dead-letter item {data.get('item', {}).get('id')}", kind='ok')
        elif action == 'log' and data.get('ok'):
            _cli_line(f"Queue log entries: {data.get('count', 0)}", kind='ok')
            for item in data.get('items') or []:
                print(json.dumps(item, ensure_ascii=False))
        else:
            _cli_line(f"Queue items: {data.get('count', 0)} (queued={data.get('queued', 0)}, done={data.get('done', 0)}, retry={data.get('retry', 0)}, dead-letter={data.get('dead_letter', 0)})", kind='ok')
            for item in data.get('items') or []:
                print(f"- {item['name']} status={item['status']} source={item.get('source')} event={item.get('event')}")
    return 0 if data.get('ok') else 1


def _cmd_agent_jobs(action: str, *, task: str | None = None, name: str | None = None, kind: str = 'run', package: str | None = None, model: str = 'rule-based', memory: str = '.mellow/agent_memory.jsonl', obs: str = '.mellow/agent_observability.jsonl', rag_file: str | None = None, retries: int = 1, timeout_ms: int | None = None, parallel: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, secrets: list[str] | None = None, payload: str | None = None, host: str = '127.0.0.1', port: int = 8788, job_id: str | None = None, backoff: dict[str, Any] | None = None, json_out: bool = False) -> int:
    if action == 'submit':
        data = submit_job(str(task), name=name, kind=kind, package=package, model=model, memory=memory, obs=obs, rag_file=rag_file, retries=retries, timeout_ms=timeout_ms, parallel=parallel, sandbox=sandbox, allow_caps=allow_caps, secrets=secrets, backoff=backoff, payload=_parse_jsonish(payload))
    elif action == 'get':
        data = get_queue_item(str(job_id))
    elif action == 'serve':
        data = start_webhook_server(host=host, port=port, enable_job_api=True)
    elif action == 'status':
        data = read_job_api_status()
    else:
        data = list_queue()
    if json_out:
        _json_print(data)
    else:
        if action == 'submit' and data.get('ok'):
            item = data.get('item') or {}
            _cli_line(f"Job submitted: {item.get('id')}", kind='ok')
            print('Status          : ' + json.dumps(item, ensure_ascii=False))
        elif action == 'get' and data.get('ok'):
            _cli_line(f"Job {job_id}", kind='ok')
            print('Status          : ' + json.dumps(data.get('item'), ensure_ascii=False))
        elif action == 'serve' and data.get('ok'):
            _cli_line(f"Job API server stopped: {data.get('url')}", kind='ok')
        elif action == 'status' and data.get('ok'):
            _cli_line('Job API server status', kind='ok')
            print('Status          : ' + json.dumps(data, ensure_ascii=False))
        else:
            _cli_line(f"Jobs in queue: {data.get('count', 0)}", kind='ok')
            for item in data.get('items') or []:
                print(f"- {item.get('id')} name={item.get('name')} status={item.get('status')}")
    return 0 if data.get('ok') else 1


def _cmd_agent_runner(action: str, *, interval_s: float = 1.0, iterations: int = 1, queue_backed: bool = False, queue_limit: int | None = None, workers: int = 1, json_out: bool = False) -> int:
    payload = run_background_runner(interval_s=interval_s, iterations=iterations, callback=_scheduled_job_callback, queue_backed=queue_backed, queue_limit=queue_limit, workers=workers) if action == 'start' else read_runner_status()
    if json_out:
        _json_print(payload)
    else:
        if action == 'start' and payload.get('ok'):
            _cli_line('Background agent runner finished', kind='ok')
            print('Status          : ' + json.dumps(payload, ensure_ascii=False))
        else:
            _cli_line('Background agent runner status', kind='ok')
            print('Status          : ' + json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get('ok', True) else 1




def _cmd_standalone_compile(input_path: str, out_path: str | None, json_out: bool, optimize: bool = True) -> int:
    try:
        res = compile_standalone_image(input_path, output_path=out_path, optimize=optimize)
    except Exception as e:
        res = {'ok': False, 'error': str(e), 'input': input_path}
    if json_out:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get('ok') else 1
    if res.get('ok'):
        _cli_line('Standalone image compiled.', kind='ok')
        print(f"Input           : {res.get('input')}")
        print(f"Output          : {res.get('output')}")
        print(f"Instructions    : {res.get('code_len')}")
        print(f"Constants       : {res.get('const_len')}")
        return 0
    _cli_line(f"Standalone compile failed: {res.get('error')}", kind='error')
    return 1


def _cmd_standalone_run(image_path: str, binary_path: str | None, json_out: bool) -> int:
    res = standalone_run_image(image_path, binary_path=binary_path)
    if json_out:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get('ok') else 1
    if res.get('stdout'):
        print(res['stdout'], end='')
    if res.get('stderr'):
        print(res['stderr'], end='', file=sys.stderr)
    if not res.get('ok'):
        _cli_line(f"Standalone runtime failed: {res.get('error') or 'run_failed'}", kind='error', file=sys.stderr)
        return 1
    return 0


def _cmd_standalone_status(json_out: bool) -> int:
    info = standalone_runtime_status()
    if json_out:
        print(json.dumps(info, indent=2))
        return 0
    _cli_line(f"Standalone runtime root: {info.get('root')}")
    if info.get('binary_exists'):
        _cli_line(f"Standalone binary: {info.get('binary_path')}", kind='ok')
    else:
        _cli_line('Standalone binary not built yet.', kind='warn')
    _cli_line(f"CMake available: {info.get('cmake_available')}")
    _cli_line(f"C compiler available: {info.get('compiler_available')}")
    return 0


def _cmd_standalone_build(json_out: bool, build_dir: str | None = None) -> int:
    res = build_standalone_runtime(build_dir=build_dir)
    if json_out:
        print(json.dumps(res, indent=2))
        return 0 if res.get('ok') else 1
    if res.get('ok'):
        _cli_line('Standalone runtime build succeeded.', kind='ok')
        return 0
    _cli_line(f"Standalone runtime build failed: {res.get('error', 'build_failed')}", kind='error')
    hint = res.get('hint')
    if hint:
        _cli_line(hint, kind='hint')
    return 1


def _cmd_standalone_doctor(json_out: bool) -> int:
    info = standalone_runtime_status()
    checks = {
        'runtime_sources': info.get('exists'),
        'cmake_available': info.get('cmake_available'),
        'compiler_available': info.get('compiler_available'),
    }
    payload = {'ok': all(checks.values()), 'checks': checks, 'status': info}
    if json_out:
        print(json.dumps(payload, indent=2))
        return 0 if payload['ok'] else 1
    for name, ok in checks.items():
        _cli_line(f"{name}: {'ok' if ok else 'missing'}", kind='ok' if ok else 'warn')
    return 0 if payload['ok'] else 1



if __name__ == "__main__":
    raise SystemExit(main())
