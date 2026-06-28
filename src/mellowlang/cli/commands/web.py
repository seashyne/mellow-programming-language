from __future__ import annotations

import sys
import json
from dataclasses import dataclass
from pathlib import Path

from ...web import MellowWebError, compile_file_to_tsx, prepare_react_dev_app, run_react_dev_app
from ..common import _json_print


@dataclass
class WebConfig:
    project_dir: Path
    entry: str | None = None
    out_dir: str = ".mellow/web-dev"
    host: str = "127.0.0.1"
    port: int = 5179


def _cmd_web(subcmd: str | None, file: str | None, out: str | None, json_out: bool) -> int:
    if subcmd not in {"build", "tsx"}:
        print("error: web needs a subcommand, e.g. `mellow web build src/Home.mellow --out src/Home.tsx`", file=sys.stderr)
        return 2
    if not file:
        print("error: web build needs an input file", file=sys.stderr)
        return 2
    input_path = Path(file)
    if not input_path.exists():
        print(f"error: path not found: {input_path}", file=sys.stderr)
        return 2
    try:
        res = compile_file_to_tsx(input_path, out)
    except MellowWebError as exc:
        if json_out:
            _json_print({"ok": False, "error": str(exc)})
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1
    if json_out:
        payload = {k: v for k, v in res.items() if k != "tsx"}
        if out:
            payload["out"] = str(Path(out))
        else:
            payload["tsx"] = res["tsx"]
        _json_print(payload)
    elif out:
        print(f"[OK] wrote TSX: {out}")
    else:
        sys.stdout.write(str(res["tsx"]))
    return 0


def _cmd_web_dev(
    file: str | None,
    *,
    app_dir: str | None,
    port: int | None,
    host: str | None,
    json_out: bool = False,
    build_only: bool = False,
    prepare_only: bool = False,
) -> int:
    config = _load_web_config(Path.cwd())
    app_dir = app_dir or str(config.project_dir / config.out_dir)
    host = host or config.host
    port = port or config.port
    if not file:
        resolved = _resolve_default_web_entry(config)
        if resolved is None:
            print("error: web dev could not find a web entry. Add `web.entry` to mellow.json/mellow.toml or pass a file.", file=sys.stderr)
            return 2
        input_path = resolved
    else:
        input_path = Path(file)
    if not input_path.exists():
        print(f"error: path not found: {input_path}", file=sys.stderr)
        return 2
    try:
        package_res = _ensure_mellow_web_package(input_path)
        if not package_res.get("ok"):
            message = str(package_res.get("error") or "mellow-web package install failed")
            if json_out:
                _json_print({"ok": False, "error": message})
            else:
                print(f"error: {message}", file=sys.stderr)
            return 1
        if not json_out and package_res.get("installed_now"):
            print(f"[OK] installed package: mellow-web ({package_res.get('project_dir')})")
        if prepare_only:
            prepared = prepare_react_dev_app(input_path, app_dir=app_dir, install=False)
            if json_out:
                _json_print({**prepared, "prepared": True, "package": package_res})
            else:
                print(f"[OK] prepared mellow-web dev app: {prepared['app_dir']}")
            return 0
        if build_only:
            prepared = prepare_react_dev_app(input_path, app_dir=app_dir, install=True)
            import subprocess
            import shutil

            npm = shutil.which("npm")
            if npm is None:
                raise MellowWebError("npm was not found on PATH; install Node.js/npm to run mellow web dev")
            completed = subprocess.run([npm, "run", "build"], cwd=prepared["app_dir"], check=False)
            if json_out:
                _json_print({**prepared, "built": completed.returncode == 0})
            return int(completed.returncode)
        return run_react_dev_app(input_path, app_dir=app_dir, port=port, host=host)
    except MellowWebError as exc:
        if json_out:
            _json_print({"ok": False, "error": str(exc)})
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1


def _ensure_mellow_web_package(input_path: Path) -> dict[str, object]:
    project_dir = _web_project_dir(input_path)
    installed_manifest = project_dir / "mellow_packages" / "installed" / "mellow-web" / "current" / "manifest.json"
    if installed_manifest.exists():
        return {"ok": True, "project_dir": str(project_dir), "installed_now": False}

    from ...package_manager import install_local_package_into_project

    res = install_local_package_into_project("mellow-web", project_dir, with_deps=True)
    if not res.get("ok"):
        res.setdefault("hint", "Install the web package first with `mellow add mellow-web`, then run `mellow web dev <file>`.")
        return res
    return {"ok": True, "project_dir": str(project_dir), "installed_now": True, "install": res}


def _web_project_dir(input_path: Path) -> Path:
    start = input_path.resolve().parent
    for candidate in (start, *start.parents):
        if candidate.name == "mellow-web" and candidate.parent.name == "starter_packages":
            continue
        if (candidate / "mellow.toml").exists() or (candidate / "mellow.json").exists():
            return candidate
    return Path.cwd().resolve()


def _resolve_default_web_entry(config: WebConfig) -> Path | None:
    project_dir = config.project_dir
    if config.entry is not None:
        candidate = (project_dir / config.entry).resolve()
        if candidate.exists():
            return candidate

    for rel in ("src/main.mellow", "src/App.mellow", "src/Counter.mellow", "main.mellow", "App.mellow"):
        candidate = project_dir / rel
        if candidate.exists():
            return candidate.resolve()

    src_dir = project_dir / "src"
    if src_dir.exists():
        for candidate in sorted(src_dir.rglob("*.mellow")):
            if "mellow_packages" not in candidate.parts and ".mellow" not in candidate.parts:
                return candidate.resolve()
    return None


def _load_web_config(cwd: Path) -> WebConfig:
    project_dir = _find_web_project_root(cwd.resolve()) or cwd.resolve()
    data = _web_manifest_data(project_dir)
    web = data.get("web") if isinstance(data.get("web"), dict) else {}
    entry = _string_or_none(web.get("entry")) or _string_or_none(data.get("web_entry"))
    out_dir = _string_or_none(web.get("out_dir")) or _string_or_none(web.get("dir")) or _string_or_none(data.get("web_out_dir")) or ".mellow/web-dev"
    host = _string_or_none(web.get("host")) or _string_or_none(data.get("web_host")) or "127.0.0.1"
    port = _int_or_default(web.get("port"), _int_or_default(data.get("web_port"), 5179))
    return WebConfig(project_dir=project_dir, entry=entry, out_dir=out_dir, host=host, port=port)


def _find_web_project_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if candidate.name == "mellow-web" and candidate.parent.name == "starter_packages":
            continue
        if (candidate / "mellow.toml").exists() or (candidate / "mellow.json").exists():
            return candidate
    return None


def _web_manifest_data(project_dir: Path) -> dict[str, object]:
    mellow_json = project_dir / "mellow.json"
    if mellow_json.exists():
        try:
            data = json.loads(mellow_json.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    mellow_toml = project_dir / "mellow.toml"
    if mellow_toml.exists():
        try:
            from ...package_manager import read_manifest

            data = read_manifest(mellow_toml)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_default(value: object, default: int) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(value)
    except Exception:
        return default
