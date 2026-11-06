from pathlib import Path

import json
import struct
import zlib

import pytest

from mellowlang.sm_codec import CODEC_V2, CODEC_V3, decode_file, decode_sm_bytes, encode_file, inspect_file
from mellowlang.melv_codec import inspect_melv
from mellowlang.melv_native_codec import (
    encode_ppm_sequence_to_melv,
    extract_native_melv_frames,
    inspect_native_melv,
)
from mellowlang.cli.main import main as mellow_main


def test_sm_roundtrip(tmp_path: Path):
    src = tmp_path / "demo.mel"
    src.write_text("keep name = \"mellow\"\nkeep name = \"mellow\"\n", encoding="utf-8")
    packed = encode_file(src)
    info = inspect_file(packed["output"])
    out = decode_file(packed["output"], tmp_path / "restored.mel")
    assert info["codec"] in {CODEC_V2, CODEC_V3}
    assert info["version"] in {2, 3}
    assert info["checksum_ok"] is True
    assert Path(out["output"]).read_text(encoding="utf-8") == src.read_text(encoding="utf-8")


def test_sm_reads_legacy_sm1_payload():
    text = "keep name = \"mellow\"\nkeep name = \"mellow\"\n"
    dictionary = ["keep", "name", "mellow", "\n"]
    token_stream = bytearray()
    for ch in text:
        data = ch.encode("utf-8")
        token_stream.append(len(data))
        token_stream.extend(data)
    header = {
        "dictionary": dictionary,
        "original_size": len(text.encode("utf-8")),
        "token_stream_size": len(token_stream),
        "codec": "sm1-token-zlib",
    }
    header_blob = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload = b"SM1\x00" + struct.pack("<I", len(header_blob)) + header_blob + zlib.compress(bytes(token_stream), level=9)
    assert decode_sm_bytes(payload) == text


def test_sm_rejects_corrupt_payload(tmp_path: Path):
    src = tmp_path / "demo.mel"
    src.write_text("keep n = 1\nkeep n = 1\n", encoding="utf-8")
    packed = encode_file(src)
    data = bytearray(Path(packed["output"]).read_bytes())
    data[-1] ^= 0x33
    with pytest.raises(Exception):
        decode_sm_bytes(bytes(data))


def test_native_sm3_roundtrip_when_extension_is_available():
    try:
        from mellowlang import _smnative  # type: ignore
    except Exception:
        pytest.skip("native SM extension is not built")
    text = b"keep score = score + 1\nkeep score = score + 1\n"
    packed = _smnative.pack_bytes(text)
    info = _smnative.inspect_bytes(packed)
    assert info["codec"] == CODEC_V3
    assert info["version"] == 3
    assert info["checksum_ok"] is True
    assert _smnative.unpack_bytes(packed) == text


def test_melv_inspect_fixture(tmp_path: Path):
    import json, zipfile
    melv = tmp_path / "demo.melv"
    with zipfile.ZipFile(melv, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("magic.bin", b"MELV1")
        zf.writestr("manifest.json", json.dumps({"codec": "jpeg-sequence", "fps": 24, "width": 64, "height": 64, "source": "demo.mp4"}))
        zf.writestr("frames/000000.jpg", b"x")
        zf.writestr("frames/000001.jpg", b"y")
    info = inspect_melv(melv)
    assert info["codec"] == "jpeg-sequence"
    assert info["frames"] == 2


def test_native_melv_ppm_roundtrip_without_external_codec(tmp_path: Path):
    frame_a = tmp_path / "a.ppm"
    frame_b = tmp_path / "b.ppm"
    header = b"P6\n2 1\n255\n"
    frame_a.write_bytes(header + bytes([255, 0, 0, 255, 0, 0]))
    frame_b.write_bytes(header + bytes([0, 255, 0, 0, 0, 255]))

    melv = tmp_path / "demo.melv"
    packed = encode_ppm_sequence_to_melv([frame_a, frame_b], melv, fps=12)
    info = inspect_native_melv(melv)
    out = extract_native_melv_frames(melv, tmp_path / "frames")

    assert packed["codec"] == "mellow-rgb-rle"
    assert info["native"] is True
    assert info["codec"] == "mellow-rgb-rle"
    assert info["frames"] == 2
    assert info["width"] == 2
    assert info["height"] == 1
    assert out["frames"] == 2
    assert (tmp_path / "frames" / "000000.ppm").read_bytes() == frame_a.read_bytes()
    assert (tmp_path / "frames" / "000001.ppm").read_bytes() == frame_b.read_bytes()


def test_melv_native_cli_pack_validate_extract(tmp_path: Path):
    frame = tmp_path / "frame.ppm"
    frame.write_bytes(b"P6\n1 1\n255\n" + bytes([10, 20, 30]))
    melv = tmp_path / "cli.melv"
    frames_dir = tmp_path / "frames"

    assert mellow_main(["melv", "pack-frames", str(frame), "-o", str(melv), "--fps", "8"]) == 0
    assert mellow_main(["melv", "validate", str(melv)]) == 0
    assert mellow_main(["melv", "extract-native", str(melv), "-o", str(frames_dir)]) == 0
    assert (frames_dir / "000000.ppm").read_bytes() == frame.read_bytes()
