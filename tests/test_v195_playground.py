from pathlib import Path
import sys

sys.path.insert(0, str((Path(__file__).resolve().parents[1] / 'src')))

from mellowlang.playground import build_static_playground, run_playground_session


def test_playground_session_runs_hello():
    payload = run_playground_session('print("hello playground")\n', optimize=True)
    assert payload['ok'] is True
    assert 'hello playground' in payload['stdout']
    assert payload['pipeline']
    assert 'dumps' in payload
    assert 'ir' in payload['dumps']


def test_playground_build_writes_assets(tmp_path):
    out = build_static_playground(tmp_path / 'site')
    assert (out / 'index.html').exists()
    assert (out / 'styles.css').exists()
    assert (out / 'app.js').exists()
