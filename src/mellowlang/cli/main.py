from __future__ import annotations

import argparse
import ast as py_ast
import difflib
import json
import re
import os
import shutil
import sys
import platform
import subprocess
import threading
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import import_module
from importlib import metadata as importlib_metadata
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, List

from .. import __version__
from ..lint import lint_source, format_source
from ..host.modules import MODULE_ALLOWLIST
from ..compiler import Compiler, CompiledProgram
from ..vm import MellowVM, RunConfig
from ..error_explain import explain as explain_error


class _LazyAttr:
    def __init__(self, module_name: str, attr_name: str):
        self._module_name = module_name
        self._attr_name = attr_name
        self._value: Any | None = None

    def _resolve(self) -> Any:
        if self._value is None:
            self._value = getattr(import_module(self._module_name), self._attr_name)
        return self._value

    def __call__(self, *args, **kwargs):
        return self._resolve()(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolve(), name)

    def __fspath__(self) -> str:
        return os.fspath(self._resolve())

    def __str__(self) -> str:
        return str(self._resolve())

    def __repr__(self) -> str:
        return repr(self._resolve())


def _lazy_attr(module_name: str, attr_name: str) -> _LazyAttr:
    return _LazyAttr(module_name, attr_name)


_PM = "mellowlang.package_manager"
pkg_init_package = _lazy_attr(_PM, "init_package")
pkg_list_installed = _lazy_attr(_PM, "list_installed")
pkg_publish_from_dir = _lazy_attr(_PM, "publish_from_dir")
pkg_install_package = _lazy_attr(_PM, "install_package")
pkg_build_package_archive = _lazy_attr(_PM, "build_package_archive")
pkg_search_remote = _lazy_attr(_PM, "search_remote")
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
PKG_CONFIG_FILE = _lazy_attr(_PM, "CONFIG_FILE")
PKG_CACHE_ROOT = _lazy_attr(_PM, "CACHE_ROOT")
pkg_interactive_pick_package = _lazy_attr(_PM, "interactive_pick_package")
pkg_diagnose_imports = _lazy_attr(_PM, "diagnose_imports")
pkg_suggest_aliases_for_package = _lazy_attr(_PM, "suggest_aliases_for_package")
pkg_scaffold_project = _lazy_attr(_PM, "scaffold_project")
pkg_ensure_project_starter_packages = _lazy_attr(_PM, "ensure_project_starter_packages")

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
# CLI policy (v1.0.7+)
# - Legacy UX stays supported.
# - Modern subcommands stay supported.
# - No breaking removals in v1.x (only additive).
# ============================================================

MODERN_CMDS = {"agent", "check", "compile", "doctor", "explain", "fmt", "help", "init", "new", "install", "login", "logout", "lsp", "modules", "native", "standalone", "pack", "pkg", "publish", "registry", "run", "search", "seed-core", "sync-imports", "resolve-runtime", "uninstall", "update", "test", "replay", "diff", "assistant", "whoami", "add", "remove", "diagnose-imports", "playground", "desktop", "mmg", "sm", "melv"}
MODERN_CMDS |= {"doctor", "pack", "explain"}



def _cli_palette() -> dict[str, str]:
    if not _supports_ansi():
        return {"reset": "", "red": "", "green": "", "yellow": "", "blue": "", "bold": "", "dim": ""}
    return {
        "reset": "\033[0m",
        "red": "\033[31m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "blue": "\033[34m",
        "bold": "\033[1m",
        "dim": "\033[2m",
    }


def _cli_icon(kind: str) -> str:
    if not _supports_ansi():
        return {"ok": "OK", "info": "*", "warn": "!", "error": "ERR", "hint": ">"}.get(kind, "*")
    return {"ok": "✓", "info": "•", "warn": "!", "error": "✖", "hint": "→"}.get(kind, "•")


def _cli_line(message: str, *, kind: str = "info", file=None) -> None:
    pal = _cli_palette()
    color = {"ok": pal["green"], "info": pal["blue"], "warn": pal["yellow"], "error": pal["red"], "hint": pal["dim"]}.get(kind, "")
    print(f"{color}{_cli_icon(kind)}{pal['reset']} {message}", file=file or sys.stdout)


def _looks_like_script_path(value: str | None) -> bool:
    if not value or value.startswith('-'):
        return False
    low = value.lower()
    return low.endswith('.mellow') or low.endswith('.mel')


def _argv_prefers_direct_run(argv: list[str]) -> bool:
    return bool(argv) and _looks_like_script_path(argv[0])


def _suggest_command(name: str) -> str | None:
    matches = difflib.get_close_matches(name, sorted(MODERN_CMDS), n=1, cutoff=0.5)
    return matches[0] if matches else None


def _prompt_yes_no(prompt: str, *, default: bool = True) -> bool:
    if not sys.stdin.isatty():
        return default
    suffix = 'Y/n' if default else 'y/N'
    try:
        raw = input(f"{prompt} [{suffix}]: ").strip().lower()
    except EOFError:
        return default
    if not raw:
        return default
    return raw in {"y", "yes"}

def _start_lsp() -> int:
    from ..lsp_server import start_lsp  # lazy import (pygls optional)
    return int(start_lsp() or 0)


def _supports_ansi() -> bool:
    if not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    env = os.environ
    return any(k in env for k in ("WT_SESSION", "TERM", "ANSICON", "ConEmuANSI")) or (
        "vscode" in env.get("TERM_PROGRAM", "").lower()
    )


def _print_pretty_error(
    err: Exception,
    filename: str | None = None,
    source_lines: list[str] | None = None,
    *,
    use_color: bool | None = None,
) -> None:
    """
    Frinds-style error formatter:
      Error: <TYPE> at <file>:<line>:<col>
        <message>
        <code frame + caret>
    """
    msg = getattr(err, "message", None) or str(err)

    if use_color is None:
        use_color = _supports_ansi()

    if use_color:
        RED = "\033[31m"
        YELLOW = "\033[33m"
        DIM = "\033[2m"
        RESET = "\033[0m"
    else:
        RED = YELLOW = DIM = RESET = ""

    # ---- Pull structured fields if present (preferred) ----
    err_type = getattr(err, "error_type", None)
    line_no = getattr(err, "line_num", None)
    col = getattr(err, "col", None)
    fn = getattr(err, "filename", None) or filename

    # ---- Fallback: infer line/col from message (ParseError, etc.) ----
    snippet = None
    if line_no is None:
        m = re.search(r"\bline\s+(\d+)\b", msg)
        if m:
            line_no = int(m.group(1))
    if fn is None:
        # e.g. "RUNTIME at test.fds:46: division by zero"
        m = re.search(r"\bat\s+(.+?):(\d+)(?::(\d+))?\b", msg)
        if m:
            fn = m.group(1)
            if line_no is None:
                line_no = int(m.group(2))
            if m.group(3) and col is None:
                col = int(m.group(3))
    # snippet often appears after ":" in messages like "... at line 6: kee i"
    m = re.search(r"\bline\s+\d+\s*:\s*(.+)$", msg)
    if m:
        snippet = m.group(1).strip()

    # --- Friendly hints (DX) ---
    # Add small, deterministic hints for common mistakes.
    try:
        if (getattr(err, 'error_type', None) in (None, 'SYNTAX') and 'Unknown statement' in msg):
            # Common case: user wrote a function call as a statement, or used named args.
            if snippet and '(' in snippet and ')' in snippet:
                msg += "\nHint: you can call functions as statements (game-friendly)."
                if '=' in snippet:
                    msg += "\nHint: named args are supported, e.g. file_write(\"a.txt\", \"hi\", mode=\"w\")."
                msg += "\nTip: if this still errors, try `call(file_write, ...)` (legacy form)."
    except Exception:
        pass

    if not err_type:
        # ParseError usually means SYNTAX, everything else ERROR
        err_type = "SYNTAX" if err.__class__.__name__ in ("ParseError",) else "ERROR"

    # Compute column from snippet if possible
    if source_lines and line_no and col is None and snippet:
        try:
            line_text = source_lines[int(line_no) - 1]
            idx = line_text.find(snippet)
            if idx >= 0:
                col = idx + 1
        except Exception:
            pass
    if col is None:
        col = 1

    # ---- Header (match Frinds look) ----
    loc = ""
    if fn and line_no:
        loc = f"{fn}:{line_no}:{col}"
    elif fn and line_no is None:
        loc = str(fn)
    elif line_no:
        loc = f"line {line_no}:{col}"

    print(f"{RED}Error:{RESET} {err_type}" + (f" at {loc}" if loc else ""))
    print(f"  {msg}")

    # ---- Call stack (if present) ----
    trace = getattr(err, "trace", None)
    if trace:
        print(f"{DIM}Call Stack:{RESET}")
        for fr in reversed(trace):
            nm = fr.get("name", "<frame>")
            ffn = fr.get("filename", fn) or "<script>"
            ln = fr.get("line")
            cc = fr.get("col")
            floc = ffn if ln is None else f"{ffn}:{ln}" + (f":{cc}" if cc else "")
            print(f"  at {nm} ({floc})")

    # ---- Code frame ----
    if not source_lines or not line_no:
        return
    try:
        ln = int(line_no)
    except Exception:
        return
    if ln < 1 or ln > len(source_lines):
        return

    i = ln - 1
    lo = max(0, i - 1)
    hi = min(len(source_lines) - 1, i + 1)
    for j in range(lo, hi + 1):
        prefix = ">" if j == i else " "
        print(f"{prefix} {j+1:3d} | {source_lines[j].rstrip()}")
        if j == i:
            caret_pos = max(1, min(int(col), len(source_lines[j]) + 1))
            print(f"    | {' '*(caret_pos-1)}{YELLOW}^{RESET}")


def _prog() -> str:
    base = os.path.basename(sys.argv[0]) or "mellow"
    return os.path.splitext(base)[0]

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

def _find_project_root(start: Path) -> Path | None:
    """Find nearest parent dir containing mellow.json."""
    try:
        p = start.resolve()
    except Exception:
        p = start
    if p.is_file():
        p = p.parent
    for parent in [p] + list(p.parents):
        if (parent / "mellow.json").exists() or (parent / "mellow.toml").exists() or (parent / "mellow.pkg.json").exists():
            return parent
    return None

def _json_print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))

