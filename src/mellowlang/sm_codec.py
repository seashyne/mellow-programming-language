from __future__ import annotations

import json
import re
import struct
import zlib
from collections import Counter
from pathlib import Path
from typing import Any

MAGIC_V1 = b"SM1\x00"
MAGIC_V2 = b"SM2\x00"
MAGIC_V3 = b"SM3\x00"
MAGIC = MAGIC_V2
CODEC_V1 = "sm1-token-zlib"
CODEC_V2 = "sm2-token-zlib-crc32"
CODEC_V3 = "sm3-token-native-crc32"
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}|\n[ \t]*|[^A-Za-z_\n]+", re.MULTILINE)


def _native_sm():
    try:
        from . import _smnative  # type: ignore

        return _smnative
    except Exception:
        return None


def _codec_for_payload(data: bytes) -> str:
    if data.startswith(MAGIC_V3):
        return CODEC_V3
    if data.startswith(MAGIC_V2):
        return CODEC_V2
    if data.startswith(MAGIC_V1):
        return CODEC_V1
    return "unknown"


def _build_dictionary(text: str, max_entries: int = 240) -> list[str]:
    counts = Counter(TOKEN_RE.findall(text))
    scored: list[tuple[int, str]] = []
    for token, count in counts.items():
        if count < 2 or len(token) < 3:
            continue
        saving = (len(token) - 2) * count
        if saving > 3:
            scored.append((saving, token))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [token for _, token in scored[:max_entries]]


def _tokenize(text: str, dictionary: list[str]) -> bytes:
    token_to_id = {tok: i for i, tok in enumerate(dictionary)}
    token_lengths = sorted({len(tok) for tok in dictionary if len(tok) > 2}, reverse=True)
    out = bytearray()
    i = 0
    n = len(text)
    while i < n:
        best = None
        for width in token_lengths:
            if width > n - i:
                continue
            chunk = text[i : i + width]
            idx = token_to_id.get(chunk)
            if idx is not None:
                best = (idx, chunk)
                break
        if best is not None:
            idx, chunk = best
            out.append(0xFF)
            out.append(idx)
            i += len(chunk)
            continue
        ch = text[i]
        data = ch.encode("utf-8")
        out.append(len(data))
        out.extend(data)
        i += 1
    return bytes(out)


def _detokenize(data: bytes, dictionary: list[str]) -> str:
    out: list[str] = []
    i = 0
    n = len(data)
    while i < n:
        marker = data[i]
        i += 1
        if marker == 0xFF:
            if i >= n:
                raise ValueError("truncated SM token stream")
            idx = data[i]
            i += 1
            try:
                out.append(dictionary[idx])
            except IndexError as exc:
                raise ValueError(f"invalid SM token index {idx}") from exc
            continue
        if marker == 0:
            raise ValueError("invalid SM literal length 0")
        if i + marker > n:
            raise ValueError("truncated SM literal")
        chunk = data[i : i + marker]
        i += marker
        out.append(chunk.decode("utf-8"))
    return "".join(out)


def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def _read_container(data: bytes) -> tuple[bytes, dict[str, Any], bytes]:
    magic = data[: len(MAGIC_V1)]
    if magic not in {MAGIC_V1, MAGIC_V2}:
        raise ValueError("not an .sm payload")
    if len(data) < len(magic) + 4:
        raise ValueError("truncated .sm payload")
    header_len = struct.unpack("<I", data[len(magic) : len(magic) + 4])[0]
    start = len(magic) + 4
    end = start + header_len
    if header_len <= 0 or end > len(data):
        raise ValueError("truncated .sm header")
    try:
        header = json.loads(data[start:end].decode("utf-8"))
    except Exception as exc:
        raise ValueError("invalid .sm header") from exc
    payload = data[end:]
    payload_size = header.get("payload_size")
    if payload_size is not None and int(payload_size) != len(payload):
        raise ValueError("SM payload size mismatch")
    return magic, header, payload


def encode_sm_text(text: str) -> bytes:
    native = _native_sm()
    if native is not None:
        return bytes(native.pack_bytes(text.encode("utf-8")))
    dictionary = _build_dictionary(text)
    token_stream = _tokenize(text, dictionary)
    payload = zlib.compress(token_stream, level=9)
    raw = text.encode("utf-8")
    header = {
        "version": 2,
        "dictionary": dictionary,
        "original_size": len(raw),
        "token_stream_size": len(token_stream),
        "payload_size": len(payload),
        "text_crc32": _crc32(raw),
        "token_crc32": _crc32(token_stream),
        "codec": _codec_for_payload(encoded),
    }
    header_blob = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return MAGIC + struct.pack("<I", len(header_blob)) + header_blob + payload


