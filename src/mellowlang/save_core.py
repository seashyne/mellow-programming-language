# mellowlang/save_core.py
from __future__ import annotations

import json
import os
import platform
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, List

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes


MAGIC = b"MSAV"  # Mellow SAVe

# File format versions:
#   1: encrypted payload (ChaCha20-Poly1305)
#   2: encrypted payload + detached signature (Ed25519) for server-signed validation
VERSION = 2


def _user_data_root() -> Path:
    """Return OS-appropriate user data directory root."""
    sysname = platform.system().lower()
    home = Path.home()
    if sysname.startswith("windows"):
        appdata = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        return Path(appdata) if appdata else (home / "AppData" / "Roaming")
    if sysname == "darwin":
        return home / "Library" / "Application Support"
    # Linux / other unix
    xdg = os.environ.get("XDG_DATA_HOME")
    return Path(xdg) if xdg else (home / ".local" / "share")


def app_save_dir(app_id: str) -> Path:
    safe = "".join(ch for ch in (app_id or "mellow.app") if ch.isalnum() or ch in ("-", "_", "."))
    safe = safe.strip(".") or "mellow.app"
    return _user_data_root() / safe / "saves"


def _device_secret_path(app_id: str) -> Path:
    return app_save_dir(app_id).parent / ".device_secret"


def _load_or_create_device_secret(app_id: str) -> bytes:
    p = _device_secret_path(app_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        data = p.read_bytes()
        if len(data) >= 32:
            return data[:32]
    secret = secrets.token_bytes(32)
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(secret)
    try:
        # best-effort: restrict permissions (POSIX)
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    os.replace(tmp, p)
    return secret


def _derive_key(device_secret: bytes, salt: bytes, info: bytes) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=info,
    )
    return hkdf.derive(device_secret)


def _slot_filename(slot: str) -> str:
    raw = (slot or "slot1").strip().strip('"').strip("'")
    raw = raw.replace("\\", "/")
    raw = raw.split("/")[-1]  # no folders
    safe = "".join(ch for ch in raw if ch.isalnum() or ch in ("-", "_"))
    return (safe or "slot1") + ".msav"


def _aad(app_id: str, slot: str, ver: int) -> bytes:
    return (f"app_id={app_id}\nslot={slot}\nver={ver}").encode("utf-8")


@dataclass
class SaveLimits:
    max_slots: int = 10
    max_bytes: int = 1_048_576  # 1 MiB