def _build_legacy_parser() -> argparse.ArgumentParser:
    prog = _prog()
    p = argparse.ArgumentParser(
        prog=prog,
        formatter_class=argparse.RawTextHelpFormatter,
        description=f"""MellowLang {__version__}
Friendly scripting language (game / AI focused)

Legacy usage:
  {prog} <script.mellow> [options]

Modern usage:
  {prog} run <script>
  {prog} check <script>
  {prog} fmt [-w] [--check] <files...>
  {prog} init <dir> [--force]
  {prog} modules [--json]
  {prog} login --token <token>
  {prog} whoami
  {prog} registry <url>
  {prog} search <query>
  {prog} install <package>
  {prog} add <package>
  {prog} remove <package>
  {prog} publish <dir>
  {prog} lsp
""",
    )

    p.add_argument("script", nargs="?", help="Path to .mellow script")

    # runtime flags (legacy-compatible)
    p.add_argument("--check", dest="check_only", action="store_true",
                  help="Only check syntax/lint; do not run")
    p.add_argument("--modules", dest="list_modules", action="store_true",
                  help="List allowed host modules (same as: modules)")
    p.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    mx = p.add_mutually_exclusive_group()
    mx.add_argument("--record", dest="record_path", help="Record deterministic replay log (.jsonl)")
    mx.add_argument("--replay", dest="replay_path", help="Replay deterministic log (.jsonl)")

    p.add_argument("--seed", type=int, help="Per-script seed")
    p.add_argument("--global-seed", type=int, help="Global base seed")

    p.add_argument("--allow-ask", action="store_true", help="Enable input()/ask() in sandbox")
    p.add_argument("--no-wait", action="store_true", help="Disable wait() in sandbox")
    p.add_argument("--sandbox", dest="sandbox_profile", choices=["default", "finance", "data"], default="default",
                  help="Runtime sandbox profile")
    p.add_argument("--data-write", action="store_true", help="Allow data core writes")
    p.add_argument("--data-batch-size", type=int, help="Maximum rows returned by data.next")
    p.add_argument("--data-max-rows", type=int, help="Maximum SQLite query rows")

    # Storage
    p.add_argument("--no-storage", action="store_true", help="Disable storage APIs")
    p.add_argument("--storage-dir", help="Base directory for storage (default: mellow_saves)")
    p.add_argument("--unsafe-fs", action="store_true", help="Allow scripts to set storage_dir to absolute paths or use '..' (unsafe)")

    # Debugger (v1.2.0)
    p.add_argument("--trace", action="store_true", help="Trace executed lines")
    p.add_argument("--step", action="store_true", help="Step execution (TTY interactive)")
    p.add_argument("--break", dest="break_lines", help="Breakpoints by line, e.g. 12,20-25")
    p.add_argument("--watch", help="Watch variables, e.g. hp,pos,target")
    p.add_argument("--ai-timeline", dest="ai_timeline", help="Write AI decision timeline (.jsonl)")
    p.add_argument("--color", action="store_true", help="Force colored errors")
    p.add_argument("--no-color", action="store_true", help="Disable colored errors")

    # compatibility flags (kept, but no longer required)
    p.add_argument("--engine", action="store_true", help="(Compat) Ignored in v1.0.7+")
    p.add_argument("--legacy", action="store_true", help="(Compat) Ignored in v1.0.7+")
    p.add_argument("--emit", dest="emit_name", help="(Compat) Reserved for .fds workflows")
    p.add_argument("--emit-args", dest="emit_args_raw", help="(Compat) JSON array args for --emit")

    p.add_argument("--lsp", action="store_true", help="Start Language Server (stdio)")
    p.add_argument("--version", action="version", version=f"{prog} {__version__}")
    return p

