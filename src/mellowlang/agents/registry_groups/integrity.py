"""Content hashes, canonical JSON and the manifest signature."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict


def _canonical_json(data: Dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def sign_agent_manifest(manifest: Dict[str, Any], signing_key: str, signer: str | None = None) -> Dict[str, Any]:
    base = dict(manifest)
    base.pop('signature', None)
    base.pop('signed_by', None)
    sig = hashlib.sha256(signing_key.encode('utf-8') + b'|' + _canonical_json(base)).hexdigest()
    base['signature'] = sig
    if signer:
        base['signed_by'] = signer
    return base


def verify_agent_manifest_signature(manifest: Dict[str, Any], signing_key: str) -> bool:
    sig = str(manifest.get('signature') or '')
    if not sig or not signing_key:
        return False
    base = dict(manifest)
    base.pop('signature', None)
    base.pop('signed_by', None)
    expected = hashlib.sha256(signing_key.encode('utf-8') + b'|' + _canonical_json(base)).hexdigest()
    return expected == sig


def _read_manifest_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))
