from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import shutil
import sys
from dataclasses import asdict
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from ... import __version__
from ...compiler import Compiler
from ...error_explain import explain as explain_error
from ...host.modules import MODULE_ALLOWLIST
from ...lint import lint_source
from ..common import (
    _cli_line,
    _find_project_root,
    _json_print,
    _lazy_attr,
    _print_pretty_error,
    _prog,
    _read_text,
    _supports_ansi,
)
from ..ux import (
    MODERN_CMDS,
    answer_cli_question as _answer_cli_question,
    format_guide as _format_guide,
    guide_topics as _guide_topics,
)

_PM = "mellowlang.package_manager"
pkg_load_config = _lazy_attr(_PM, "load_config")
pkg_get_registry_url = _lazy_attr(_PM, "get_registry_url")
pkg_cache_root_path = _lazy_attr(_PM, "cache_root_path")
pkg_config_file_path = _lazy_attr(_PM, "config_file_path")
pkg_list_installed = _lazy_attr(_PM, "list_installed")
pkg_whoami_remote = _lazy_attr(_PM, "whoami_remote")
pkg_save_config = _lazy_attr(_PM, "save_config")
pkg_set_registry = _lazy_attr(_PM, "set_registry")
native_vm_status = _lazy_attr("mellowlang.native_vm", "native_vm_status")
build_native_vm = _lazy_attr("mellowlang.native_vm", "build_native_vm")

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
    cache_root = pkg_cache_root_path()
    config_file = pkg_config_file_path()
    cache_count = len(list(cache_root.rglob("*.mpkg"))) if cache_root.exists() else 0
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
        "config_file": str(config_file),
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
        from ...lsp_server import lsp_runtime_status
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


def _safe_config(cfg: dict[str, Any]) -> dict[str, Any]:
    safe = dict(cfg)
    auth = safe.get("auth")
    if isinstance(auth, dict):
        safe["auth"] = {str(k): "***" for k in auth}
    return safe


def _config_get_value(data: dict[str, Any], key: str | None) -> Any:
    if not key:
        return data
    current: Any = data
    for part in key.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(key)
    return current


def _coerce_config_value(value: str) -> Any:
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower == "null":
        return None
    try:
        return json.loads(value)
    except Exception:
        return value


def _config_set_value(data: dict[str, Any], key: str, value: Any) -> None:
    current: dict[str, Any] = data
    parts = key.split(".")
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def _cmd_status(json_out: bool, strict: bool = False) -> int:
    info = _doctor_report()
    checks = list(info.get("checks", []))
    warnings = sum(1 for check in checks if check.get("status") == "warn")
    errors = sum(1 for check in checks if check.get("status") == "error")
    native = info.get("native_vm") or {}
    payload = {
        "ok": errors == 0 and warnings == 0,
        "mellow_version": info.get("mellow_version"),
        "project_root": info.get("project_root"),
        "registry": info.get("registry"),
        "config_file": info.get("config_file"),
        "installed_packages": info.get("installed_packages"),
        "cache_packages": info.get("cache_packages"),
        "native_vm_available": bool(native.get("available")),
        "warnings": warnings,
        "errors": errors,
        "checks": checks,
    }
    if json_out:
        _json_print(payload)
        return 2 if strict and not payload["ok"] else 0

    _cli_line("Mellow project status", kind="ok" if payload["ok"] else "warn")
    print(f"Version         : {payload['mellow_version']}")
    print(f"Project         : {payload['project_root']}")
    print(f"Registry        : {payload['registry']}")
    print(f"Config          : {payload['config_file']}")
    print(f"Native VM       : {'ready' if payload['native_vm_available'] else 'not ready'}")
    print(f"Packages        : {payload['installed_packages']} installed, {payload['cache_packages']} cached")
    print(f"Checks          : {errors} error(s), {warnings} warning(s)")
    if warnings or errors:
        for check in checks:
            if check.get("status") in {"warn", "error"}:
                print(f"  [{check.get('status', '').upper()}] {check.get('name')}: {check.get('detail')}")
    print("Next            : mellow run <file> | mellow doctor | mellow release-gate")
    return 2 if strict and not payload["ok"] else 0


