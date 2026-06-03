from __future__ import annotations

import io
from contextlib import redirect_stdout

from mellowlang.cli.main import main


def test_top_level_registry_command_updates_config(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "cfg"
    monkeypatch.setenv("MELLOW_CONFIG_DIR", str(cfg_dir))
    import mellowlang.package_manager as pm
    pm.CONFIG_HOME = cfg_dir
    pm.CONFIG_FILE = cfg_dir / "config.json"

    out = io.StringIO()
    with redirect_stdout(out):
        code = main(["registry", "https://registry.example.test"])
    assert code == 0
    assert "default registry" in out.getvalue()
    assert pm.load_config()["registry"] == "https://registry.example.test"


def test_help_mentions_registry_and_login(capsys):
    code = main([])
    assert code == 2
    out = capsys.readouterr().out
    assert "login --token <token>" in out
    assert "registry <url>" in out
