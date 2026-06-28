from pathlib import Path

from mellowlang.sm_codec import encode_file, decode_file, inspect_file
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
    assert info["codec"] == "sm1-token-zlib"
    assert Path(out["output"]).read_text(encoding="utf-8") == src.read_text(encoding="utf-8")


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
