from pathlib import Path
import sys

sys.path.insert(0, str((Path(__file__).resolve().parents[1] / "src")))

from mellowlang.host.runtime import default_host
from mellowlang.package_manager import init_package, publish_from_dir, install_package, build_package_archive, list_installed
from mellowlang.cli.main import _cmd_compile, main


def test_game_engine_helpers():
    host = default_host()
    a = host.call('std.game.entity.create', ['a', 0, 0, 2, 2])
    b = host.call('std.game.entity.create', ['b', 1, 1, 2, 2])
    c = host.call('std.game.entity.move', [a, 1, 0])
    hit = host.call('std.game.physics.collide_aabb', [c, b])
    frame = host.call('std.game.anim.frame', [4, 0.75, 4, True])
    assert hit is True
    assert frame['frame'] == 3


def test_ai_api_helpers():
    host = default_host()
    providers = host.call('std.ai.api_providers', [])
    reply = host.call('std.ai.api_complete', ['offline', 'hello mellow', {'style': 'test'}])
    assert any(p['name'] == 'offline' for p in providers)
    assert 'response' in reply


def test_package_manager_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pkg_dir = tmp_path / 'hello_pkg'
    man = init_package(pkg_dir, name='hello-world', author='Sea Shyne')
    assert man['name'] == 'hello-world'
    assert man['authors'] == ['Sea Shyne']
    pub = publish_from_dir(pkg_dir)
    assert pub['name'] == 'hello-world'
    ins = install_package('hello-world')
    assert ins['name'] == 'hello-world'
    assert ins['creator'] == 'Sea Shyne'
    built = build_package_archive(pkg_dir)
    assert Path(built['archive']).exists()
    assert any(row['name'] == 'hello-world' and row['creator'] == 'Sea Shyne' for row in list_installed())


def test_package_init_author_and_list_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = main(['pkg', 'init', 'demo_pkg', '--name', 'demo-pkg', '--author', 'Mellow Maker'])
    assert code == 0
    manifest = (tmp_path / 'demo_pkg' / 'mellow.pkg.json').read_text(encoding='utf-8')
    assert '"Mellow Maker"' in manifest
    assert main(['pkg', 'publish', 'demo_pkg']) == 0
    assert main(['pkg', 'install', 'demo-pkg']) == 0
    capsys.readouterr()
    assert main(['pkg', 'list']) == 0
    out = capsys.readouterr().out
    assert 'demo-pkg@0.1.0 by Mellow Maker' in out


def test_compile_command_outputs(tmp_path):
    src = tmp_path / 'demo.mellow'
    src.write_text('print(1+2)\n', encoding='utf-8')
    bytecode_out = tmp_path / 'demo.mellowc.json'
    py_out = tmp_path / 'demo.generated.py'
    assert _cmd_compile(str(src), 'bytecode', str(bytecode_out)) == 0
    assert _cmd_compile(str(src), 'python', str(py_out)) == 0
    assert bytecode_out.exists()
    assert py_out.exists()
