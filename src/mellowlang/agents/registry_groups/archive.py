"""A package directory becomes a reproducible, optionally signed archive."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict

from .catalog import agent_manifest_dict
from .integrity import _sha256_file, sign_agent_manifest
from .layout import (AGENT_REGISTRY_ROOT, ARCHIVE_EXT, REPRO_ZIP_TIMESTAMP,
                     ensure_agent_dirs, normalize_agent_name)


def _iter_agent_files(package_dir: Path):
    ignore_names = {'.git', '.pytest_cache', '__pycache__', '.DS_Store'}
    items: list[Path] = []
    for sub in package_dir.rglob('*'):
        if any(part in ignore_names for part in sub.parts):
            continue
        if sub.is_file() and sub.name != '.DS_Store':
            items.append(sub)
    for sub in sorted(items, key=lambda p: str(p.relative_to(package_dir)).replace('\\', '/')):
        yield sub


def _write_reproducible_zip(zf: zipfile.ZipFile, arcname: str, raw: bytes) -> None:
    info = zipfile.ZipInfo(filename=arcname, date_time=REPRO_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o644 << 16
    zf.writestr(info, raw)


def build_agent_archive(package_dir: str | Path, out_path: str | Path | None = None, *, signing_key: str | None = None, signer: str | None = None) -> Dict[str, Any]:
    pd = Path(package_dir)
    manifest = agent_manifest_dict(pd)
    if signing_key:
        manifest = sign_agent_manifest(manifest, signing_key, signer=signer)
    out = Path(out_path) if out_path else pd / f"{normalize_agent_name(manifest['name']).replace('/', '_')}-{manifest['version']}{ARCHIVE_EXT}"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        _write_reproducible_zip(zf, 'agent-manifest.json', (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode('utf-8'))
        for sub in _iter_agent_files(pd):
            if out.resolve() == sub.resolve():
                continue
            arcname = str(sub.relative_to(pd)).replace('\\', '/')
            _write_reproducible_zip(zf, arcname, sub.read_bytes())
    sha256 = _sha256_file(out)
    return {'ok': True, 'name': manifest['name'], 'version': manifest['version'], 'archive': str(out), 'sha256': sha256, 'manifest': manifest, 'signed': bool(signing_key), 'reproducible': True}


def publish_agent_from_dir(package_dir: str | Path, *, signing_key: str | None = None, signer: str | None = None) -> Dict[str, Any]:
    ensure_agent_dirs()
    pd = Path(package_dir)
    manifest = agent_manifest_dict(pd)
    if signing_key:
        manifest = sign_agent_manifest(manifest, signing_key, signer=signer)
    name = normalize_agent_name(manifest['name'])
    version = str(manifest['version'])
    out_dir = AGENT_REGISTRY_ROOT / name / version
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(pd, out_dir)
    built = build_agent_archive(pd, out_dir / f'{name.replace("/", "_")}-{version}{ARCHIVE_EXT}', signing_key=signing_key, signer=signer)
    manifest['archive_sha256'] = built['sha256']
    (out_dir / 'agent-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'ok': True, 'name': name, 'version': version, 'published_to': str(out_dir), 'archive': built['archive'], 'sha256': built['sha256'], 'signed': bool(signing_key), 'reproducible': True}
