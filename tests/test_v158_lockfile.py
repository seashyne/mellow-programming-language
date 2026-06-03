from pathlib import Path
import json
from mellowlang.package_manager import _save_import_map, _save_lockfile, _load_lockfile


def test_lockfile_roundtrip(tmp_path: Path):
    path = _save_lockfile({"lockfile_version": 1, "registry": "https://example", "packages": {}, "root": {"dependencies": {}, "imports": []}}, tmp_path)
    assert path.exists()
    data = _load_lockfile(tmp_path)
    assert data["registry"] == "https://example"


def test_import_map_written(tmp_path: Path):
    path = _save_import_map(tmp_path, [])
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "imports" in data
