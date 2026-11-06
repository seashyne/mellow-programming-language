"""The compile and React dev-server entry points the `mellow web`
commands call."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from .emitting import emit_tsx
from .model import MellowWebError
from .parsing import parse_web_source
from .scaffold import (
    _dev_index_html,
    _dev_main_tsx,
    _dev_package_json,
    _dev_tsconfig_json,
    _dev_vite_config,
    _write_dev_file,
)


def compile_file_to_tsx(input_path: str | Path, out_path: str | Path | None = None) -> dict[str, Any]:
    source_path = Path(input_path)
    component = parse_web_source(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    tsx = emit_tsx(component)
    if out_path is not None:
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(tsx, encoding="utf-8")
    return {"ok": True, "component": component.name, "kind": component.kind, "tsx": tsx}


def prepare_react_dev_app(
    input_path: str | Path,
    *,
    app_dir: str | Path = ".mellow/web-dev",
    install: bool = True,
) -> dict[str, Any]:
    source_path = Path(input_path).resolve()
    target_dir = Path(app_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    src_dir = target_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    generated = compile_file_to_tsx(source_path, target_dir / "MellowApp.tsx")
    _write_dev_file(target_dir / "package.json", _dev_package_json())
    _write_dev_file(target_dir / "index.html", _dev_index_html())
    _write_dev_file(target_dir / "tsconfig.json", _dev_tsconfig_json())
    _write_dev_file(target_dir / "vite.config.ts", _dev_vite_config())
    _write_dev_file(src_dir / "main.tsx", _dev_main_tsx())

    if install and not (target_dir / "node_modules").exists():
        npm = shutil.which("npm")
        if npm is None:
            raise MellowWebError("npm was not found on PATH; install Node.js/npm to run mellow web dev")
        completed = subprocess.run([npm, "install"], cwd=target_dir, check=False)
        if completed.returncode != 0:
            raise MellowWebError(f"npm install failed with exit code {completed.returncode}")

    return {
        "ok": True,
        "app_dir": str(target_dir),
        "source": str(source_path),
        "component": generated["component"],
        "tsx": str(target_dir / "MellowApp.tsx"),
    }


def run_react_dev_app(
    input_path: str | Path,
    *,
    app_dir: str | Path = ".mellow/web-dev",
    port: int = 5179,
    host: str = "127.0.0.1",
    build_only: bool = False,
) -> int:
    prepared = prepare_react_dev_app(input_path, app_dir=app_dir, install=True)
    npm = shutil.which("npm")
    if npm is None:
        raise MellowWebError("npm was not found on PATH; install Node.js/npm to run mellow web dev")
    target_dir = Path(prepared["app_dir"])
    if build_only:
        return int(subprocess.run([npm, "run", "build"], cwd=target_dir, check=False).returncode)
    print(f"[OK] mellow-web generated: {prepared['tsx']}")
    print(f"[OK] React dev server: http://{host}:{port}/")
    return int(subprocess.run([npm, "run", "dev", "--", "--host", host, "--port", str(port)], cwd=target_dir, check=False).returncode)
