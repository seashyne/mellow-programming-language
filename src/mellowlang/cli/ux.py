from __future__ import annotations

import difflib
from typing import Any

from .. import __version__


CLI_ALIASES = {
    "r": "run",
    "rec": "record",
    "c": "check",
    "b": "bench",
    "s": "status",
    "g": "guide",
    "ai": "ask",
    "sec": "security",
    "rg": "release-gate",
    "cfg": "config",
}

MODERN_CMDS = {"agent", "ask", "author", "bench", "check", "compile", "completion", "config", "doctor", "explain", "fmt", "guide", "help", "init", "new", "install", "info", "login", "logout", "lsp", "modules", "native", "record", "release-gate", "security", "standalone", "status", "pack", "pkg", "profile", "publish", "registry", "run", "search", "seed-core", "signature", "sync-imports", "resolve-runtime", "trust", "uninstall", "update", "verify", "test", "replay", "diff", "assistant", "whoami", "add", "remove", "diagnose-imports", "playground", "desktop", "mmg", "sm", "melv"}
MODERN_CMDS |= set(CLI_ALIASES)
MODERN_CMDS |= {"doctor", "pack", "explain"}


CLI_GUIDES: dict[str, dict[str, Any]] = {
    "run": {
        "title": "Run a script",
        "use": "Use this when you just want to execute a .mellow file.",
        "commands": ["mellow run app.mellow", "mellow r app.mellow", "mellow app.mellow"],
        "tips": ["Use `mellow check app.mellow` before running in CI.", "Use `--engine py` only when debugging Python fallback behavior."],
    },
    "check": {
        "title": "Check syntax and lint",
        "use": "Use this before commits, release gates, or when the script fails to parse.",
        "commands": ["mellow check app.mellow", "mellow c app.mellow"],
        "tips": ["This does not run the program.", "For full release confidence, run `mellow release-gate`."],
    },
    "record": {
        "title": "Record and replay deterministic runs",
        "use": "Use this when a bug is hard to reproduce or you want a stable run log.",
        "commands": ["mellow record app.mellow replay.jsonl", "mellow replay app.mellow replay.jsonl", "mellow diff old.jsonl new.jsonl"],
        "tips": ["Prefer `record`/`replay` commands over `run --record` for humans.", "`run --record` and `run --replay` still work for scripts."],
    },
    "packages": {
        "title": "Packages",
        "use": "Use packages to share reusable Mellow modules and lock project dependencies.",
        "commands": ["mellow search ui", "mellow install mellow.ui", "mellow add mellow.ui", "mellow verify mellow.ui"],
        "tips": ["Use `add` for projects because it updates the manifest.", "Use `verify` and `trust` for package integrity."],
    },
    "security": {
        "title": "Security and release gates",
        "use": "Use this for AI-era safety checks: sandbox, AI tool default-deny, and package trust.",
        "commands": ["mellow security audit", "mellow sec audit", "mellow release-gate", "mellow rg"],
        "tips": ["Run `release-gate` before publishing a release.", "Use `--json` in CI."],
    },
    "config": {
        "title": "Config",
        "use": "Use this to inspect registry, auth state, and local CLI settings.",
        "commands": ["mellow config list", "mellow cfg get registry", "mellow config path", "mellow registry https://example.com"],
        "tips": ["Auth tokens are masked in `config list`.", "Use `whoami` to check the active registry identity."],
    },
    "ai": {
        "title": "AI help in the CLI",
        "use": "Use this when you know what you want, but not which command to type.",
        "commands": ["mellow ask how do I record a replay", "mellow ask install a package", "mellow guide security"],
        "tips": ["The CLI helper is offline and command-focused.", "For code-level hints, use `mellow assistant <file>`."],
    },
}


def suggest_command(name: str) -> str | None:
    matches = difflib.get_close_matches(name, sorted(MODERN_CMDS), n=1, cutoff=0.5)
    return matches[0] if matches else None


def guide_topics() -> list[str]:
    return sorted(CLI_GUIDES)


def format_guide(topic: str, prog: str) -> str:
    key = topic.lower().strip()
    if key in {"package", "pkg", "install", "add", "search"}:
        key = "packages"
    if key in {"replay", "recording", "determinism"}:
        key = "record"
    if key in {"sec", "audit", "release", "gate"}:
        key = "security"
    if key in {"cfg", "registry"}:
        key = "config"
    if key not in CLI_GUIDES:
        suggestion = difflib.get_close_matches(key, guide_topics(), n=1, cutoff=0.45)
        if suggestion:
            key = suggestion[0]
        else:
            topics = ", ".join(guide_topics())
            return f"Unknown guide topic: {topic}\nAvailable topics: {topics}\nTry: {prog} ask \"what do I need?\""
    guide = CLI_GUIDES[key]
    lines = [guide["title"], "", f"When: {guide['use']}", "", "Commands:"]
    lines.extend(f"  {cmd}" for cmd in guide.get("commands", []))
    tips = guide.get("tips", [])
    if tips:
        lines.append("")
        lines.append("Notes:")
        lines.extend(f"  - {tip}" for tip in tips)
    return "\n".join(lines)


