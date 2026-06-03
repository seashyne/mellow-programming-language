from __future__ import annotations

from pathlib import Path

from mellowlang.cli import main as cli_main
from mellowlang import lsp_server


def test_doctor_report_detects_distribution_mismatch(monkeypatch):
    monkeypatch.setattr(cli_main, '_distribution_version', lambda: '1.6.4')
    monkeypatch.setattr(cli_main, '_read_project_version', lambda project_root: '1.6.5')
    monkeypatch.setattr(cli_main, '_find_all_mellow_on_path', lambda: ['/tmp/mellow'])
    monkeypatch.setattr(cli_main.shutil, 'which', lambda name: '/tmp/mellow')
    monkeypatch.setattr(cli_main, '_find_project_root', lambda start: Path('/tmp/project'))
    report = cli_main._doctor_report()
    assert report['has_mismatch'] is True
    assert any(c['name'] == 'installed_distribution' and c['status'] == 'warn' for c in report['checks'])


def test_doctor_report_detects_duplicate_path(monkeypatch):
    monkeypatch.setattr(cli_main, '_distribution_version', lambda: '1.6.5')
    monkeypatch.setattr(cli_main, '_read_project_version', lambda project_root: '1.6.5')
    monkeypatch.setattr(cli_main, '_find_all_mellow_on_path', lambda: ['/tmp/a/mellow', '/tmp/b/mellow'])
    monkeypatch.setattr(cli_main.shutil, 'which', lambda name: '/tmp/a/mellow')
    monkeypatch.setattr(cli_main, '_find_project_root', lambda start: Path('/tmp/project'))
    report = cli_main._doctor_report()
    assert any(c['name'] == 'path_duplicates' and c['status'] == 'warn' for c in report['checks'])


def test_lsp_symbols_and_hover():
    text = 'skill greet(name)\n  print(name)\nend\n\non spawn()\nend\nfoo = 1\n'
    syms = list(lsp_server._iter_symbols(text))
    names = [s['name'] for s in syms]
    assert 'greet' in names
    assert 'spawn' in names
    assert 'foo' in names
    hover = lsp_server.Hover(contents=lsp_server.MarkupContent(kind=lsp_server.MarkupKind.Markdown, value='ok'))
    assert hover.contents.value == 'ok'
    assert lsp_server._extract_word('print(name)', 0, 2) == 'print'
