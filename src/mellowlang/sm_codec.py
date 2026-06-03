from __future__ import annotations

import json
import re
import struct
import zlib
from collections import Counter
from pathlib import Path
from typing import Any

MAGIC = b"SM1\x00"
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}|\n[ \t]*|[^A-Za-z_\n]+", re.MULTILINE)


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
    out = bytearray()
    i = 0
    n = len(text)
    max_len = max((len(t) for t in dictionary), default=0)
    while i < n:
        best = None
        upper = min(max_len, n - i)
        for width in range(upper, 2, -1):
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
        chunk = data[i : i + marker]
        i += marker
        out.append(chunk.decode("utf-8"))
    return "".join(out)


def encode_sm_text(text: str) -> bytes:
    dictionary = _build_dictionary(text)
    token_stream = _tokenize(text, dictionary)
    payload = zlib.compress(token_stream, level=9)
    header = {
        "dictionary": dictionary,
        "original_size": len(text.encode("utf-8")),
        "token_stream_size": len(token_stream),
        "codec": "sm1-token-zlib",
    }
    header_blob = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return MAGIC + struct.pack("<I", len(header_blob)) + header_blob + payload


def decode_sm_bytes(data: bytes) -> str:
    if not data.startswith(MAGIC):
        raise ValueError("not an .sm payload")
    if len(data) < len(MAGIC) + 4:
        raise ValueError("truncated .sm payload")
    header_len = struct.unpack("<I", data[len(MAGIC) : len(MAGIC) + 4])[0]
    start = len(MAGIC) + 4
    header = json.loads(data[start : start + header_len].decode("utf-8"))
    payload = zlib.decompress(data[start + header_len :])
    return _detokenize(payload, list(header.get("dictionary") or []))


def encode_file(input_path: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    src = Path(input_path)
    text = src.read_text(encoding="utf-8")
    encoded = encode_sm_text(text)
    out = Path(output_path) if output_path else src.with_suffix(src.suffix + ".sm")
    out.write_bytes(encoded)
    return {
        "input": str(src),
        "output": str(out),
        "input_bytes": len(text.encode("utf-8")),
        "output_bytes": len(encoded),
        "ratio": round(len(encoded) / max(1, len(text.encode("utf-8"))), 4),
        "saved_bytes": len(text.encode("utf-8")) - len(encoded),
        "codec": "sm1-token-zlib",
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
    out.write_text(text, encoding="utf-8")
    return {
        "input": str(src),
        "output": str(out),
        "decoded_bytes": len(text.encode("utf-8")),
        "codec": "sm1-token-zlib",
    }


def inspect_file(path: str | Path) -> dict[str, Any]:
    data = Path(path).read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError("not an .sm payload")
    header_len = struct.unpack("<I", data[len(MAGIC) : len(MAGIC) + 4])[0]
    start = len(MAGIC) + 4
    header = json.loads(data[start : start + header_len].decode("utf-8"))
    return {
        "path": str(path),
        "codec": header.get("codec"),
        "dictionary_entries": len(header.get("dictionary") or []),
        "original_size": header.get("original_size"),
        "token_stream_size": header.get("token_stream_size"),
        "compressed_size": len(data),
    }