def _build_modern_parser() -> argparse.ArgumentParser:
    prog = _prog()
    p = argparse.ArgumentParser(
        prog=prog,
        formatter_class=argparse.RawTextHelpFormatter,
        description=f"""MellowLang {__version__}

Modern commands:
  {prog} run <file>            Run a script
  {prog} check <file>          Lint / syntax check
  {prog} assistant <file>      Code assistant (summary + hints)
  {prog} fmt <files...>        Format source
  {prog} init <dir>            Create a project
  {prog} modules [--json]      List allowed host modules
  {prog} login --token <token> Authenticate to a registry
  {prog} whoami                Show active registry identity
  {prog} registry <url>        Set default registry
  {prog} search <query>        Search packages
  {prog} install <package>     Install package from registry
  {prog} publish <dir>         Publish package to registry
  {prog} seed-core <dir>       Generate starter packages for the Mellow ecosystem
  {prog} sync-imports <dir>    Resolve imports, install missing deps, and write mellow.lock
  {prog} resolve-runtime <dir> Build .mellow_runtime.json for package imports
  {prog} update [name]         Update dependencies from registry/lockfile
  {prog} uninstall <name>      Remove an installed dependency
  {prog} lsp                   Start language server (stdio)
""",
    )
    p.add_argument("--version", action="version", version=f"{prog} {__version__}")

    sub = p.add_subparsers(dest="cmd")

    pr = sub.add_parser("run", help="Run a script")
    pr.add_argument("file")
    pr.add_argument("--json", action="store_true")
    pr.add_argument("--engine", choices=["auto","py","c","fast"], default="auto", help="Execution engine: fast=compile-to-Python (~100-200x faster)")
    pr.add_argument("--record", dest="record_path")
    pr.add_argument("--replay", dest="replay_path")
    pr.add_argument("--seed", type=int)
    pr.add_argument("--global-seed", type=int)
    pr.add_argument("--allow-ask", action="store_true")
    pr.add_argument("--no-wait", action="store_true")
    pr.add_argument("--sandbox", dest="sandbox_profile", choices=["default", "finance", "data"], default="default",
                    help="Runtime sandbox profile")
    pr.add_argument("--data-write", action="store_true", help="Allow data.sqlite_execute and other data writes")
    pr.add_argument("--data-batch-size", type=int, help="Maximum rows returned by data.next")
    pr.add_argument("--data-max-rows", type=int, help="Maximum SQLite rows returned per query")
    pr.add_argument("--data-max-record-bytes", type=int, help="Maximum encoded size of one streamed record")
    pr.add_argument("--data-max-streams", type=int, help="Maximum concurrently open data streams")
    pr.add_argument("--no-storage", action="store_true", help="Disable storage APIs")
    pr.add_argument("--storage-dir", help="Base directory for storage (default: mellow_saves)")
    pr.add_argument("--unsafe-fs", action="store_true", help="Allow scripts to set storage_dir to absolute paths or use '..' (unsafe)")
    pr.add_argument("--max-steps", type=int, help="Sandbox step limit")
    pr.add_argument("--max-ms", type=int, help="Sandbox time limit (milliseconds)")
    pr.add_argument("--syscall-budget", type=int, help="Sandbox syscall budget")
    pr.add_argument("--profile", action="store_true", help="Return execution stats")

    # Debugger (v1.2.0)
    pr.add_argument("--trace", action="store_true", help="Trace executed lines")
    pr.add_argument("--step", action="store_true", help="Step execution (TTY interactive)")
    pr.add_argument("--break", dest="break_lines", help="Breakpoints by line, e.g. 12,20-25")
    pr.add_argument("--watch", help="Watch variables, e.g. hp,pos,target")
    pr.add_argument("--ai-timeline", dest="ai_timeline", help="Write AI decision timeline (.jsonl)")
    pr.add_argument("--registry", help="Registry base URL used for auto-resolve")
    pr.add_argument("--no-resolve", action="store_true", help="Skip auto dependency/runtime resolution before run")

    
    pt = sub.add_parser("test", help="Run tests (optionally dual-engine)")
    pt.add_argument("path", nargs="?", default="tests", help="File or directory (default: tests)")
    pt.add_argument("--engine", choices=["py","c","dual"], default="dual")
    pt.add_argument("--pattern", default="*.mellow", help="Glob pattern for test files")
    pt.add_argument("--json", action="store_true")

    prp = sub.add_parser("replay", help="Replay a recorded run")
    prp.add_argument("file", help="Script to run")
    prp.add_argument("--input", required=True, dest="replay_path", help="Replay log (.jsonl)")
    prp.add_argument("--engine", choices=["auto","py","c"], default="auto")
    prp.add_argument("--json", action="store_true")

    pdiff = sub.add_parser("diff", help="Diff two replay logs (.jsonl)")
    pdiff.add_argument("a")
    pdiff.add_argument("b")
    pdiff.add_argument("--json", action="store_true")

    pcompile = sub.add_parser("compile", help="Compile a script to bytecode JSON or Python")
    pcompile.add_argument("file")
    pcompile.add_argument("--target", choices=["bytecode", "python"], default="bytecode")
    pcompile.add_argument("--out")
    pcompile.add_argument("--dump-ast", action="store_true", help="Print AST after parsing")
    pcompile.add_argument("--dump-ir", action="store_true", help="Print lowered IR before optimization")
    pcompile.add_argument("--dump-ir-optimized", action="store_true", help="Print optimized IR used for bytecode generation")
    pcompile.add_argument("--dump-cfg", action="store_true", help="Print CFG before optimization")
    pcompile.add_argument("--dump-cfg-optimized", action="store_true", help="Print CFG after optimization")
    pcompile.add_argument("--dump-dom", action="store_true", help="Print dominator tree before optimization")
    pcompile.add_argument("--dump-dom-optimized", action="store_true", help="Print dominator tree after optimization")
    pcompile.add_argument("--dump-def-use", action="store_true", help="Print SSA-prep def-use chains before optimization")
    pcompile.add_argument("--dump-def-use-optimized", action="store_true", help="Print SSA-prep def-use chains after optimization")
    pcompile.add_argument("--dump-ssa", action="store_true", help="Print SSA metadata before optimization")
    pcompile.add_argument("--dump-ssa-optimized", action="store_true", help="Print SSA metadata after optimization")
    pcompile.add_argument("--dump-format", choices=["text", "json"], default="text")
    pcompile.add_argument("--no-optimize", action="store_true", help="Disable IR optimization passes")

    ppkg = sub.add_parser("pkg", help="Package manager (local + online registry)")
    pkg_sub = ppkg.add_subparsers(dest="pkg_cmd")
    pkg_init = pkg_sub.add_parser("init", help="Create mellow.pkg.json package")
    pkg_init.add_argument("dir")
    pkg_init.add_argument("--name")
    pkg_init.add_argument("--entry", default="main.mellow")
    pkg_publish = pkg_sub.add_parser("publish", help="Publish package")
    pkg_publish.add_argument("dir")
    pkg_publish.add_argument("--online", action="store_true", help="Publish to remote registry")
    pkg_publish.add_argument("--registry", help="Registry base URL")
    pkg_publish.add_argument("--token", help="Publish token; otherwise uses saved token or MELLOW_PUBLISH_TOKEN")
    pkg_install = pkg_sub.add_parser("install", help="Install package")
    pkg_install.add_argument("name")
    pkg_install.add_argument("--version")
    pkg_install.add_argument("--online", action="store_true", help="Install from remote registry")
    pkg_install.add_argument("--registry", help="Registry base URL")
    pkg_install.add_argument("--no-deps", action="store_true", help="Do not install package dependencies")
    pkg_install.add_argument("--project-dir", help="Project directory to write mellow.lock into")
    pkg_search = pkg_sub.add_parser("search", help="Search remote registry")
    pkg_search.add_argument("query")
    pkg_search.add_argument("--registry", help="Registry base URL")
    pkg_login = pkg_sub.add_parser("login", help="Save token or login to remote registry")
    pkg_login.add_argument("--token", help="Publish token")
    pkg_login.add_argument("--username")
    pkg_login.add_argument("--password")
    pkg_login.add_argument("--registry", help="Registry base URL")
    pkg_whoami = pkg_sub.add_parser("whoami", help="Show current registry identity")
    pkg_whoami.add_argument("--registry", help="Registry base URL")
    pkg_registry = pkg_sub.add_parser("registry", help="Configure default registry URL")
    pkg_registry.add_argument("url")
    pkg_list = pkg_sub.add_parser("list", help="List installed packages")
    pkg_build = pkg_sub.add_parser("build", help="Build .mpkg archive")
    pkg_build.add_argument("dir")
    pkg_build.add_argument("--out")
    pkg_seed = pkg_sub.add_parser("seed-core", help="Generate core starter packages for Mellow")
    pkg_seed.add_argument("dir")
    pkg_seed.add_argument("--publish-local", action="store_true", help="Publish generated packages into the local registry")
    pkg_sync = pkg_sub.add_parser("sync-imports", help="Resolve project imports and write mellow.lock")
    pkg_sync.add_argument("dir")
    pkg_sync.add_argument("--registry", help="Registry base URL")
    pkg_serve = pkg_sub.add_parser("serve", help="Run local registry server")
    pkg_serve.add_argument("--host", default="127.0.0.1")
    pkg_serve.add_argument("--port", type=int, default=8089)
    pkg_serve.add_argument("--data-dir", default="mellow_registry_data")

    pinstall = sub.add_parser("install", help="Install package from registry (pip-style)")
    pinstall.add_argument("name")
    pinstall.add_argument("--version")
    pinstall.add_argument("--registry", help="Registry base URL")
    pinstall.add_argument("--no-deps", action="store_true", help="Do not install package dependencies")
    pinstall.add_argument("--project-dir", help="Project directory to write mellow.lock into")

    padd = sub.add_parser("add", help="Add dependency to project manifest and install it")
    padd.add_argument("name")
    padd.add_argument("--version")
    padd.add_argument("--registry", help="Registry base URL")
    padd.add_argument("--project-dir", default=".")
    padd.add_argument("--no-deps", action="store_true")
    padd.add_argument("--alias", help="Install alias to remember for this package")
    padd.add_argument("--interactive", action="store_true", help="Interactively choose from namespace suggestions")

    prem = sub.add_parser("remove", help="Remove dependency from project manifest and uninstall it")
    prem.add_argument("name")
    prem.add_argument("--project-dir", default=".")

    pdiag = sub.add_parser("diagnose-imports", help="Show import diagnostics and package suggestions")
    pdiag.add_argument("dir")
    pdiag.add_argument("--registry", help="Registry base URL")

    psearch = sub.add_parser("search", help="Search public registry")
    psearch.add_argument("query")
    psearch.add_argument("--registry", help="Registry base URL")
    psearch.add_argument("--interactive", action="store_true", help="Prompt to pick a package from results")

    ppublish = sub.add_parser("publish", help="Publish package to registry")
    ppublish.add_argument("dir")
    ppublish.add_argument("--registry", help="Registry base URL")
    ppublish.add_argument("--token", help="Publish token; otherwise uses saved token or MELLOW_PUBLISH_TOKEN")

    pseed = sub.add_parser("seed-core", help="Generate recommended starter packages for Mellow")
    pseed.add_argument("dir")
    pseed.add_argument("--publish-local", action="store_true", help="Publish generated packages into the local registry")
    psync = sub.add_parser("sync-imports", help="Resolve imports, install missing dependencies, and write mellow.lock")
    psync.add_argument("dir")
    psync.add_argument("--registry", help="Registry base URL")

    plogin = sub.add_parser("login", help="Save a publish token for the registry")
    plogin.add_argument("--token", help="Publish token to save")
    plogin.add_argument("--username")
    plogin.add_argument("--password")
    plogin.add_argument("--registry", help="Registry base URL")

    pwho = sub.add_parser("whoami", help="Show current registry identity")
    pwho.add_argument("--registry", help="Registry base URL")

    preg = sub.add_parser("registry", help="Configure default registry URL")
    preg.add_argument("url")

    plogout = sub.add_parser("logout", help="Remove saved auth token for a registry")
    plogout.add_argument("--registry", help="Registry base URL")

    pp = sub.add_parser("pack", help="Package a script (game/mod bundle)")
    pp.add_argument("entry", help="Entry .mellow file")
    pp.add_argument("--out", default="dist/mellow_pack.zip")
    pp.add_argument("--include", action="append", default=[], help="Extra paths to include")
    pp.add_argument("--name", default="mellow-pack")
    pp.add_argument("--version", default=__version__)

    pc = sub.add_parser("check", help="Check a script")
    pc.add_argument("file")
    pc.add_argument("--json", action="store_true")
    pd = sub.add_parser("doctor", help="Check installation and environment")
    pd.add_argument("--json", action="store_true")
    pd.add_argument("--strict", action="store_true", help="Exit with code 1 when install/version mismatch is detected")

    pn = sub.add_parser("native", help="Inspect or build the native Mellow VM")
    pn_sub = pn.add_subparsers(dest="native_cmd")
    pn_status = pn_sub.add_parser("status", help="Show native VM status")
    pn_status.add_argument("--json", action="store_true")
    pn_build = pn_sub.add_parser("build", help="Build the native VM extension in place")
    pn_build.add_argument("--json", action="store_true")
    pn_doctor = pn_sub.add_parser("doctor", help="Native VM diagnostics")
    pn_doctor.add_argument("--json", action="store_true")

    psr = sub.add_parser("standalone", help="Build or run the standalone Mellow VM runtime")
    psr_sub = psr.add_subparsers(dest="standalone_cmd")
    psr_status = psr_sub.add_parser("status", help="Show standalone runtime status")
    psr_status.add_argument("--json", action="store_true")
    psr_build = psr_sub.add_parser("build", help="Build the standalone runtime executable")
    psr_build.add_argument("--json", action="store_true")
    psr_build.add_argument("--build-dir")
    psr_doctor = psr_sub.add_parser("doctor", help="Standalone runtime diagnostics")
    psr_doctor.add_argument("--json", action="store_true")
    psr_compile = psr_sub.add_parser("compile", help="Compile .mellow source to standalone image (.mvi)")
    psr_compile.add_argument("input")
    psr_compile.add_argument("-o", "--out")
    psr_compile.add_argument("--json", action="store_true")
    psr_compile.add_argument("--no-optimize", action="store_true")
    psr_run = psr_sub.add_parser("run", help="Run a standalone image via the standalone Mellow VM")
    psr_run.add_argument("image")
    psr_run.add_argument("--binary")
    psr_run.add_argument("--json", action="store_true")

    pe = sub.add_parser("explain", help="Explain an error id")
    pe.add_argument("error_id", help="Example: E001")
    pe.add_argument("--json", action="store_true")

    pa = sub.add_parser("assistant", help="Mellow Code Assistant (summary + hints)")
    pa.add_argument("file")
    pa.add_argument("--mode", choices=["summary", "diagnose"], default="summary")
    pa.add_argument("--json", action="store_true")

    pf = sub.add_parser("fmt", help="Format files")
    pf.add_argument("files", nargs="+")
    pf.add_argument("-w", "--write", action="store_true")
    pf.add_argument("--check", action="store_true")

    pi = sub.add_parser("init", help="Create project from template")
    pi.add_argument("dir")
    pi.add_argument("--force", action="store_true")

    pnw = sub.add_parser("new", help="Scaffold a new Mellow project with starter packages")
    pnw.add_argument("dir")
    pnw.add_argument("--force", action="store_true")
    pnw.add_argument("--no-core", action="store_true", help="Do not preload starter core packages")
    pnw.add_argument("--preset", default="starter")

    pdesk = sub.add_parser("desktop", help="Desktop/window host for Mellow app presets")
    pdesk_sub = pdesk.add_subparsers(dest="desktop_cmd")
    pdesk_run = pdesk_sub.add_parser("run", help="Open a desktop window from a .mel file")
    pdesk_run.add_argument("file")
    pdesk_run.add_argument("--dump-spec", action="store_true")
    pdesk_build = pdesk_sub.add_parser("build", help="Build a portable desktop app bundle (no PyInstaller)")
    pdesk_build.add_argument("file")
    pdesk_build.add_argument("--out", default="dist/desktop")
    pdesk_build.add_argument("--name")
    pdesk_build.add_argument("--onefile", action="store_true")
    pdesk_build.add_argument("--console", action="store_true")
    pdesk_build.add_argument("--json", action="store_true")
    pdesk_status = pdesk_sub.add_parser("status", help="Show desktop host availability")
    pdesk_status.add_argument("--json", action="store_true")

    pmmg = sub.add_parser("mmg", help="Mellow Magic Graphics runtime")
    pmmg_sub = pmmg.add_subparsers(dest="mmg_cmd")
    pmmg_run = pmmg_sub.add_parser("run", help="Open a MMG canvas from a .mel file")
    pmmg_run.add_argument("file")
    pmmg_run.add_argument("--dump-spec", action="store_true")
    pmmg_run_native = pmmg_sub.add_parser("run-native", help="Run MMG through the native SDL2/OpenGL backend")
    pmmg_run_native.add_argument("file")
    pmmg_run_native.add_argument("--build-if-missing", action="store_true")
    pmmg_run_native.add_argument("--keep-scene", action="store_true")
    pmmg_run_native.add_argument("--scene-out")
    pmmg_export_native = pmmg_sub.add_parser("export-native", help="Export a .mel file to a native .mmgscene command file")
    pmmg_export_native.add_argument("file")
    pmmg_export_native.add_argument("-o", "--out", required=True)
    pmmg_build_native = pmmg_sub.add_parser("build-native", help="Build the native MMG SDL2/OpenGL backend")
    pmmg_build_native.add_argument("--json", action="store_true")
    pmmg_status = pmmg_sub.add_parser("status", help="Show MMG runtime availability")
    pmmg_status.add_argument("--json", action="store_true")

    psm = sub.add_parser("sm", help="Mellow Smallless reversible compression")
    psm_sub = psm.add_subparsers(dest="sm_cmd")
    psm_pack = psm_sub.add_parser("pack", help="Compress a text file into .sm")
    psm_pack.add_argument("input")
    psm_pack.add_argument("-o", "--out")
    psm_pack.add_argument("--json", action="store_true")
    psm_unpack = psm_sub.add_parser("unpack", help="Restore a .sm file")
    psm_unpack.add_argument("input")
    psm_unpack.add_argument("-o", "--out")
    psm_unpack.add_argument("--json", action="store_true")
    psm_inspect = psm_sub.add_parser("inspect", help="Inspect a .sm file")
    psm_inspect.add_argument("input")
    psm_inspect.add_argument("--json", action="store_true")

    pmelv = sub.add_parser("melv", help="Mellow video container tools")
    pmelv_sub = pmelv.add_subparsers(dest="melv_cmd")
    pmelv_encode = pmelv_sub.add_parser("encode", help="Encode a video file into .melv")
    pmelv_encode.add_argument("input")
    pmelv_encode.add_argument("-o", "--out", required=True)
    pmelv_encode.add_argument("--fps", type=float)
    pmelv_encode.add_argument("--max-frames", type=int)
    pmelv_encode.add_argument("--json", action="store_true")
    pmelv_decode = pmelv_sub.add_parser("decode", help="Decode a .melv file back to a video")
    pmelv_decode.add_argument("input")
    pmelv_decode.add_argument("-o", "--out", required=True)
    pmelv_decode.add_argument("--json", action="store_true")
    pmelv_extract = pmelv_sub.add_parser("extract", help="Extract frames from a .melv file")
    pmelv_extract.add_argument("input")
    pmelv_extract.add_argument("-o", "--out", required=True)
    pmelv_extract.add_argument("--json", action="store_true")
    pmelv_inspect = pmelv_sub.add_parser("inspect", help="Inspect a .melv file")
    pmelv_inspect.add_argument("input")
    pmelv_inspect.add_argument("--json", action="store_true")

    pm = sub.add_parser("modules", help="List allowed host modules")
    pm.add_argument("--json", action="store_true")

    pagent = sub.add_parser("agent", help="AI-native agent runtime")
    pagent.set_defaults(_agent_help_parser=pagent)
    agent_sub = pagent.add_subparsers(dest="agent_cmd")
    pa_run = agent_sub.add_parser("run", help="Run a single agent task")
    pa_run.add_argument("--task", required=True)
    pa_run.add_argument("--model", default="rule-based")
    pa_run.add_argument("--memory", default=".mellow/agent_memory.jsonl")
    pa_run.add_argument("--obs", default=".mellow/agent_observability.jsonl")
    pa_run.add_argument("--tool", dest="tools", action="append", default=[])
    pa_run.add_argument("--allow-tool", dest="allow_tools", action="append", default=[])
    pa_run.add_argument("--deny-tool", dest="deny_tools", action="append", default=[])
    pa_run.add_argument("--rag-file")
    pa_run.add_argument("--prompt-file")
    pa_run.add_argument("--tool-manifest")
    pa_run.add_argument("--package")
    pa_run.add_argument("--sandbox", action="store_true")
    pa_run.add_argument("--allow-cap", dest="allow_caps", action="append", default=[])
    pa_run.add_argument("--deny-cap", dest="deny_caps", action="append", default=[])
    pa_run.add_argument("--secret", dest="secrets", action="append", default=[])
    pa_run.add_argument("--timeout-ms", type=int)
    pa_run.add_argument("--debug", action="store_true")
    pa_run.add_argument("--policy-file")
    pa_run.add_argument("--policy-key")
    pa_run.add_argument("--structured", choices=["auto", "text"], default="auto")
    pa_run.add_argument("--json", action="store_true")

    pa_workflow = agent_sub.add_parser("workflow", help="Run a built-in agent workflow")
    pa_workflow.add_argument("--task", required=True)
    pa_workflow.add_argument("--model", default="rule-based")
    pa_workflow.add_argument("--memory", default=".mellow/agent_memory.jsonl")
    pa_workflow.add_argument("--obs", default=".mellow/agent_observability.jsonl")
    pa_workflow.add_argument("--rag-file")
    pa_workflow.add_argument("--package")
    pa_workflow.add_argument("--sandbox", action="store_true")
    pa_workflow.add_argument("--allow-cap", dest="allow_caps", action="append", default=[])
    pa_workflow.add_argument("--deny-cap", dest="deny_caps", action="append", default=[])
    pa_workflow.add_argument("--secret", dest="secrets", action="append", default=[])
    pa_workflow.add_argument("--retries", type=int, default=1)
    pa_workflow.add_argument("--timeout-ms", type=int, default=2000)
    pa_workflow.add_argument("--parallel", action="store_true")
    pa_workflow.add_argument("--debug", action="store_true")
    pa_workflow.add_argument("--policy-file")
    pa_workflow.add_argument("--policy-key")
    pa_workflow.add_argument("--json", action="store_true")

    pa_demo = agent_sub.add_parser("demo", help="Print a concise Mellow 1.7 feature overview")
    pa_demo.add_argument("--json", action="store_true")

    pa_inspect = agent_sub.add_parser("inspect-log", help="Inspect an observability log")
    pa_inspect.add_argument("path")
    pa_inspect.add_argument("--json", action="store_true")

    pa_trace = agent_sub.add_parser("trace", help="Summarize an observability log")
    pa_trace.add_argument("path")
    pa_trace.add_argument("--json", action="store_true")

    pa_preview = agent_sub.add_parser("preview", help="Preview an agent package")
    pa_preview.add_argument("ref")
    pa_preview.add_argument("--json", action="store_true")

    pa_pdebug = agent_sub.add_parser("prompt-debug", help="Render and inspect a prompt file")
    pa_pdebug.add_argument("path")
    pa_pdebug.add_argument("--task", default="demo task")
    pa_pdebug.add_argument("--json", action="store_true")

    pplay = sub.add_parser("playground", help="Run the Mellow code playground UI")
    pplay.add_argument("--host", default="127.0.0.1")
    pplay.add_argument("--port", type=int, default=8765)
    pplay.add_argument("--build-only", action="store_true", help="Write static playground assets without starting the server")
    pplay.add_argument("--out", default=".mellow/playground", help="Output directory for static assets")
    pplay.add_argument("--json", action="store_true")

    pa_play = agent_sub.add_parser("playground", help="Generate or serve a local playground")
    pa_play.add_argument("--out", default=".mellow/playground/index.html")
    pa_play.add_argument("--serve", action="store_true")
    pa_play.add_argument("--port", type=int, default=8765)
    pa_play.add_argument("--json", action="store_true")

    pa_serve = agent_sub.add_parser("serve", help="Serve an agent package over HTTP")
    pa_serve.add_argument("--package")
    pa_serve.add_argument("--deployment-manifest")
    pa_serve.add_argument("--host", default="127.0.0.1")
    pa_serve.add_argument("--port", type=int, default=8787)
    pa_serve.add_argument("--json", action="store_true")

    pa_market = agent_sub.add_parser("marketplace", help="Browse local or remote agent marketplace results")
    pa_market.add_argument("query", nargs='?', default="agent")
    pa_market.add_argument("--online", action="store_true")
    pa_market.add_argument("--registry")
    pa_market.add_argument("--json", action="store_true")

    pa_deploy = agent_sub.add_parser("deploy", help="Create a deployment bundle for an agent package")
    pa_deploy.add_argument("ref")
    pa_deploy.add_argument("--out", default=".mellow/deploy")
    pa_deploy.add_argument("--public-url")
    pa_deploy.add_argument("--host")
    pa_deploy.add_argument("--port", type=int)
    pa_deploy.add_argument("--target", choices=["local-http", "docker", "cloudflare-workers", "vercel"], default="local-http")
    pa_deploy.add_argument("--control-plane")
    pa_deploy.add_argument("--json", action="store_true")

    pa_cp = agent_sub.add_parser("control-plane", help="Manage local or remote hosted deployment state")
    cp_sub = pa_cp.add_subparsers(dest="agent_cp_cmd")
    pa_cp_reg = cp_sub.add_parser("register", help="Register a deployment manifest in the local control plane state")
    pa_cp_reg.add_argument("manifest")
    pa_cp_reg.add_argument("--bundle-dir", default=".")
    pa_cp_reg.add_argument("--control-plane")
    pa_cp_reg.add_argument("--revision-notes")
    pa_cp_reg.add_argument("--json", action="store_true")
    pa_cp_sync = cp_sub.add_parser("sync", help="Sync a deployment bundle to a local or remote control plane")
    pa_cp_sync.add_argument("manifest")
    pa_cp_sync.add_argument("--bundle-dir", default=".")
    pa_cp_sync.add_argument("--control-plane")
    pa_cp_sync.add_argument("--token")
    pa_cp_sync.add_argument("--revision-notes")
    pa_cp_sync.add_argument("--json", action="store_true")
    pa_cp_ls = cp_sub.add_parser("list", help="List known hosted deployments")
    pa_cp_ls.add_argument("--control-plane")
    pa_cp_ls.add_argument("--token")
    pa_cp_ls.add_argument("--json", action="store_true")
    pa_cp_status = cp_sub.add_parser("status", help="Show hosted deployment status")
    pa_cp_status.add_argument("ref")
    pa_cp_status.add_argument("--control-plane")
    pa_cp_status.add_argument("--token")
    pa_cp_status.add_argument("--json", action="store_true")
    pa_cp_rev = cp_sub.add_parser("revisions", help="List revisions for a hosted deployment")
    pa_cp_rev.add_argument("ref")
    pa_cp_rev.add_argument("--control-plane")
    pa_cp_rev.add_argument("--token")
    pa_cp_rev.add_argument("--json", action="store_true")
    pa_cp_roll = cp_sub.add_parser("rollout", help="Promote a deployment revision")
    pa_cp_roll.add_argument("ref")
    pa_cp_roll.add_argument("--revision", type=int, required=True)
    pa_cp_roll.add_argument("--canary-percent", type=int)
    pa_cp_roll.add_argument("--control-plane")
    pa_cp_roll.add_argument("--token")
    pa_cp_roll.add_argument("--json", action="store_true")
    pa_cp_health = cp_sub.add_parser("health", help="Run deployment health checks")
    pa_cp_health.add_argument("ref")
    pa_cp_health.add_argument("--control-plane")
    pa_cp_health.add_argument("--token")
    pa_cp_health.add_argument("--json", action="store_true")
    pa_cp_traffic = cp_sub.add_parser("traffic", help="Update stable/canary traffic split")
    pa_cp_traffic.add_argument("ref")
    pa_cp_traffic.add_argument("--stable", type=int, required=True)
    pa_cp_traffic.add_argument("--canary", type=int, required=True)
    pa_cp_traffic.add_argument("--control-plane")
    pa_cp_traffic.add_argument("--token")
    pa_cp_traffic.add_argument("--json", action="store_true")
    pa_cp_rollback = cp_sub.add_parser("rollback", help="Rollback a deployment")
    pa_cp_rollback.add_argument("ref")
    pa_cp_rollback.add_argument("--revision", type=int)
    pa_cp_rollback.add_argument("--control-plane")
    pa_cp_rollback.add_argument("--token")
    pa_cp_rollback.add_argument("--json", action="store_true")

    pa_cp_metrics = cp_sub.add_parser("metrics", help="Record or inspect deployment metrics")
    pa_cp_metrics.add_argument("ref")
    pa_cp_metrics.add_argument("--cpu", type=float)
    pa_cp_metrics.add_argument("--memory", type=float)
    pa_cp_metrics.add_argument("--rps", type=float)
    pa_cp_metrics.add_argument("--p95-ms", dest="p95_ms", type=float)
    pa_cp_metrics.add_argument("--error-rate", dest="error_rate", type=float)
    pa_cp_metrics.add_argument("--replicas", type=int)
    pa_cp_metrics.add_argument("--queued-requests", dest="queued_requests", type=int)
    pa_cp_metrics.add_argument("--in-flight", dest="in_flight", type=int)
    pa_cp_metrics.add_argument("--control-plane")
    pa_cp_metrics.add_argument("--token")
    pa_cp_metrics.add_argument("--json", action="store_true")
    pa_cp_signals = cp_sub.add_parser("signals", help="Show autoscaling signals for a deployment")
    pa_cp_signals.add_argument("ref")
    pa_cp_signals.add_argument("--control-plane")
    pa_cp_signals.add_argument("--token")
    pa_cp_signals.add_argument("--json", action="store_true")
    pa_cp_alert_rules = cp_sub.add_parser("alert-rules", help="Set or inspect deployment alert rules")
    pa_cp_alert_rules.add_argument("ref")
    pa_cp_alert_rules.add_argument("--file")
    pa_cp_alert_rules.add_argument("--control-plane")
    pa_cp_alert_rules.add_argument("--token")
    pa_cp_alert_rules.add_argument("--json", action="store_true")
    pa_cp_alerts = cp_sub.add_parser("alerts", help="Evaluate deployment alert rules")
    pa_cp_alerts.add_argument("ref")
    pa_cp_alerts.add_argument("--control-plane")
    pa_cp_alerts.add_argument("--token")
    pa_cp_alerts.add_argument("--json", action="store_true")

    pa_secret = agent_sub.add_parser("secret", help="Manage agent secrets")
    secret_sub = pa_secret.add_subparsers(dest="agent_secret_cmd")
    pa_secret_set = secret_sub.add_parser("set", help="Set a secret")
    pa_secret_set.add_argument("name")
    pa_secret_set.add_argument("value")
    pa_secret_set.add_argument("--scope", dest="scopes", action="append", default=[])
    pa_secret_set.add_argument("--description")
    pa_secret_set.add_argument("--json", action="store_true")
    pa_secret_rm = secret_sub.add_parser("remove", help="Remove a secret")
    pa_secret_rm.add_argument("name")
    pa_secret_rm.add_argument("--json", action="store_true")
    pa_secret_ls = secret_sub.add_parser("list", help="List stored secrets")
    pa_secret_ls.add_argument("--json", action="store_true")


    pa_sched = agent_sub.add_parser("schedule", help="Manage scheduled agent jobs")
    sched_sub = pa_sched.add_subparsers(dest="agent_sched_cmd")
    pa_sched_add = sched_sub.add_parser("add", help="Add a cron-scheduled agent job")
    pa_sched_add.add_argument("--name", required=True)
    pa_sched_add.add_argument("--cron", required=True)
    pa_sched_add.add_argument("--task", required=True)
    pa_sched_add.add_argument("--kind", choices=["run", "workflow"], default="run")
    pa_sched_add.add_argument("--package")
    pa_sched_add.add_argument("--model", default="rule-based")
    pa_sched_add.add_argument("--memory", default=".mellow/agent_memory.jsonl")
    pa_sched_add.add_argument("--obs", default=".mellow/agent_observability.jsonl")
    pa_sched_add.add_argument("--rag-file")
    pa_sched_add.add_argument("--retries", type=int, default=1)
    pa_sched_add.add_argument("--timeout-ms", type=int)
    pa_sched_add.add_argument("--parallel", action="store_true")
    pa_sched_add.add_argument("--sandbox", action="store_true")
    pa_sched_add.add_argument("--allow-cap", dest="allow_caps", action="append", default=[])
    pa_sched_add.add_argument("--secret", dest="secrets", action="append", default=[])
    pa_sched_add.add_argument("--backoff", choices=["fixed", "exponential", "jitter"], default="fixed")
    pa_sched_add.add_argument("--backoff-delay-ms", type=int, default=0)
    pa_sched_add.add_argument("--backoff-max-ms", type=int, default=30000)
    pa_sched_add.add_argument("--json", action="store_true")
    pa_sched_list = sched_sub.add_parser("list", help="List scheduled jobs")
    pa_sched_list.add_argument("--json", action="store_true")
    pa_sched_due = sched_sub.add_parser("run-due", help="Run all jobs due right now")
    pa_sched_due.add_argument("--json", action="store_true")

    pa_runner = agent_sub.add_parser("runner", help="Run scheduled jobs in a background-style loop")
    runner_sub = pa_runner.add_subparsers(dest="agent_runner_cmd")
    pa_runner_start = runner_sub.add_parser("start", help="Start the runner loop")
    pa_runner_start.add_argument("--interval-s", type=float, default=1.0)
    pa_runner_start.add_argument("--iterations", type=int, default=1)
    pa_runner_start.add_argument("--queue-backed", action="store_true")
    pa_runner_start.add_argument("--queue-limit", type=int)
    pa_runner_start.add_argument("--workers", type=int, default=1)
    pa_runner_start.add_argument("--json", action="store_true")
    pa_runner_status = runner_sub.add_parser("status", help="Show runner status")
    pa_runner_status.add_argument("--json", action="store_true")

    pa_trigger = agent_sub.add_parser("trigger", help="Manage event triggers")
    trigger_sub = pa_trigger.add_subparsers(dest="agent_trigger_cmd")
    pa_trigger_add = trigger_sub.add_parser("add", help="Add an event trigger")
    pa_trigger_add.add_argument("--name", required=True)
    pa_trigger_add.add_argument("--event", required=True)
    pa_trigger_add.add_argument("--task", required=True)
    pa_trigger_add.add_argument("--kind", choices=["run", "workflow"], default="run")
    pa_trigger_add.add_argument("--package")
    pa_trigger_add.add_argument("--model", default="rule-based")
    pa_trigger_add.add_argument("--memory", default=".mellow/agent_memory.jsonl")
    pa_trigger_add.add_argument("--obs", default=".mellow/agent_observability.jsonl")
    pa_trigger_add.add_argument("--rag-file")
    pa_trigger_add.add_argument("--retries", type=int, default=1)
    pa_trigger_add.add_argument("--timeout-ms", type=int)
    pa_trigger_add.add_argument("--parallel", action="store_true")
    pa_trigger_add.add_argument("--sandbox", action="store_true")
    pa_trigger_add.add_argument("--allow-cap", dest="allow_caps", action="append", default=[])
    pa_trigger_add.add_argument("--secret", dest="secrets", action="append", default=[])
    pa_trigger_add.add_argument("--filter", dest="filters", action="append", default=[])
    pa_trigger_add.add_argument("--backoff", choices=["fixed", "exponential", "jitter"], default="fixed")
    pa_trigger_add.add_argument("--backoff-delay-ms", type=int, default=0)
    pa_trigger_add.add_argument("--backoff-max-ms", type=int, default=30000)
    pa_trigger_add.add_argument("--json", action="store_true")
    pa_trigger_list = trigger_sub.add_parser("list", help="List event triggers")
    pa_trigger_list.add_argument("--json", action="store_true")
    pa_trigger_emit = trigger_sub.add_parser("emit", help="Emit an event and enqueue matching jobs")
    pa_trigger_emit.add_argument("event")
    pa_trigger_emit.add_argument("--payload")
    pa_trigger_emit.add_argument("--json", action="store_true")

    pa_webhook = agent_sub.add_parser("webhook", help="Manage webhook-triggered jobs")
    webhook_sub = pa_webhook.add_subparsers(dest="agent_webhook_cmd")
    pa_webhook_add = webhook_sub.add_parser("add", help="Create a webhook job")
    pa_webhook_add.add_argument("--name", required=True)
    pa_webhook_add.add_argument("--event", required=True)
    pa_webhook_add.add_argument("--task", required=True)
    pa_webhook_add.add_argument("--token")
    pa_webhook_add.add_argument("--kind", choices=["run", "workflow"], default="run")
    pa_webhook_add.add_argument("--package")
    pa_webhook_add.add_argument("--model", default="rule-based")
    pa_webhook_add.add_argument("--memory", default=".mellow/agent_memory.jsonl")
    pa_webhook_add.add_argument("--obs", default=".mellow/agent_observability.jsonl")
    pa_webhook_add.add_argument("--rag-file")
    pa_webhook_add.add_argument("--retries", type=int, default=1)
    pa_webhook_add.add_argument("--timeout-ms", type=int)
    pa_webhook_add.add_argument("--parallel", action="store_true")
    pa_webhook_add.add_argument("--sandbox", action="store_true")
    pa_webhook_add.add_argument("--allow-cap", dest="allow_caps", action="append", default=[])
    pa_webhook_add.add_argument("--secret", dest="secrets", action="append", default=[])
    pa_webhook_add.add_argument("--backoff", choices=["fixed", "exponential", "jitter"], default="fixed")
    pa_webhook_add.add_argument("--backoff-delay-ms", type=int, default=0)
    pa_webhook_add.add_argument("--backoff-max-ms", type=int, default=30000)
    pa_webhook_add.add_argument("--json", action="store_true")
    pa_webhook_list = webhook_sub.add_parser("list", help="List webhook jobs")
    pa_webhook_list.add_argument("--json", action="store_true")
    pa_webhook_recv = webhook_sub.add_parser("receive", help="Receive a webhook payload and enqueue matching jobs")
    pa_webhook_recv.add_argument("name")
    pa_webhook_recv.add_argument("--token")
    pa_webhook_recv.add_argument("--payload")
    pa_webhook_recv.add_argument("--json", action="store_true")
    pa_webhook_serve = webhook_sub.add_parser("serve", help="Start an HTTP webhook server")
    pa_webhook_serve.add_argument("--host", default="127.0.0.1")
    pa_webhook_serve.add_argument("--port", type=int, default=8788)
    pa_webhook_serve.add_argument("--token-header", default="X-Mellow-Webhook-Token")
    pa_webhook_serve.add_argument("--no-job-api", action="store_true")
    pa_webhook_serve.add_argument("--json", action="store_true")
    pa_webhook_status = webhook_sub.add_parser("status", help="Show webhook server status")
    pa_webhook_status.add_argument("--json", action="store_true")

    pa_queue = agent_sub.add_parser("queue", help="Inspect and run queue-backed jobs")
    queue_sub = pa_queue.add_subparsers(dest="agent_queue_cmd")
    pa_queue_list = queue_sub.add_parser("list", help="List queue items")
    pa_queue_list.add_argument("--json", action="store_true")
    pa_queue_run = queue_sub.add_parser("run", help="Drain queued jobs")
    pa_queue_run.add_argument("--limit", type=int)
    pa_queue_run.add_argument("--workers", type=int, default=1)
    pa_queue_run.add_argument("--json", action="store_true")
    pa_queue_stats = queue_sub.add_parser("stats", help="Show queue stats")
    pa_queue_stats.add_argument("--json", action="store_true")
    pa_queue_dlq = queue_sub.add_parser("dead-letter", help="List dead-letter queue items")
    pa_queue_dlq.add_argument("--json", action="store_true")
    pa_queue_retry = queue_sub.add_parser("retry", help="Requeue a dead-letter item")
    pa_queue_retry.add_argument("item_id")
    pa_queue_retry.add_argument("--json", action="store_true")
    pa_queue_log = queue_sub.add_parser("log", help="Show durable queue log")
    pa_queue_log.add_argument("--limit", type=int, default=50)
    pa_queue_log.add_argument("--json", action="store_true")

    pa_jobs = agent_sub.add_parser("jobs", help="Persistent HTTP job API and direct job submission")
    jobs_sub = pa_jobs.add_subparsers(dest="agent_jobs_cmd")
    pa_jobs_submit = jobs_sub.add_parser("submit", help="Submit a job directly into the durable queue")
    pa_jobs_submit.add_argument("--task", required=True)
    pa_jobs_submit.add_argument("--name")
    pa_jobs_submit.add_argument("--kind", choices=["run", "workflow"], default="run")
    pa_jobs_submit.add_argument("--package")
    pa_jobs_submit.add_argument("--model", default="rule-based")
    pa_jobs_submit.add_argument("--memory", default=".mellow/agent_memory.jsonl")
    pa_jobs_submit.add_argument("--obs", default=".mellow/agent_observability.jsonl")
    pa_jobs_submit.add_argument("--rag-file")
    pa_jobs_submit.add_argument("--retries", type=int, default=1)
    pa_jobs_submit.add_argument("--timeout-ms", type=int)
    pa_jobs_submit.add_argument("--parallel", action="store_true")
    pa_jobs_submit.add_argument("--sandbox", action="store_true")
    pa_jobs_submit.add_argument("--allow-cap", dest="allow_caps", action="append", default=[])
    pa_jobs_submit.add_argument("--secret", dest="secrets", action="append", default=[])
    pa_jobs_submit.add_argument("--payload")
    pa_jobs_submit.add_argument("--backoff", choices=["fixed", "exponential", "jitter"], default="fixed")
    pa_jobs_submit.add_argument("--backoff-delay-ms", type=int, default=0)
    pa_jobs_submit.add_argument("--backoff-max-ms", type=int, default=30000)
    pa_jobs_submit.add_argument("--json", action="store_true")
    pa_jobs_list = jobs_sub.add_parser("list", help="List jobs from the durable queue")
    pa_jobs_list.add_argument("--json", action="store_true")
    pa_jobs_get = jobs_sub.add_parser("get", help="Get a job by id")
    pa_jobs_get.add_argument("job_id")
    pa_jobs_get.add_argument("--json", action="store_true")
    pa_jobs_serve = jobs_sub.add_parser("serve", help="Serve the persistent HTTP job API")
    pa_jobs_serve.add_argument("--host", default="127.0.0.1")
    pa_jobs_serve.add_argument("--port", type=int, default=8788)
    pa_jobs_serve.add_argument("--json", action="store_true")
    pa_jobs_status = jobs_sub.add_parser("status", help="Show HTTP job API server status")
    pa_jobs_status.add_argument("--json", action="store_true")

    pa_pkg = agent_sub.add_parser("package", help="Create or run an agent package")
    pkg_sub = pa_pkg.add_subparsers(dest="agent_pkg_cmd")
    pa_pkg_init = pkg_sub.add_parser("init", help="Create a starter agent package")
    pa_pkg_init.add_argument("dir")
    pa_pkg_init.add_argument("--name", default="demo.agent")
    pa_pkg_init.add_argument("--force", action="store_true")
    pa_pkg_run = pkg_sub.add_parser("run", help="Run an agent package")
    pa_pkg_run.add_argument("dir")
    pa_pkg_run.add_argument("--task", required=True)
    pa_pkg_run.add_argument("--json", action="store_true")
    pa_pkg_build = pkg_sub.add_parser("build", help="Build an agent package archive")
    pa_pkg_build.add_argument("dir")
    pa_pkg_build.add_argument("--out")
    pa_pkg_build.add_argument("--signing-key")
    pa_pkg_build.add_argument("--signer")
    pa_pkg_build.add_argument("--lock", action="store_true")
    pa_pkg_build.add_argument("--json", action="store_true")
    pa_pkg_publish = pkg_sub.add_parser("publish", help="Publish an agent package to local or remote registry")
    pa_pkg_publish.add_argument("dir")
    pa_pkg_publish.add_argument("--online", action="store_true")
    pa_pkg_publish.add_argument("--registry")
    pa_pkg_publish.add_argument("--token")
    pa_pkg_publish.add_argument("--signing-key")
    pa_pkg_publish.add_argument("--signer")
    pa_pkg_publish.add_argument("--private", action="store_true")
    pa_pkg_publish.add_argument("--lock", action="store_true")
    pa_pkg_publish.add_argument("--json", action="store_true")
    pa_pkg_install = pkg_sub.add_parser("install", help="Install an agent package from local or remote registry")
    pa_pkg_install.add_argument("name", nargs='?')
    pa_pkg_install.add_argument("--version")
    pa_pkg_install.add_argument("--online", action="store_true")
    pa_pkg_install.add_argument("--registry")
    pa_pkg_install.add_argument("--target-dir")
    pa_pkg_install.add_argument("--verify-key")
    pa_pkg_install.add_argument("--lockfile")
    pa_pkg_install.add_argument("--frozen", action="store_true")
    pa_pkg_install.add_argument("--private", action="store_true")
    pa_pkg_install.add_argument("--json", action="store_true")
    pa_pkg_search = pkg_sub.add_parser("search", help="Search agent packages")
    pa_pkg_search.add_argument("query")
    pa_pkg_search.add_argument("--online", action="store_true")
    pa_pkg_search.add_argument("--registry")
    pa_pkg_search.add_argument("--private", action="store_true")
    pa_pkg_search.add_argument("--json", action="store_true")
    pa_pkg_graph = pkg_sub.add_parser("graph", help="Show agent package dependency graph")
    pa_pkg_graph.add_argument("ref")
    pa_pkg_graph.add_argument("--json", action="store_true")
    pa_pkg_lock = pkg_sub.add_parser("lock", help="Generate an agent lockfile")
    pa_pkg_lock.add_argument("dir")
    pa_pkg_lock.add_argument("--json", action="store_true")
    pa_reg = agent_sub.add_parser("registry", help="Manage agent registry auth")
    reg_sub = pa_reg.add_subparsers(dest="agent_reg_cmd")
    pa_reg_login = reg_sub.add_parser("login", help="Save agent registry token")
    pa_reg_login.add_argument("--registry")
    pa_reg_login.add_argument("--token", required=True)
    pa_reg_login.add_argument("--private", action="store_true")
    pa_reg_login.add_argument("--json", action="store_true")
    pa_reg_logout = reg_sub.add_parser("logout", help="Clear agent registry token")
    pa_reg_logout.add_argument("--registry")
    pa_reg_logout.add_argument("--private", action="store_true")
    pa_reg_logout.add_argument("--json", action="store_true")
    pa_reg_whoami = reg_sub.add_parser("whoami", help="Show saved agent registry auth status")
    pa_reg_whoami.add_argument("--registry")
    pa_reg_whoami.add_argument("--json", action="store_true")

    pa_policy = agent_sub.add_parser("policy", help="Sign or verify capability policies")
    policy_sub = pa_policy.add_subparsers(dest="agent_policy_cmd")
    pa_policy_sign = policy_sub.add_parser("sign", help="Sign a capability policy JSON file")
    pa_policy_sign.add_argument("path")
    pa_policy_sign.add_argument("--key", required=True)
    pa_policy_sign.add_argument("--signer")
    pa_policy_sign.add_argument("--json", action="store_true")
    pa_policy_verify = policy_sub.add_parser("verify", help="Verify a signed capability policy JSON file")
    pa_policy_verify.add_argument("path")
    pa_policy_verify.add_argument("--key", required=True)
    pa_policy_verify.add_argument("--json", action="store_true")

    pa_prompt = agent_sub.add_parser("prompt", help="Render a prompt DSL file")
    pa_prompt.add_argument("path")
    pa_prompt.add_argument("--task", default="demo task")
    pa_prompt.add_argument("--json", action="store_true")

    sub.add_parser("lsp", help="Start language server")
    sub.add_parser("help", help="Show help")

    return p

