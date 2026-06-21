from pathlib import Path

from mellowlang.compiler import Compiler
from mellowlang.package_manager import init_package, read_manifest, seed_core_packages

REQUIRED_STARTER_PACKAGES = {
    "core-ai",
    "core-collections",
    "core-data",
    "core-gamekit",
    "core-http",
    "core-json",
    "core-ledger",
    "core-llm",
    "core-math",
    "core-mmg",
    "core-money",
    "mellow-sdk",
    "core-print",
    "core-save",
    "core-storage",
    "core-strings",
    "core-time",
    "core-window",
    "core-workflow",
}


def test_read_manifest_directory_error(tmp_path: Path):
    d = tmp_path / "empty"
    d.mkdir()
    try:
        read_manifest(d)
    except FileNotFoundError as e:
        assert "no package manifest found" in str(e)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_seed_core_packages(tmp_path: Path):
    res = seed_core_packages(tmp_path / "core", publish_local=False)
    names = {item['name'] for item in res['items']}
    assert REQUIRED_STARTER_PACKAGES <= names
    for item in res['items']:
        man = read_manifest(Path(item['dir']))
        assert man['name'] == item['name']
        assert man['version'] == item['version']


def test_starter_package_manifests_and_entries_compile():
    root = Path(__file__).resolve().parents[1] / "starter_packages"
    names = set()
    for package_dir in sorted(path for path in root.iterdir() if (path / "mellow.toml").exists()):
        manifest = read_manifest(package_dir / "mellow.toml")
        compat = read_manifest(package_dir / "mellow.pkg.json")
        names.add(manifest["name"])
        for key in ("name", "version", "entry", "description", "authors", "license", "keywords", "badges", "official", "visibility", "dependencies"):
            assert compat.get(key) == manifest.get(key), f"{manifest['name']} mismatch: {key}"
        assert manifest["authors"] == ["Mellow Code Team"]
        assert "official" in manifest["badges"]
        assert manifest["official"] is True
        assert manifest["keywords"]
        if manifest["name"] == "core-save":
            assert manifest.get("deprecated") is True
            assert "deprecated" in manifest["badges"]
        entry = package_dir / manifest["entry"]
        assert entry.exists(), f"{manifest['name']} missing entry {manifest['entry']}"
        Compiler().compile(entry.read_text(encoding="utf-8"), filename=str(entry))
    assert REQUIRED_STARTER_PACKAGES <= names
