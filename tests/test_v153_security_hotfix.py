from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import mellowlang.package_manager as pm


def test_login_with_token_does_not_save_invalid_token(tmp_path: Path, monkeypatch):
    cfg_dir = tmp_path / 'cfg'
    monkeypatch.setenv('MELLOW_CONFIG_DIR', str(cfg_dir))
    pm.CONFIG_HOME = cfg_dir
    pm.CONFIG_FILE = cfg_dir / 'config.json'

    def fake_request(method, url, payload=None, token=None):
        return {'ok': False, 'error': 'invalid publish token'}

    monkeypatch.setattr(pm, '_request_json', fake_request)
    res = pm.login_with_token('bad-token', registry='https://registry.example.test')
    assert res['ok'] is False
    cfg = pm.load_config()
    assert cfg.get('auth', {}).get('https://registry.example.test') is None


def test_extract_archive_blocks_zip_slip(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('../evil.txt', 'nope')
        zf.writestr('mellow.pkg.json', json.dumps({'name': 'badpkg', 'version': '0.1.0', 'entry': 'src/main.mellow'}))
    res = pm._extract_archive_to_install('badpkg', '0.1.0', buf.getvalue())
    assert res['ok'] is False
    assert 'unsafe archive entry' in res['error']
    assert not (tmp_path / 'evil.txt').exists()
