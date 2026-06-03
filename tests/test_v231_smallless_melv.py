from pathlib import Path

from mellowlang.sm_codec import encode_file, decode_file, inspect_file
from mellowlang.melv_codec import inspect_melv


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