def answer_cli_question(question: str, prog: str) -> dict[str, Any]:
    q = question.lower()
    matches: list[str] = []
    rules = [
        ("record", ("record", "replay", "determin", "log", "bug")),
        ("packages", ("package", "install", "dependency", "module", "registry", "publish")),
        ("security", ("security", "audit", "sandbox", "release", "gate", "safe", "trust")),
        ("config", ("config", "registry", "token", "login", "auth")),
        ("check", ("check", "lint", "syntax", "parse")),
        ("run", ("run", "execute", "start")),
        ("ai", ("ai", "assistant", "help", "ask")),
    ]
    for topic, words in rules:
        if any(word in q for word in words):
            matches.append(topic)
    if not matches:
        matches = ["run", "check", "guide"]
    primary = matches[0]
    if primary == "guide":
        commands = [f"{prog} guide"]
        summary = "Start with the guide topics."
    else:
        commands = CLI_GUIDES.get(primary, CLI_GUIDES["run"]).get("commands", [])[:3]
        summary = CLI_GUIDES.get(primary, CLI_GUIDES["run"]).get("use", "")
    return {
        "ok": True,
        "question": question,
        "best_topic": primary,
        "summary": summary,
        "commands": commands,
        "next": f"{prog} guide {primary}" if primary in CLI_GUIDES else f"{prog} guide",
        "mode": "offline-cli-helper",
    }


def quick_help_text(prog: str) -> str:
    return f"""MellowLang {__version__}

Usage:
  {prog} <file.mellow>          Run a script
  {prog} run <file>             Run a script (alias: r)
  {prog} check <file>           Check syntax/lint (alias: c)
  {prog} record <file> <log>     Record deterministic replay
  {prog} replay <file> <log>     Replay a recorded run
  {prog} status                 Project health summary (alias: s)
  {prog} ask "what to do"        Get command help

Common commands:
  new <dir>        Create a project
  test [path]      Run tests
  bench            Run quick benchmarks
  security audit   Run local security checks
  release-gate     Run benchmark + sandbox + package integrity gates
  install <pkg>    Install a package
  search <query>   Search packages
  config list      Show CLI config
  guide            Learn common workflows
  doctor           Diagnose install/environment

More:
  {prog} help              Show command groups
  {prog} guide record      Learn a workflow
  {prog} help --full       Show every command
  {prog} run -h            Show run options
"""


def modern_help_text(prog: str) -> str:
    return f"""MellowLang {__version__}

Common:
  {prog} run <file>            Run a script (alias: r)
  {prog} check <file>          Lint / syntax check (alias: c)
  {prog} status                Show project readiness at a glance (alias: s)
  {prog} doctor                Check installation and environment
  {prog} new <dir>             Create a project
  {prog} test [path]           Run tests

Build and debug:
  {prog} compile <file>        Compile or inspect IR
  {prog} bench                 Run performance smoke benchmarks (alias: b)
  {prog} release-gate          Run benchmark + sandbox + package integrity gates (alias: rg)
  {prog} record <file> <log>   Record deterministic replay (alias: rec)
  {prog} replay <file>         Replay a recorded run
  {prog} diff <a> <b>          Diff two run records
  {prog} explain <error>       Explain an error id

Packages:
  {prog} search <query>        Search packages
  {prog} info <package>        Show package details
  {prog} install <package>     Install package from registry
  {prog} add <package>         Add a dependency to the project
  {prog} remove <package>      Remove a dependency from the project
  {prog} update [package]      Update dependencies
  {prog} verify <package>      Verify package integrity
  {prog} trust check <package> Inspect package trust policy

Security and AI:
  {prog} security audit        Run local security checks (alias: sec audit)
  {prog} agent run <task>      Run an AI agent task
  {prog} assistant <file>      Code assistant (summary + hints)
  {prog} ask "question"        Offline CLI command helper (alias: ai)
  {prog} guide ai              Learn AI helper limits

Config:
  {prog} config list           Show CLI config (alias: cfg list)
  {prog} registry <url>        Set default registry
  {prog} login --token <token> Authenticate to a registry
  {prog} whoami                Show active registry identity
  {prog} completion powershell Print shell completion script
"""
