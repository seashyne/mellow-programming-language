from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

MAGIC = b"MELV2"
VERSION = 1
CODEC = "mellow-rgb-rle"
HEADER = struct.Struct("<5sIIIIII")
FRAME_LEN = struct.Struct("<I")


def _read_ppm(path: str | Path) -> tuple[int, int, bytes]:
    data = Path(path).read_bytes()
    tokens: list[bytes] = []
    pos = 0
    n = len(data)
    while len(tokens) < 4:
        while pos < n and data[pos] in b" \t\r\n":
            pos += 1
        if pos < n and data[pos] == ord("#"):
            while pos < n and data[pos] not in b"\r\n":
                pos += 1
            continue
        start = pos
        while pos < n and data[pos] not in b" \t\r\n":
            pos += 1
        if start == pos:
            raise ValueError(f"invalid PPM header: {path}")
        tokens.append(data[start:pos])
    if tokens[0] != b"P6":
        raise ValueError(f"unsupported image format for native MELV: {path} (expected PPM P6)")
    width = int(tokens[1])
    height = int(tokens[2])
    max_value = int(tokens[3])
    if max_value != 255:
        raise ValueError(f"unsupported PPM max value {max_value}: {path}")
    if pos < n and data[pos] in b" \t\r\n":
        pos += 1
    pixels = data[pos:]
    expected = width * height * 3
    if len(pixels) != expected:
        raise ValueError(f"PPM pixel data size mismatch: {path}")
    return width, height, pixels


def _write_ppm(path: Path, width: int, height: int, pixels: bytes) -> None:
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + pixels)


def _replace_output(tmp: Path, out: Path) -> None:
    try:
        tmp.replace(out)
    except PermissionError:
        out.write_bytes(tmp.read_bytes())
        try:
            tmp.unlink(missing_ok=True)
        except PermissionError:
            pass


def _rle_encode_rgb(pixels: bytes) -> bytes:
    if len(pixels) % 3 != 0:
        raise ValueError("RGB payload must be divisible by 3")
    out = bytearray()
    total = len(pixels) // 3
    idx = 0
    while idx < total:
        base = idx * 3
        r, g, b = pixels[base], pixels[base + 1], pixels[base + 2]
        run = 1
        while idx + run < total and run < 255:
            p = (idx + run) * 3
            if pixels[p] != r or pixels[p + 1] != g or pixels[p + 2] != b:
                break
            run += 1
        out.extend((run, r, g, b))
        idx += run
    return bytes(out)


def _rle_decode_rgb(payload: bytes, expected_pixels: int) -> bytes:
    out = bytearray()
    if len(payload) % 4 != 0:
        raise ValueError("invalid MELV RLE payload length")
    for idx in range(0, len(payload), 4):
        run, r, g, b = payload[idx], payload[idx + 1], payload[idx + 2], payload[idx + 3]
        if run == 0:
            raise ValueError("invalid MELV RLE run length 0")
        out.extend(bytes((r, g, b)) * run)
    expected_bytes = expected_pixels * 3
    if len(out) != expected_bytes:
        raise ValueError(f"decoded frame has {len(out)} bytes, expected {expected_bytes}")
    return bytes(out)


def encode_ppm_sequence_to_melv(frame_paths: list[str | Path], output_path: str | Path, *, fps: float = 24.0) -> dict[str, Any]:
    if not frame_paths:
        raise ValueError("native MELV encode needs at least one PPM frame")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        from . import _melv  # type: ignore

        payload = _melv.pack_frames([str(Path(p)) for p in frame_paths], str(out), float(fps))
        if payload.get("ok"):
            payload.update(
                {
                    "output": str(out),
                    "format": "MELV2",
                    "format_version": VERSION,
                    "codec": CODEC,
                    "native": True,
                    "backend": "c",
                    "dependencies": [],
                }
            )
            return payload
    except Exception:
        pass
    fps_num = int(round(float(fps) * 1000))
    fps_den = 1000
    encoded: list[bytes] = []
    width = height = 0
    for idx, frame_path in enumerate(frame_paths):
        w, h, pixels = _read_ppm(frame_path)
        if idx == 0:
            width, height = w, h
        elif (w, h) != (width, height):
            raise ValueError(f"frame size mismatch: {frame_path}")
        encoded.append(_rle_encode_rgb(pixels))
    tmp = out.with_suffix(out.suffix + ".tmp")
    with tmp.open("wb") as fh:
        fh.write(HEADER.pack(MAGIC, VERSION, width, height, fps_num, fps_den, len(encoded)))
        for payload in encoded:
            fh.write(FRAME_LEN.pack(len(payload)))
            fh.write(payload)
    _replace_output(tmp, out)
    return {
        "output": str(out),
        "codec": CODEC,
        "fps": fps_num / fps_den,
        "width": width,
        "height": height,
        "frames": len(encoded),
        "native": True,
        "backend": "python",
        "dependencies": [],
    }


def inspect_native_melv(path: str | Path) -> dict[str, Any]:
    src = Path(path)
    try:
        from . import _melv  # type: ignore

        info = _melv.inspect(str(src))
        if info.get("native") and info.get("codec") == CODEC:
            info["path"] = str(src)
            info["format"] = "MELV2"
            info["backend"] = "c"
            return info
    except Exception:
        pass
    with src.open("rb") as fh:
        header = fh.read(HEADER.size)
        if len(header) != HEADER.size:
            raise ValueError("not a native MELV file")
        magic, version, width, height, fps_num, fps_den, frames = HEADER.unpack(header)
        if magic != MAGIC:
            raise ValueError("not a native MELV2 file")
        for _ in range(frames):
            raw_len = fh.read(FRAME_LEN.size)
            if len(raw_len) != FRAME_LEN.size:
                raise ValueError("truncated MELV frame table")
            (payload_len,) = FRAME_LEN.unpack(raw_len)
            if len(fh.read(payload_len)) != payload_len:
                raise ValueError("truncated MELV frame payload")
    return {
        "path": str(src),
        "ok": True,
        "native": True,
        "codec": CODEC,
        "format": "MELV2",
        "format_version": version,
        "fps": fps_num / fps_den,
        "width": width,
        "height": height,
        "frames": frames,
        "bytes": src.stat().st_size,
        "backend": "python",
    }


def extract_native_melv_frames(input_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    src = Path(input_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    try:
        from . import _melv  # type: ignore

        payload = _melv.extract_native(str(src), str(out))
        if payload.get("ok"):
            return {
                "input": str(src),
                "output": str(out),
                "frames": payload.get("frames"),
                "codec": CODEC,
                "native": True,
                "backend": "c",
            }
    except Exception:
        pass
    with src.open("rb") as fh:
        header = fh.read(HEADER.size)
        if len(header) != HEADER.size:
            raise ValueError("not a native MELV file")
        magic, version, width, height, fps_num, fps_den, frames = HEADER.unpack(header)
        if magic != MAGIC or version != VERSION:
            raise ValueError("not a supported native MELV2 file")
        expected_pixels = width * height
        for idx in range(frames):
            raw_len = fh.read(FRAME_LEN.size)
            if len(raw_len) != FRAME_LEN.size:
                raise ValueError("truncated MELV frame table")
            (payload_len,) = FRAME_LEN.unpack(raw_len)
            payload = fh.read(payload_len)
            if len(payload) != payload_len:
                raise ValueError("truncated MELV frame payload")
            pixels = _rle_decode_rgb(payload, expected_pixels)
            _write_ppm(out / f"{idx:06d}.ppm", width, height, pixels)
    return {"input": str(src), "output": str(out), "frames": frames, "codec": CODEC, "native": True, "backend": "python"}