# ----------------------------
# Command handlers
# ----------------------------


def _find_all_mellow_on_path() -> list[str]:
    seen: list[str] = []
    path_env = os.environ.get("PATH", "")
    if not path_env:
        return seen
    names = ["mellow"]
    if os.name == "nt":
        pathext = [ext.lower() for ext in os.environ.get("PATHEXT", ".EXE;.BAT;.CMD").split(";") if ext]
        names = [f"mellow{ext}" for ext in pathext] + ["mellow"]
    for raw_dir in path_env.split(os.pathsep):
        d = raw_dir.strip().strip('"')
        if not d:
            continue
        for name in names:
            candidate = Path(d) / name
            try:
                if candidate.exists():
                    resolved = str(candidate.resolve())
                    if resolved not in seen:
                        seen.append(resolved)
            except Exception:
                continue
    return seen


def _distribution_version() -> str | None:
    try:
        return importlib_metadata.version("mellowlang")
    except Exception:
        return None


def _read_project_version(project_root: Path | None) -> str | None:
    if not project_root:
        return None
    for name in ("pyproject.toml", "setup.cfg"):
        p = project_root / name
        if not p.exists():
            continue
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        m = re.search(r"(?m)^version\s*=\s*['\"]([^'\"]+)['\"]\s*$", raw)
        if m:
            return m.group(1).strip()
    return None