def _cmd_config(action: str, key: str | None = None, value: str | None = None, json_out: bool = False) -> int:
    if action == "path":
        payload = {"config": str(pkg_config_file_path())}
        if json_out:
            _json_print(payload)
        else:
            print(payload["config"])
        return 0

    cfg = pkg_load_config()
    if action in {"list", None}:
        payload = _safe_config(cfg)
        if json_out:
            _json_print(payload)
        else:
            for name, item in sorted(payload.items()):
                if isinstance(item, (dict, list)):
                    item = json.dumps(item, ensure_ascii=False, sort_keys=True)
                print(f"{name}: {item}")
        return 0

    if action == "get":
        try:
            payload = _config_get_value(_safe_config(cfg), key)
        except KeyError:
            _cli_line(f"config key not found: {key}", kind="error", file=sys.stderr)
            return 2
        if json_out:
            _json_print({"key": key, "value": payload})
        else:
            if isinstance(payload, (dict, list)):
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(payload)
        return 0

    if action == "set":
        if not key or value is None:
            _cli_line("config set requires <key> <value>", kind="error", file=sys.stderr)
            return 2
        if key == "registry":
            result = pkg_set_registry(value)
            payload = {"key": key, "value": result.get("registry"), "config": result.get("config")}
        else:
            typed_value = _coerce_config_value(value)
            _config_set_value(cfg, key, typed_value)
            pkg_save_config(cfg)
            payload = {"key": key, "value": typed_value, "config": str(pkg_config_file_path())}
        if json_out:
            _json_print(payload)
        else:
            print(f"{payload['key']}: {payload['value']}")
        return 0

    _cli_line(f"unknown config command: {action}", kind="error", file=sys.stderr)
    return 2


def _cmd_completion(shell: str) -> int:
    commands = sorted(MODERN_CMDS)
    words = " ".join(commands)
    if shell == "powershell":
        quoted = ", ".join(repr(cmd) for cmd in commands)
        print(f"""$MellowCommands = @({quoted})
Register-ArgumentCompleter -Native -CommandName mellow -ScriptBlock {{
    param($wordToComplete, $commandAst, $cursorPosition)
    $MellowCommands |
        Where-Object {{ $_ -like "$wordToComplete*" }} |
        ForEach-Object {{ [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', "mellow $_") }}
}}""")
        return 0
    if shell == "bash":
        print(f"""_mellow_complete() {{
    local cur="${{COMP_WORDS[COMP_CWORD]}}"
    COMPREPLY=( $(compgen -W "{words}" -- "$cur") )
}}
complete -F _mellow_complete mellow""")
        return 0
    _cli_line(f"unsupported completion shell: {shell}", kind="error", file=sys.stderr)
    return 2


def _cmd_guide(topic: str | None, json_out: bool = False, list_topics: bool = False) -> int:
    prog = _prog()
    if list_topics:
        payload = {"ok": True, "topics": _guide_topics()}
        if json_out:
            _json_print(payload)
        else:
            print("Guide topics:")
            for item in payload["topics"]:
                print(f"  {item}")
        return 0
    topic = topic or "ai"
    if json_out:
        key = topic.lower().strip()
        payload = {
            "ok": True,
            "topic": topic,
            "text": _format_guide(key, prog),
        }
        _json_print(payload)
    else:
        print(_format_guide(topic, prog))
    return 0

def _cmd_ask(question_parts: list[str], json_out: bool = False) -> int:
    question = " ".join(question_parts).strip()
    if not question:
        question = "what can I do"
    payload = _answer_cli_question(question, _prog())
    if json_out:
        _json_print(payload)
    else:
        _cli_line(payload["summary"], kind="info")
        print("Try:")
        for command in payload.get("commands", []):
            print(f"  {command}")
        print(f"Learn more: {payload['next']}")
        print("Mode      : offline CLI helper")
    return 0


