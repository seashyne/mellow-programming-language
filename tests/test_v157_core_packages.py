from pathlib import Path

from mellowlang.package_manager import init_package, read_manifest, seed_core_packages


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
    assert {'core-print','core-strings','core-json','core-http','core-storage','core-gamekit','core-ai'} <= names
    for item in res['items']:
        man = read_manifest(Path(item['dir']))
        assert man['name'] == item['name']