def _doctor_report() -> dict[str, Any]:
    cfg = pkg_load_config()
    registry = cfg.get("registry") or pkg_get_registry_url()
    cache_count = len(list(PKG_CACHE_ROOT.rglob("*.mpkg"))) if PKG_CACHE_ROOT.exists() else 0
    project_root = _find_project_root(Path.cwd()) or Path.cwd()
    module_file = Path(__file__).resolve()
    module_root = str(module_file.parents[1])
    dist_version = _distribution_version()
    project_version = _read_project_version(project_root)
    path_candidates = _find_all_mellow_on_path()
    first_mellow = shutil.which("mellow")
    checks: list[dict[str, str]] = []
    optional: list[dict[str, Any]] = []

    def add_check(name: str, status: str, detail: str, fix: str | None = None) -> None:
        item = {"name": name, "status": status, "detail": detail}
        if fix:
            item["fix"] = fix
        checks.append(item)

    def add_optional(name: str, module: str, extra: str, purpose: str) -> None:
        available = importlib.util.find_spec(module) is not None
        optional.append({
            "name": name,
            "module": module,
            "extra": extra,
            "purpose": purpose,
            "available": available,
            "status": "ok" if available else "optional",
            "fix": None if available else f"Install with `python -m pip install -e .[{extra}]`.",
        })

    if first_mellow:
        add_check("mellow_on_path", "ok", f"CLI found on PATH: {first_mellow}")
    else:
        add_check("mellow_on_path", "warn", "mellow executable was not found on PATH", "Add your Python Scripts directory to PATH or run `py -m mellowlang.cli.main ...`.")

    if dist_version and dist_version != __version__:
        add_check("installed_distribution", "warn", f"Installed package version is {dist_version}, but imported mellowlang version is {__version__}.", "Reinstall from the current checkout with `pip uninstall mellowlang && pip install -e .` or `pip install .`.")
    elif dist_version:
        add_check("installed_distribution", "ok", f"Installed package version matches imported package ({dist_version}).")
    else:
        add_check("installed_distribution", "warn", "Could not read installed `mellowlang` package metadata.", "If this is a source checkout, reinstall with `pip install -e .`.")

    if project_version and project_version != __version__:
        add_check("project_checkout", "warn", f"Project version in {project_root / 'pyproject.toml'} is {project_version}, but imported mellowlang version is {__version__}.", "Update the package version files or reinstall the project so the CLI and source checkout agree.")
    elif project_version:
        add_check("project_checkout", "ok", f"Project checkout version matches imported package ({project_version}).")

    if len(path_candidates) > 1:
        add_check("path_duplicates", "warn", f"Found multiple `mellow` executables on PATH ({len(path_candidates)}).", "Remove stale installs from PATH or keep only the preferred Python Scripts directory first.")
    else:
        add_check("path_duplicates", "ok", "Only one `mellow` executable was discovered on PATH.")

    try:
        project_root_resolved = project_root.resolve()
    except Exception:
        project_root_resolved = project_root

    if str(module_file).startswith(str(project_root_resolved)) and first_mellow and not str(first_mellow).startswith(str(project_root_resolved)):
        add_check("editable_shadow", "warn", f"Imported source is coming from the current checkout ({module_root}) while the CLI launcher lives elsewhere ({first_mellow}).", "This usually means an editable install or stale launcher mismatch. Reinstall with `pip install -e .` from this checkout.")
    else:
        add_check("editable_shadow", "ok", "CLI launcher and imported package location look consistent enough for this environment.")

    native = native_vm_status()
    if native.get('available'):
        add_check("native_vm", "ok", f"Native VM is loadable: {native.get('extension_path')}")
    elif native.get('extension_exists'):
        add_check("native_vm", "warn", f"Native VM binary exists but is not loadable: {native.get('load_error')}", "Rebuild the extension for this Python using `mellow native build`.")
    else:
        add_check("native_vm", "warn", "Native VM is not built yet.", "Run `mellow native build` after installing a compiler and Python development headers.")

    add_optional("lsp", "pygls", "lsp", "Language Server Protocol support")
    add_optional("security", "cryptography", "security", "signed saves, package signing, and agent policy signing")
    add_optional("network", "websockets", "net", "websocket helpers and network tests")
    add_optional("video", "cv2", "video", "MELV video encode/decode")

    mismatches = [c for c in checks if c["status"] in {"warn", "error"}]
    return {
        "mellow_version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "exe": sys.executable,
        "cwd": str(Path.cwd()),
        "ansi": _supports_ansi(),
        "config_file": str(PKG_CONFIG_FILE),
        "registry": registry,
        "cache_packages": cache_count,
        "installed_packages": len(pkg_list_installed()),
        "scripts_on_path": first_mellow,
        "all_scripts_on_path": path_candidates,
        "project_root": str(project_root),
        "module_file": str(module_file),
        "module_root": module_root,
        "distribution_version": dist_version,
        "project_version": project_version,
        "native_vm": native,
        "optional_features": optional,
        "checks": checks,
        "has_mismatch": bool(mismatches),
    }