def _cmd_bench(rounds: int, json_out: bool) -> int:
    from ...benchmarking import run_benchmarks

    result = run_benchmarks(rounds=rounds)
    if json_out:
        _json_print(result)
        return 0 if result.get("ok") else 1
    _cli_line("Mellow performance benchmark", kind="ok" if result.get("ok") else "warn")
    for suite in result.get("suites", []):
        name = suite.get("name")
        fields = ", ".join(f"{k}={v}" for k, v in suite.items() if k not in {"name", "cache"})
        print(f"  {name}: {fields}")
    return 0 if result.get("ok") else 1


def _cmd_security_audit(include_packages: bool, strict: bool, json_out: bool) -> int:
    from ...security_audit import run_security_audit

    result = run_security_audit(include_packages=include_packages)
    if strict and result.get("warnings"):
        result = dict(result)
        result["ok"] = False
    if json_out:
        _json_print(result)
        return 0 if result.get("ok") else 1
    _cli_line("Mellow security audit", kind="ok" if result.get("ok") else "warn")
    for check in result.get("checks", []):
        status = "OK" if check.get("ok") else check.get("severity", "error").upper()
        print(f"  [{status}] {check.get('name')}: {check.get('detail')}")
    print(f"Errors          : {result.get('errors', 0)}")
    print(f"Warnings        : {result.get('warnings', 0)}")
    return 0 if result.get("ok") else 1


def _cmd_release_gate(rounds: int, json_out: bool) -> int:
    from ...release_gate import run_release_gate

    try:
        result = run_release_gate(rounds=rounds)
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    if json_out:
        _json_print(result)
        return 0 if result.get("ok") else 1
    _cli_line("Mellow release gate", kind="ok" if result.get("ok") else "error")
    if result.get("error"):
        print(f"Error           : {result['error']}")
        return 1
    print(f"Benchmark       : {'pass' if result.get('benchmark', {}).get('ok') else 'fail'}")
    print(f"Sandbox/security: {'pass' if result.get('sandbox', {}).get('ok') else 'fail'}")
    pkg = result.get("package_integrity", {})
    print(f"Package integrity: {'pass' if pkg.get('ok') else 'fail'} ({pkg.get('count', 0)} package(s))")
    stability = result.get("stability", {})
    if stability.get("skipped"):
        print("Stability gates : skipped")
    else:
        print(f"Stability gates : {'pass' if stability.get('ok') else 'fail'}")
    return 0 if result.get("ok") else 1


def _cmd_native_status(json_out: bool) -> int:
    info = native_vm_status()
    if json_out:
        _json_print(info)
        return 0 if info.get('available') else 1
    _cli_line('Native Mellow VM status', kind='ok' if info.get('available') else 'warn')
    print(f"Available       : {info.get('available')}")
    print(f"Extension       : {info.get('extension_path')}")
    print(f"Architecture    : {info.get('normalized_arch')} ({info.get('machine')})")
    print(f"Native backend  : {info.get('native_backend')}")
    print(f"Backends        : {', '.join(info.get('available_native_backends') or [])}")
    print(f"CPU workers     : {info.get('multi_core_workers')}")
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
    cpu = info.get('cpu_profile') or {}
    if cpu.get('normalized_arch') not in {'x86_64', 'arm64'}:
        fixes.append('This CPU uses the portable generic C backend; add an architecture backend before claiming tuned native performance.')
    if json_out:
        _json_print(payload)
        return 0 if payload['ok'] else 1
    _cli_line('Native Mellow VM doctor', kind='ok' if payload['ok'] else 'warn')
    print(f"OK              : {payload['ok']}")
    print(f"Architecture    : {cpu.get('normalized_arch')}")
    print(f"Native backend  : {cpu.get('preferred_backend')}")
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
    from ...assistant import analyze_source, render_human

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
