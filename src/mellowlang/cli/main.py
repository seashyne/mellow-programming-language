from __future__ import annotations

import argparse
import sys
from typing import List

from .. import __version__
from .common import (
    _cli_line,
    _lazy_attr,
    _looks_like_script_path,
    _prog,
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
from .commands.agents import (
    _build_backoff,
    _cmd_agent_control_plane,
    _cmd_agent_demo,
    _cmd_agent_deploy,
    _cmd_agent_inspect_log,
    _cmd_agent_jobs,
    _cmd_agent_marketplace,
    _cmd_agent_package_build,
    _cmd_agent_package_graph,
    _cmd_agent_package_init,
    _cmd_agent_package_install,
    _cmd_agent_package_lock,
    _cmd_agent_package_publish,
    _cmd_agent_package_search,
    _cmd_agent_playground,
    _cmd_agent_policy_sign,
    _cmd_agent_policy_verify,
    _cmd_agent_preview,
    _cmd_agent_prompt,
    _cmd_agent_prompt_debug,
    _cmd_agent_queue,
    _cmd_agent_registry_login,
    _cmd_agent_registry_logout,
    _cmd_agent_registry_whoami,
    _cmd_agent_run,
    _cmd_agent_runner,
    _cmd_agent_schedule,
    _cmd_agent_secret,
    _cmd_agent_serve,
    _cmd_agent_trace,
    _cmd_agent_trigger,
    _cmd_agent_webhook,
    _cmd_agent_workflow,
    _cmd_playground,
    _run_agent_package,
)
from .commands.compiler import _cmd_compile, _cmd_pack
from .commands.media import (
    _cmd_desktop_run,
    _cmd_desktop_status,
    _cmd_melv_decode,
    _cmd_melv_encode,
    _cmd_melv_extract,
    _cmd_melv_extract_native,
    _cmd_melv_inspect,
    _cmd_melv_pack_frames,
    _cmd_melv_validate,
    _cmd_mmg_build_native,
    _cmd_mmg_export_native,
    _cmd_mmg_run,
    _cmd_mmg_run_native,
    _cmd_mmg_status,
    _cmd_sm_inspect,
    _cmd_sm_pack,
    _cmd_sm_unpack,
)
from .commands import packages as _package_commands
from .commands.packages import _cmd_pkg
from .commands.project import _cmd_check, _cmd_fmt, _cmd_init, _cmd_new
from .commands.runtime import _cmd_diff, _cmd_record, _cmd_replay, _cmd_run, _cmd_test
from .commands.standalone import (
    _cmd_standalone_build,
    _cmd_standalone_compile,
    _cmd_standalone_doctor,
    _cmd_standalone_run,
    _cmd_standalone_status,
)
from .commands.web import _cmd_web, _cmd_web_dev
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
pkg_trust_author = _lazy_attr(_PM, "trust_author")
pkg_trusted_authors = _lazy_attr(_PM, "trusted_authors")

# Kept as lazy compatibility hooks for callers that patch the former CLI facade.
pkg_search_remote = _lazy_attr(_PM, "search_remote")
pkg_package_info_remote = _lazy_attr(_PM, "package_info_remote")
pkg_install_remote = _lazy_attr(_PM, "install_remote")
pkg_author_profile_remote = _lazy_attr(_PM, "author_profile_remote")
pkg_package_signature_remote = _lazy_attr(_PM, "package_signature_remote")
pkg_update_packages = _lazy_attr(_PM, "update_packages")

# ============================================================
# CLI policy
# - Commands use the explicit subcommand interface.
# ----------------------------



def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    prog = _prog()

    if not argv or argv in (["-h"], ["--help"]):
        print(_quick_help_text(prog))
        return 0

    if argv == ["--version"]:
        print(f"{prog} {__version__}")
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

        for name in (
            "pkg_search_remote",
            "pkg_package_info_remote",
            "pkg_install_remote",
            "pkg_author_profile_remote",
            "pkg_package_signature_remote",
            "pkg_update_packages",
        ):
            setattr(_package_commands, name, globals()[name])

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
        if cmd == "web":
            if getattr(ns, "web_cmd", None) == "dev":
                return _cmd_web_dev(
                    getattr(ns, "file", None),
                    app_dir=getattr(ns, "dir", None),
                    port=getattr(ns, "port", None),
                    host=getattr(ns, "host", None),
                    json_out=getattr(ns, "json", False),
                    build_only=getattr(ns, "build_only", False),
                    prepare_only=getattr(ns, "prepare_only", False),
                )
            return _cmd_web(getattr(ns, "web_cmd", None), getattr(ns, "file", None), getattr(ns, "out", None), getattr(ns, "json", False))
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
            if subcmd in {"encode", "import-video"}:
                return _cmd_melv_encode(ns.input, ns.out, getattr(ns, "fps", None), getattr(ns, "max_frames", None), getattr(ns, "json", False))
            if subcmd == "pack-frames":
                return _cmd_melv_pack_frames(ns.frames, ns.out, getattr(ns, "fps", None), getattr(ns, "json", False))
            if subcmd in {"decode", "export-video"}:
                return _cmd_melv_decode(ns.input, ns.out, getattr(ns, "json", False))
            if subcmd == "extract-native":
                return _cmd_melv_extract_native(ns.input, ns.out, getattr(ns, "json", False))
            if subcmd == "extract":
                return _cmd_melv_extract(ns.input, ns.out, getattr(ns, "json", False))
            if subcmd == "inspect":
                return _cmd_melv_inspect(ns.input, getattr(ns, "json", False))
            if subcmd == "validate":
                return _cmd_melv_validate(ns.input, getattr(ns, "strict", False), getattr(ns, "json", False))
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



if __name__ == "__main__":
    raise SystemExit(main())