def _cmd_doctor(json_out: bool, strict: bool = False) -> int:
    info = _doctor_report()
    try:
        from ..lsp_server import lsp_runtime_status
        lsp_info = lsp_runtime_status()
    except Exception as e:  # pragma: no cover
        lsp_info = {"ready": False, "backend": "error", "error": repr(e)}

    info["lsp_ready"] = bool(lsp_info.get("ready"))
    info["lsp_backend"] = lsp_info.get("backend")
    info["lsp_error"] = lsp_info.get("error")

    checks = list(info.get("checks", []))
    if info["lsp_ready"]:
        checks.append({"name": "lsp_runtime", "status": "ok", "detail": f"LSP backend ready ({info['lsp_backend']})."})
    else:
        detail = info["lsp_error"] or "unknown LSP runtime issue"
        checks.append({
            "name": "lsp_runtime",
            "status": "warn",
            "detail": f"LSP backend is not ready: {detail}",
            "fix": "Install compatible pygls/lsprotocol packages in the same Python environment, then reinstall Mellow with `python -m pip install -e .`."
        })
    info["agent_runtime_ready"] = True
    info["checks"] = checks
    info["has_mismatch"] = any(c.get("status") in {"warn", "error"} for c in checks)

    if json_out:
        _json_print(info)
    else:
        print(f"MellowLang {info['mellow_version']}")
        print("")
        print("Environment")
        print(f"  Python        : {info['python']}")
        print(f"  Platform      : {info['platform']}")
        print(f"  Executable    : {info['exe']}")
        print(f"  CWD           : {info['cwd']}")
        print(f"  Project root  : {info['project_root']}")
        print(f"  ANSI          : {info['ansi']}")
        print("")
        print("Packages")
        print(f"  Registry      : {info['registry']}")
        try:
            who = pkg_whoami_remote(info['registry'])
            if who.get('ok'):
                print(f"  Registry user : {who.get('username')}")
        except Exception:
            pass
        print(f"  Config        : {info['config_file']}")
        print(f"  Installed     : {info['installed_packages']}")
        print(f"  Cache         : {info['cache_packages']}")
        print("")
        print("Runtimes")
        print(f"  Agent runtime : {'ready' if info.get('agent_runtime_ready') else 'not ready'}")
        print(f"  LSP backend   : {info['lsp_backend']}")
        print(f"  LSP ready     : {info['lsp_ready']}")
        if info.get('lsp_error'):
            print(f"  LSP reason    : {info['lsp_error']}")
        print("")
        print("Optional features")
        for feature in info.get("optional_features", []):
            status = "OK" if feature.get("available") else "OPTIONAL"
            print(f"  [{status}] {feature['name']}: {feature['purpose']}")
            if feature.get("fix"):
                print(f"         {feature['fix']}")
        print("")
        print("Checks")
        print(f"  mellow on PATH: {info['scripts_on_path']}")
        if not info['scripts_on_path']:
            print('hint: mellow executable is not on PATH; use `py -m mellowlang.cli.main ...` or add Python Scripts to PATH')
        for check in info['checks']:
            status = check['status']
            icon = {'ok': 'OK', 'warn': 'WARN', 'error': 'ERR'}.get(status, status.upper())
            print(f"  [{icon}] {check['name']}: {check['detail']}")
            if check.get('fix'):
                print(f"         fix: {check['fix']}")
    return 2 if strict and info.get('has_mismatch') else 0