class SaveSystem:
    """Encrypted, tamper-evident save system.

    Security properties (offline):
      - AEAD encryption (ChaCha20-Poly1305): confidentiality + integrity.
      - Per-file random salt + nonce.
      - Key derived from per-app device secret (stored in user data dir with tight perms when possible).

    Note: offline client-side encryption cannot fully stop a determined attacker,
    but this prevents casual editing and detects tampering reliably.
    """

    def __init__(self, *, app_id: str, limits: SaveLimits | None = None) -> None:
        self.app_id = app_id
        self.dir = app_save_dir(app_id)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.device_secret = _load_or_create_device_secret(app_id)
        self.limits = limits or SaveLimits()

    def list_slots(self) -> List[str]:
        if not self.dir.exists():
            return []
        out: List[str] = []
        for p in sorted(self.dir.glob("*.msav")):
            out.append(p.stem)
        return out[: self.limits.max_slots]

    def delete_slot(self, slot: str) -> bool:
        p = self.dir / _slot_filename(slot)
        if p.exists():
            p.unlink()
            return True
        return False

    def commit(self, slot: str, data: Dict[str, Any]) -> bool:
        slots = self.list_slots()
        if slot not in slots and len(slots) >= self.limits.max_slots:
            raise ValueError("SAVE_QUOTA_SLOTS: too many save slots")

        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > self.limits.max_bytes:
            raise ValueError("SAVE_QUOTA_BYTES: save payload too large")

        # v1 (unsigned) format is still supported for reading.
        ver = 1
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        key = _derive_key(self.device_secret, salt=salt, info=(self.app_id + ":" + slot).encode("utf-8"))
        aead = ChaCha20Poly1305(key)
        ct = aead.encrypt(nonce, payload, _aad(self.app_id, slot, ver))

        header = MAGIC + bytes([ver]) + salt + nonce
        blob = header + ct

        p = self.dir / _slot_filename(slot)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(blob)
        os.replace(tmp, p)
        return True

    def load(self, slot: str) -> Optional[Dict[str, Any]]:
        p = self.dir / _slot_filename(slot)
        if not p.exists():
            return None
        blob = p.read_bytes()
        if len(blob) < 4 + 1 + 16 + 12 + 16:
            raise ValueError("SAVE_CORRUPT: file too small")
        if blob[:4] != MAGIC:
            raise ValueError("SAVE_CORRUPT: bad magic")
        ver = int(blob[4])
        if ver not in (1, 2):
            raise ValueError(f"SAVE_UNSUPPORTED_VERSION: {ver}")
        salt = blob[5:21]
        nonce = blob[21:33]

        sig: Optional[bytes] = None
        off = 33
        if ver == 2:
            if len(blob) < off + 2:
                raise ValueError("SAVE_CORRUPT: missing signature")
            sig_len = int.from_bytes(blob[off:off+2], "big")
            off += 2
            if sig_len <= 0 or sig_len > 256:
                raise ValueError("SAVE_CORRUPT: bad signature length")
            if len(blob) < off + sig_len + 16:
                raise ValueError("SAVE_CORRUPT: truncated signature")
            sig = blob[off:off+sig_len]
            off += sig_len

        ct = blob[off:]

        key = _derive_key(self.device_secret, salt=salt, info=(self.app_id + ":" + slot).encode("utf-8"))
        aead = ChaCha20Poly1305(key)
        try:
            pt = aead.decrypt(nonce, ct, _aad(self.app_id, slot, ver))
        except Exception:
            raise ValueError("SAVE_TAMPERED: integrity check failed")

        if len(pt) > self.limits.max_bytes:
            raise ValueError("SAVE_QUOTA_BYTES: payload too large")
        try:
            obj = json.loads(pt.decode("utf-8"))
        except Exception:
            raise ValueError("SAVE_CORRUPT: invalid json")
        if not isinstance(obj, dict):
            raise ValueError("SAVE_CORRUPT: payload must be object")
        # Attach signature if present (used by VM helpers)
        if sig is not None:
            obj["$signature"] = sig.hex()
        return obj

    def commit_signed(self, slot: str, data: Dict[str, Any], *, signature: bytes) -> bool:
        """Commit save file with a detached Ed25519 signature.

        The signature is validated by the game/server key (public key) when loading.

        Signature should be computed over the canonical plaintext payload bytes.
        """
        slots = self.list_slots()
        if slot not in slots and len(slots) >= self.limits.max_slots:
            raise ValueError("SAVE_QUOTA_SLOTS: too many save slots")

        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > self.limits.max_bytes:
            raise ValueError("SAVE_QUOTA_BYTES: save payload too large")

        ver = 2
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        key = _derive_key(self.device_secret, salt=salt, info=(self.app_id + ":" + slot).encode("utf-8"))
        aead = ChaCha20Poly1305(key)
        ct = aead.encrypt(nonce, payload, _aad(self.app_id, slot, ver))

        if not isinstance(signature, (bytes, bytearray)):
            raise ValueError("SAVE_SIGNATURE: invalid signature")
        sig_b = bytes(signature)
        if len(sig_b) <= 0 or len(sig_b) > 256:
            raise ValueError("SAVE_SIGNATURE: invalid signature length")

        header = MAGIC + bytes([ver]) + salt + nonce + len(sig_b).to_bytes(2, "big") + sig_b
        blob = header + ct

        p = self.dir / _slot_filename(slot)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(blob)
        os.replace(tmp, p)
        return True