def decode_sm_bytes(data: bytes) -> str:
    if data.startswith(MAGIC_V3):
        native = _native_sm()
        if native is None:
            raise ValueError("SM3 native codec is not available; rebuild with `mellow native build` or install from this checkout")
        return bytes(native.unpack_bytes(data)).decode("utf-8")
    _magic, header, payload = _read_container(data)
    token_stream = zlib.decompress(payload)
    token_stream_size = header.get("token_stream_size")
    if token_stream_size is not None and int(token_stream_size) != len(token_stream):
        raise ValueError("SM token stream size mismatch")
    token_crc32 = header.get("token_crc32")
    if token_crc32 is not None and int(token_crc32) != _crc32(token_stream):
        raise ValueError("SM token stream checksum mismatch")
    text = _detokenize(token_stream, list(header.get("dictionary") or []))
    raw = text.encode("utf-8")
    original_size = header.get("original_size")
    if original_size is not None and int(original_size) != len(raw):
        raise ValueError("SM original size mismatch")
    text_crc32 = header.get("text_crc32")
    if text_crc32 is not None and int(text_crc32) != _crc32(raw):
        raise ValueError("SM text checksum mismatch")
    return text


def encode_file(input_path: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    src = Path(input_path)
    input_bytes = src.read_bytes()
    text = input_bytes.decode("utf-8")
    encoded = encode_sm_text(text)
    out = Path(output_path) if output_path else src.with_suffix(src.suffix + ".sm")
    out.write_bytes(encoded)
    return {
        "input": str(src),
        "output": str(out),
        "input_bytes": len(input_bytes),
        "output_bytes": len(encoded),
        "ratio": round(len(encoded) / max(1, len(input_bytes)), 4),
        "saved_bytes": len(input_bytes) - len(encoded),
        "codec": _codec_for_payload(encoded),
    }


def decode_file(input_path: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    src = Path(input_path)
    text = decode_sm_bytes(src.read_bytes())
    if output_path is None:
        if src.suffix == ".sm":
            out = src.with_suffix("")
            if out == src:
                out = src.with_name(src.name + ".decoded")
        else:
            out = src.with_name(src.name + ".decoded")
    else:
        out = Path(output_path)
    decoded = text.encode("utf-8")
    out.write_bytes(decoded)
    return {
        "input": str(src),
        "output": str(out),
        "decoded_bytes": len(decoded),
        "codec": _codec_for_payload(src.read_bytes()),
    }


def inspect_file(path: str | Path) -> dict[str, Any]:
    data = Path(path).read_bytes()
    if data.startswith(MAGIC_V3):
        native = _native_sm()
        if native is None:
            raise ValueError("SM3 native codec is not available; rebuild with `mellow native build` or install from this checkout")
        payload = dict(native.inspect_bytes(data))
        payload["path"] = str(path)
        return payload
    magic, header, payload = _read_container(data)
    checksum_ok = None
    try:
        token_stream = zlib.decompress(payload)
        checksum_ok = True
        if header.get("token_stream_size") is not None:
            checksum_ok = checksum_ok and int(header["token_stream_size"]) == len(token_stream)
        if header.get("token_crc32") is not None:
            checksum_ok = checksum_ok and int(header["token_crc32"]) == _crc32(token_stream)
        if header.get("text_crc32") is not None or header.get("original_size") is not None:
            text = _detokenize(token_stream, list(header.get("dictionary") or []))
            raw = text.encode("utf-8")
            if header.get("original_size") is not None:
                checksum_ok = checksum_ok and int(header["original_size"]) == len(raw)
            if header.get("text_crc32") is not None:
                checksum_ok = checksum_ok and int(header["text_crc32"]) == _crc32(raw)
    except Exception:
        checksum_ok = False
    return {
        "path": str(path),
        "codec": header.get("codec"),
        "version": header.get("version", 1 if magic == MAGIC_V1 else 2),
        "dictionary_entries": len(header.get("dictionary") or []),
        "original_size": header.get("original_size"),
        "token_stream_size": header.get("token_stream_size"),
        "payload_size": header.get("payload_size", len(payload)),
        "compressed_size": len(data),
        "checksum_ok": checksum_ok,
    }
