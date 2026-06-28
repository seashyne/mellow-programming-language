from __future__ import annotations

import shutil
import os
from pathlib import Path

from mellowlang.web import emit_tsx, parse_web_source
from mellowlang.cli.main import main


def test_mellow_web_emits_react_tsx_counter() -> None:
    component = parse_web_source(
        """use mellow-web as web

page Counter
  state count = 0

  view:
    Stack(gap: 12)
      Title("Mellow Counter")
      Text("Count: {count}")
      Button("Add", onClick: count += 1)
"""
    )
    tsx = emit_tsx(component)
    assert 'import { useState } from "react"' in tsx
    assert "export default function Counter()" in tsx
    assert "const [count, setCount] = useState(0)" in tsx
    assert '<h1>"Mellow Counter"</h1>' not in tsx
    assert "<h1>Mellow Counter</h1>" in tsx
    assert "{() => setCount((count) => count + 1)}" in tsx


def test_mellow_web_cli_build_writes_tsx() -> None:
    work = Path.cwd() / ".tmp_mellow_web_cli_test"
    src = work / "Counter.mellow"
    out = work / "Counter.tsx"
    try:
        work.mkdir(parents=True, exist_ok=True)
        src.write_text(
            """page Counter
  state count = 0

  view:
    Stack(gap: 10)
      Text("Count: {count}")
      Button("Add", onClick: count += 1)
""",
            encoding="utf-8",
        )
        assert main(["web", "build", str(src), "--out", str(out)]) == 0
        generated = out.read_text(encoding="utf-8")
        assert "export default function Counter()" in generated
        assert 'style={{"display": "flex", "flexDirection": "column", "gap": 10}}' in generated
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_mellow_web_cli_dev_prepare_installs_web_package() -> None:
    work = Path.cwd() / ".tmp_mellow_web_dev_test"
    src = work / "Counter.mellow"
    app_dir = work / "app"
    try:
        work.mkdir(parents=True, exist_ok=True)
        (work / "mellow.toml").write_text(
            """name = "web-dev-test"
version = "0.1.0"
entry = "Counter.mellow"
dependencies = {}
""",
            encoding="utf-8",
        )
        src.write_text(
            """page Counter
  state count = 0

  view:
    Stack(gap: 10)
      Text("Count: {count}")
      Button("Add", onClick: count += 1)
""",
            encoding="utf-8",
        )
        assert main(["web", "dev", str(src), "--dir", str(app_dir), "--prepare-only"]) == 0
        generated = app_dir / "MellowApp.tsx"
        assert generated.exists()
        assert "export default function Counter()" in generated.read_text(encoding="utf-8")
        assert (work / "mellow_packages" / "installed" / "mellow-web" / "current" / "manifest.json").exists()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_mellow_web_dev_defaults_to_project_entry() -> None:
    work = Path.cwd() / ".tmp_mellow_web_default_entry_test"
    src_dir = work / "src"
    app_dir = work / ".mellow" / "web-dev"
    old_cwd = Path.cwd()
    try:
        src_dir.mkdir(parents=True, exist_ok=True)
        (work / "mellow.json").write_text(
            """{
  "name": "default-web-entry-test",
  "web": {
    "entry": "src/App.mellow"
  }
}
""",
            encoding="utf-8",
        )
        (src_dir / "App.mellow").write_text(
            """page App
  state count = 0

  view:
    Stack(gap: 10)
      Text("Count: {count}")
""",
            encoding="utf-8",
        )
        os.chdir(work)
        assert main(["web", "dev", "--prepare-only"]) == 0
        generated = app_dir / "MellowApp.tsx"
        assert generated.exists()
        assert "export default function App()" in generated.read_text(encoding="utf-8")
        assert (work / "mellow_packages" / "installed" / "mellow-web" / "current" / "manifest.json").exists()
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(work, ignore_errors=True)


def test_mellow_web_dev_uses_project_config() -> None:
    work = Path.cwd() / ".tmp_mellow_web_config_test"
    src_dir = work / "src"
    app_dir = work / ".mellow" / "custom-web"
    old_cwd = Path.cwd()
    try:
        src_dir.mkdir(parents=True, exist_ok=True)
        (work / "mellow.json").write_text(
            """{
  "name": "web-config-test",
  "web": {
    "entry": "src/App.mellow",
    "out_dir": ".mellow/custom-web",
    "host": "127.0.0.1",
    "port": 5191
  }
}
""",
            encoding="utf-8",
        )
        (src_dir / "App.mellow").write_text(
            """page App
  view:
    Text("Configured")
""",
            encoding="utf-8",
        )
        os.chdir(work)
        assert main(["web", "dev", "--prepare-only"]) == 0
        assert (app_dir / "MellowApp.tsx").exists()
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(work, ignore_errors=True)


def test_mellow_web_dev_flag_dir_overrides_config() -> None:
    work = Path.cwd() / ".tmp_mellow_web_config_override_test"
    src_dir = work / "src"
    app_dir = work / "override-app"
    old_cwd = Path.cwd()
    try:
        src_dir.mkdir(parents=True, exist_ok=True)
        (work / "mellow.json").write_text(
            """{
  "name": "web-config-override-test",
  "web": {
    "entry": "src/App.mellow",
    "out_dir": ".mellow/custom-web"
  }
}
""",
            encoding="utf-8",
        )
        (src_dir / "App.mellow").write_text(
            """page App
  view:
    Text("Override")
""",
            encoding="utf-8",
        )
        os.chdir(work)
        assert main(["web", "dev", "--dir", str(app_dir), "--prepare-only"]) == 0
        assert (app_dir / "MellowApp.tsx").exists()
        assert not (work / ".mellow" / "custom-web" / "MellowApp.tsx").exists()
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(work, ignore_errors=True)