def _cmd_native_status(json_out: bool) -> int:
    info = native_vm_status()
    if json_out:
        _json_print(info)
        return 0 if info.get('available') else 1
    _cli_line('Native Mellow VM status', kind='ok' if info.get('available') else 'warn')
    print(f"Available       : {info.get('available')}")
    print(f"Extension       : {info.get('extension_path')}")
    print(f"Compiler        : {info.get('compiler')}")
    print(f"Python headers  : {info.get('python_include')}")
    print(f"Build ready     : {info.get('build_ready')}")
    if info.get('load_error'):
        print(f"Load error      : {info.get('load_error')}")
    print(f"Build command   : {info.get('build_command')}")
    return 0 if info.get('available') else 1


def _cmd_native_build(json_out: bool) -> int:
    res = build_native_vm(inplace=True)
    if json_out:
        _json_print(res)
        return 0 if res.get('ok') else 1
    if res.get('ok'):
        _cli_line('Native VM built successfully', kind='ok')
    else:
        _cli_line('Native VM build did not complete successfully', kind='warn')
    if res.get('stdout'):
        print(res['stdout'].rstrip())
    if res.get('stderr'):
        print(res['stderr'].rstrip(), file=sys.stderr)
    status = res.get('status') or {}
    print(f"Extension       : {status.get('extension_path')}")
    print(f"Available       : {status.get('available')}")
    return 0 if res.get('ok') else 1


def _cmd_native_doctor(json_out: bool) -> int:
    info = native_vm_status()
    payload = {
        'ok': bool(info.get('available')),
        'status': info,
        'fixes': [],
    }
    fixes = payload['fixes']
    if not info.get('compiler_found'):
        fixes.append('Install a C compiler (gcc, clang, or MSVC Build Tools).')
    if not info.get('python_headers_found'):
        fixes.append('Install Python development headers for your current Python version.')
    if info.get('extension_exists') and info.get('load_error'):
        fixes.append('Rebuild the extension for the exact Python ABI you are using now.')
    if json_out:
        _json_print(payload)
        return 0 if payload['ok'] else 1
    _cli_line('Native Mellow VM doctor', kind='ok' if payload['ok'] else 'warn')
    print(f"OK              : {payload['ok']}")
    for fix in fixes:
        _cli_line(fix, kind='hint')
    return 0 if payload['ok'] else 1


def _cmd_modules(json_out: bool) -> int:
    if json_out:
        _json_print(MODULE_ALLOWLIST)
        return 0
    print("Allowed host modules:")
    for mod in sorted(MODULE_ALLOWLIST.keys()):
        print(f"  - {mod}")
    return 0


def _cmd_explain(error_id: str, json_out: bool) -> int:
    info = explain_error(error_id)
    if not info:
        if json_out:
            _json_print({"ok": False, "error": f"unknown error id: {error_id}"})
        else:
            print(f"unknown error id: {error_id}")
            print("try: mellow explain E001")
        return 2
    if json_out:
        _json_print({"ok": True, **asdict(info)})
        return 0
    print(f"{info.id} - {info.title}")
    print()
    print("What it means:")
    print(f"  {info.what}")
    print("Why it happens:")
    print(f"  {info.why}")
    print("How to fix:")
    print(f"  {info.fix}")
    print()
    print("Bad:")
    print(info.example_bad.strip("\n"))
    print()
    print("Good:")
    print(info.example_good.strip("\n"))
    return 0


def _cmd_assistant(file: str, mode: str, json_out: bool) -> int:
    """Built-in lightweight code assistant.

    This is intentionally deterministic and offline:
      - summary: AST-based outline + hints
      - diagnose: try compile; if ok, print summary + lints count
    """
    from ..assistant import analyze_source, render_human

    p = Path(file)
    if not p.exists():
        if json_out:
            _json_print({"ok": False, "error": f"path not found: {p}"})
        else:
            print(f"error: path not found: {p}")
        return 2

    src = _read_text(p)

    if mode == "diagnose":
        # 1) compile (best signal)
        try:
            Compiler().compile(src, filename=str(p))
        except Exception as e:
            if json_out:
                _json_print({"ok": False, "stage": "compile", "error": str(e)})
            else:
                _print_pretty_error(e, filename=str(p), source_lines=src.splitlines(True))
            return 1

    # 2) AST-based assistant report
    try:
        rep = analyze_source(src, filename=str(p))
    except Exception as e:
        if json_out:
            _json_print({"ok": False, "stage": "assistant", "error": str(e)})
        else:
            print(f"assistant error: {e}")
        return 2

    if mode == "diagnose":
        issues = lint_source(src)
        payload = rep.to_dict()
        payload["lint_issues"] = len(issues)
        if json_out:
            _json_print({"ok": True, **payload})
        else:
            print(render_human(rep), end="")
            if issues:
                print(f"\nLint: {len(issues)} issue(s). Run: mellow check {p}")
        return 0

    # summary
    if json_out:
        _json_print({"ok": True, **rep.to_dict()})
    else:
        print(render_human(rep), end="")
    return 0


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

    print(f"✓ packaged: {out_p}")
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
        print(f"✓ compiled to Python: {out}")
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
        'pipeline': getattr(prog, 'pipeline', 'legacy'),
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
    print(f"✓ compiled to bytecode: {out}")
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

