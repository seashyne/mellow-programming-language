from __future__ import annotations

import importlib

cli_main = importlib.import_module("mellowlang.cli.main")
lsp_server = importlib.import_module("mellowlang.lsp_server")


def test_lsp_runtime_status_shape():
    status = lsp_server.lsp_runtime_status()
    assert set(status.keys()) == {"ready", "backend", "error"}
    assert isinstance(status["ready"], bool)


def test_doctor_strict_fails_when_lsp_not_ready(monkeypatch):
    monkeypatch.setattr(cli_main, '_doctor_report', lambda: {
        'mellow_version': '1.6.5.1',
        'python': '3.14.3',
        'platform': 'TestOS',
        'exe': '/tmp/python',
        'cwd': '/tmp',
        'ansi': False,
        'config_file': '/tmp/config.json',
        'registry': 'https://example.invalid',
        'cache_packages': 0,
        'installed_packages': 0,
        'scripts_on_path': '/tmp/mellow',
        'project_root': '/tmp/project',
        'checks': [],
        'has_mismatch': False,
    })

    class FakeWho(dict):
        def get(self, key, default=None):
            return default

    monkeypatch.setattr(cli_main, 'pkg_whoami_remote', lambda registry: FakeWho())
    monkeypatch.setattr(lsp_server, 'lsp_runtime_status', lambda: {
        'ready': False,
        'backend': 'stub',
        'error': 'boom',
    })

    rc = cli_main._cmd_doctor(json_out=False, strict=True)
    assert rc == 2


def test_start_lsp_error_is_actionable(monkeypatch):
    monkeypatch.setattr(lsp_server, 'HAVE_PYGLS', False)
    monkeypatch.setattr(lsp_server, 'PYGLS_IMPORT_ERROR', 'ImportError(\"demo\")')
    try:
        lsp_server.start_lsp()
    except RuntimeError as e:
        msg = str(e)
        assert 'Mellow LSP could not start.' in msg
        assert 'doctor --strict' in msg
    else:  # pragma: no cover
        raise AssertionError('expected RuntimeError')
