from __future__ import annotations

import base64
import json
from typing import Any, Dict

from .config import ensure_user_dirs, keys_dir_path
from .metadata import normalize_name

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    from cryptography.hazmat.primitives import serialization
except Exception:  # pragma: no cover
    Ed25519PrivateKey = None
    Ed25519PublicKey = None
    serialization = None


def _signature_payload(manifest: Dict[str, Any], sha256: str) -> bytes:
    payload = {
        "name": normalize_name(str(manifest.get("name", "pkg"))),
        "version": str(manifest.get("version", "0.0.0")),
        "entry": str(manifest.get("entry", "src/main.mellow")),
        "sha256": sha256.lower(),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

def ensure_signing_keypair() -> Dict[str, str]:
    ensure_user_dirs()
    key_dir = keys_dir_path()
    priv_path = key_dir / "ed25519_private.pem"
    pub_path = key_dir / "ed25519_public.pem"
    if priv_path.exists() and pub_path.exists():
        return {"private": str(priv_path), "public": str(pub_path)}
    if Ed25519PrivateKey is None or serialization is None:
        raise RuntimeError("cryptography with Ed25519 support is required for package signing")
    key = Ed25519PrivateKey.generate()
    priv_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv_path.write_bytes(priv_bytes)
    pub_path.write_bytes(pub_bytes)
    return {"private": str(priv_path), "public": str(pub_path)}

def sign_manifest(manifest: Dict[str, Any], sha256: str) -> Dict[str, Any]:
    if Ed25519PrivateKey is None or serialization is None:
        return manifest
    ensure_signing_keypair()
    key_dir = keys_dir_path()
    priv = serialization.load_pem_private_key((key_dir / "ed25519_private.pem").read_bytes(), password=None)
    pub_bytes = (key_dir / "ed25519_public.pem").read_bytes()
    signature = priv.sign(_signature_payload(manifest, sha256))
    signed = dict(manifest)
    signed["signing"] = {
        "algorithm": "ed25519",
        "public_key_pem": pub_bytes.decode("utf-8"),
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }
    return signed

def verify_signed_manifest(manifest: Dict[str, Any], sha256: str) -> Dict[str, Any]:
    info = dict((manifest or {}).get("signing") or {})
    if not info:
        return {"ok": True, "signed": False}
    if Ed25519PublicKey is None or serialization is None:
        return {"ok": False, "signed": True, "error": "cryptography with Ed25519 support is required for signature verification"}
    try:
        pub = serialization.load_pem_public_key(str(info.get("public_key_pem", "")).encode("utf-8"))
        sig = base64.b64decode(str(info.get("signature_b64", "")))
        pub.verify(sig, _signature_payload(manifest, sha256))
        return {"ok": True, "signed": True, "algorithm": info.get("algorithm", "ed25519")}
    except Exception as e:
        return {"ok": False, "signed": True, "error": f"signature verification failed: {e}"}