def _cmd_pkg(ns: argparse.Namespace) -> int:
    pkg_cmd = getattr(ns, 'pkg_cmd', None)
    if pkg_cmd == 'init':
        man = pkg_init_package(ns.dir, name=ns.name, entry=ns.entry)
        print(f"✓ package initialized: {Path(ns.dir).resolve()}")
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
        print(res.get('published_to') or pkg_get_registry_url(ns.registry))
        return 0
    if pkg_cmd == 'install':
        res = pkg_install_remote(ns.name, version=ns.version, registry=ns.registry, project_dir=getattr(ns, 'project_dir', None), with_deps=not getattr(ns, 'no_deps', False)) if getattr(ns, 'online', False) else pkg_install_package(ns.name, version=ns.version)
        if 'error' in res:
            _cli_line(str(res['error']), kind='error', file=sys.stderr)
            if res.get('suggestions'):
                _cli_line('Try: ' + ', '.join(res.get('suggestions', [])[:5]), kind='hint', file=sys.stderr)
            return 2
        _cli_line(f"package installed: {res['name']}@{res['version']}", kind='ok')
        print(res['installed_to'])
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
            versions = ','.join(item.get('versions', []))
            print(f"- {item['name']}  latest={item.get('latest')}  versions={versions}")
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
        print(f"✓ logged in as {res.get('username')} -> {res.get('registry')}")
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
        print(f"✓ default registry: {res['registry']}")
        return 0
    if pkg_cmd == 'logout':
        from ..package_manager import clear_auth_token as pkg_clear_auth_token
        res = pkg_clear_auth_token(registry=ns.registry)
        print(f"✓ logged out from {res['registry']}")
        return 0
    if pkg_cmd == 'list':
        rows = pkg_list_installed()
        if not rows:
            print('No packages installed.')
            return 0
        for row in rows:
            print(f"- {row['name']}@{row['version']} -> {row['install_path']}")
        return 0
    if pkg_cmd == 'build':
        res = pkg_build_package_archive(ns.dir, out_path=ns.out)
        print(f"✓ package archive built: {res['archive']}")
        print(f"sha256: {res['sha256']}")
        return 0
    if pkg_cmd == 'seed-core':
        res = pkg_seed_core_packages(ns.dir, publish_local=getattr(ns, 'publish_local', False))
        print(f"✓ core starter packages generated: {res['root']}")
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
        print(f"✓ runtime map written: {res['runtime_map']}")
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
        res = pkg_update_remote(getattr(ns, 'name', None), registry=ns.registry, project_dir=getattr(ns, 'project_dir', '.'))
        if not res.get('ok'):
            print(f"error: {res.get('error', 'update failed')}")
            return 2
        print(f"✓ dependencies updated: {res.get('count', 0)}")
        for item in res.get('updated', []):
            print(f"- {item.get('name')}@{item.get('version')}")
        return 0
    if pkg_cmd == 'uninstall':
        res = pkg_uninstall_package(ns.name, project_dir=getattr(ns, 'project_dir', '.'))
        if not res.get('ok'):
            print(f"error: {res.get('error', 'uninstall failed')}")
            return 2
        print(f"✓ package removed: {res['name']}")
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
        print('✓ import diagnostics ok')
        return 0
    if pkg_cmd == 'serve':
        from ..registry.server import run_registry_server
        run_registry_server(ns.host, ns.port, ns.data_dir)
        return 0
    print('usage: mellow pkg <init|publish|install|add|remove|search|login|whoami|registry|list|build|seed-core|sync-imports|resolve-runtime|diagnose-imports|update|uninstall|serve> ...')
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
    print(f"✓ created project: {dest}")
    return 0


def _cmd_new(dest_dir: str, force: bool, *, with_core: bool = True, preset: str = "starter") -> int:
    res = pkg_scaffold_project(dest_dir, force=force, with_core=with_core, preset=preset)
    if not res.get("ok"):
        print(f"error: {res.get('error', 'project scaffold failed')}")
        return 2
    print(f"✓ created project: {res['project_dir']}")
    print(f"✓ manifest: {res['manifest']}")
    print(f"✓ preset: {res.get('preset', 'starter')}")
    if res.get('preload'):
        installed = []
        for item in res.get('preload', {}).get('installed', []):
            name = item.get('name')
            version = item.get('version')
            row = f"{name}@{version}" if version else str(name)
            if row not in installed:
                installed.append(row)
        if installed:
            print("✓ starter packages: " + ", ".join(installed))
        runtime = (res.get('preload') or {}).get('runtime') or {}
        if runtime.get('runtime_map'):
            print(f"✓ runtime map: {runtime['runtime_map']}")
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
             data_max_record_bytes: int | None = None, data_max_open_streams: int | None = None) -> int:
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

        # permissions can be list[str] (preferred) or dict (legacy)
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
        if project_mode:
            sandbox_root = str(manifest_data.get("sandbox_root") or manifest_data.get("sandbox") or "saves")
            perms = manifest_data.get("permissions")
            read_roots: list[str] = []
            write_roots: list[str] = []
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
                    if t.startswith("fs.read:"):
                        read_roots.append(t.split(":", 1)[1])
                    elif t.startswith("fs.write:"):
                        write_roots.append(t.split(":", 1)[1])
                    elif t.startswith("fs.rw:"):
                        r = t.split(":", 1)[1]
                        read_roots.append(r)
                        write_roots.append(r)
            elif isinstance(perms, dict):
                # legacy
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

def _run_one_script(path: Path, *, engine: str) -> dict[str, Any]:
    import io
    import contextlib

    src = _read_text(path)
    comp = Compiler()
    program = comp.compile(src, filename=str(path))
    vm = MellowVM()
    cfg = RunConfig(engine=engine)

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            result = vm.run(program, config=cfg)
        return {"ok": True, "stdout": buf_out.getvalue(), "stderr": buf_err.getvalue(), "result": result}
    except Exception as e:
        return {"ok": False, "stdout": buf_out.getvalue(), "stderr": buf_err.getvalue(), "error": str(e), "type": e.__class__.__name__}

def _cmd_test(path: str, *, engine: str, pattern: str, json_out: bool) -> int:
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
        if engine == "dual":
            r_py = _run_one_script(f, engine="py")
            r_c = _run_one_script(f, engine="c")
            same, why = compare(r_py, r_c)
            ok = same
            rec = {"file": str(f), "ok": ok, "why": why, "py": r_py, "c": r_c}
        else:
            r = _run_one_script(f, engine=engine)
            ok = bool(r.get("ok"))
            rec = {"file": str(f), "ok": ok, "run": r}
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
    runtime = _make_agent_runtime(model, memory_path, obs_path, allow_tools, deny_tools, rag_file, tool_manifest, sandbox=sandbox, allow_caps=allow_caps, deny_caps=deny_caps, secrets=secrets, signed_policy=signed_policy)
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

    if _argv_prefers_direct_run(argv):
        argv = ["run"] + argv

    if argv and argv[0] not in MODERN_CMDS and not argv[0].startswith('-') and not _looks_like_script_path(argv[0]):
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
            p.print_help()
            return 0

        # dispatch
        if cmd == "modules":
            return _cmd_modules(ns.json)
        if cmd == "check":
            return _cmd_check(ns.file, ns.json)
        if cmd == "doctor":
            return _cmd_doctor(ns.json, getattr(ns, "strict", False))
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
        if cmd == "publish":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="publish", dir=ns.dir, online=True, registry=ns.registry, token=ns.token))
        if cmd == "seed-core":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="seed-core", dir=ns.dir, publish_local=ns.publish_local))
        if cmd == "sync-imports":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="sync-imports", dir=ns.dir, registry=ns.registry))
        if cmd == "resolve-runtime":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="resolve-runtime", dir=ns.dir, registry=ns.registry, strict=getattr(ns, 'strict', False)))
        if cmd == "update":
            return _cmd_pkg(argparse.Namespace(pkg_cmd="update", name=getattr(ns, 'name', None), registry=ns.registry, project_dir=ns.project_dir))
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
            return int(_start_lsp() or 0)
        if cmd == "pack":
            return _cmd_pack(ns.entry, ns.out, ns.include, ns.name, ns.version)
        if cmd == "run":
            return _cmd_run(
                ns.file,
                json_out=ns.json,
                engine=getattr(ns, "engine", "auto"),
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
            )
        if cmd == "test":
            return _cmd_test(
                ns.path,
                engine=getattr(ns, "engine", "auto"),
                pattern=getattr(ns, "pattern", None),
                json_out=ns.json,
            )
        if cmd == "replay":
            return _cmd_replay(
                ns.file,
                replay_path=ns.replay_path,
                engine=getattr(ns, "engine", "auto"),
                json_out=ns.json,
            )
        if cmd == "diff":
            return _cmd_diff(ns.a, ns.b, json_out=ns.json)

        # unknown / future command
        p.print_help()
        return 2



    # modern-command fallback: if the first token looks like a command word,
    # prefer the modern parser so users get proper subcommand handling/errors.
    if argv and not argv[0].startswith('-'):
        try:
            p = _build_modern_parser()
            ns = p.parse_args(argv)
            if getattr(ns, "cmd", None):
                return main(argv=[ns.cmd] + argv[1:])
        except SystemExit:
            # Fall back to legacy parsing for actual script files.
            pass

    # legacy mode
    p = _build_legacy_parser()
    ns = p.parse_args(argv)

    if getattr(ns, "lsp", False):
        return int(_start_lsp() or 0)

    if getattr(ns, "list_modules", False):
        return _cmd_modules(bool(ns.json))

    if not ns.script:
        p.print_help()
        return 2

    if getattr(ns, "check_only", False):
        return _cmd_check(ns.script, bool(ns.json))

    return _cmd_run(
        ns.script,
        json_out=bool(ns.json),
        engine=getattr(ns, "engine", "auto"),
        record_path=getattr(ns, "record_path", None),
        replay_path=getattr(ns, "replay_path", None),
        seed=getattr(ns, "seed", None),
        global_seed=getattr(ns, "global_seed", None),
        allow_ask=getattr(ns, "allow_ask", False),
        no_wait=getattr(ns, "no_wait", False),
        trace=getattr(ns, "trace", False),
        step=getattr(ns, "step", False),
        break_lines=getattr(ns, "break_lines", None),
        watch=getattr(ns, "watch", None),
        ai_timeline=getattr(ns, "ai_timeline", None),
        color=getattr(ns, "color", False),
        no_color=getattr(ns, "no_color", False),
        allow_storage=not getattr(ns, "no_storage", False),
        storage_dir=getattr(ns, "storage_dir", None),
        allow_unsafe_fs=getattr(ns, "unsafe_fs", False),
        max_steps=getattr(ns, "max_steps", None),
        max_ms=getattr(ns, "max_ms", None),
        syscall_budget=getattr(ns, "syscall_budget", None),
        profile=bool(getattr(ns, "profile", False)),
        sandbox_profile=getattr(ns, "sandbox_profile", "default"),
        allow_data_write=getattr(ns, "data_write", False),
        data_max_batch_size=getattr(ns, "data_batch_size", None),
        data_max_query_rows=getattr(ns, "data_max_rows", None),
        data_max_record_bytes=getattr(ns, "data_max_record_bytes", None),
        data_max_open_streams=getattr(ns, "data_max_streams", None),
    )


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
