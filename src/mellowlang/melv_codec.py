from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

MAGIC = b"MELV1"


def _load_cv2():
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "MELV video encode/decode requires opencv-python. "
            "Install it with: python -m pip install opencv-python"
        ) from exc
    return cv2


def inspect_melv(path: str | Path) -> dict[str, Any]:
    src = Path(path)
    with zipfile.ZipFile(src, "r") as zf:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        entries = [n for n in zf.namelist() if n.startswith("frames/") and n.endswith(".jpg")]
    return {
        "path": str(src),
        "codec": manifest.get("codec"),
        "fps": manifest.get("fps"),
        "width": manifest.get("width"),
        "height": manifest.get("height"),
        "frames": len(entries),
        "source": manifest.get("source"),
    }


def encode_video_to_melv(input_path: str | Path, output_path: str | Path, *, fps: float | None = None, max_frames: int | None = None, jpeg_quality: int = 85) -> dict[str, Any]:
    cv2 = _load_cv2()
    src = Path(input_path)
    out = Path(output_path)
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {src}")
    detected_fps = float(cap.get(cv2.CAP_PROP_FPS) or 24.0)
    use_fps = float(fps or detected_fps or 24.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    count = 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        manifest = {
            "magic": "MELV1",
            "codec": "jpeg-sequence",
            "fps": use_fps,
            "width": width,
            "height": height,
            "source": src.name,
        }
        zf.writestr("magic.bin", MAGIC)
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if max_frames is not None and count >= max_frames:
                break
            enc_ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)])
            if not enc_ok:
                raise RuntimeError(f"failed to encode frame {count}")
            zf.writestr(f"frames/{count:06d}.jpg", buf.tobytes())
            count += 1
        manifest["frames"] = count
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    cap.release()
    return {
        "input": str(src),
        "output": str(out),
        "fps": use_fps,
        "frames": count,
        "width": width,
        "height": height,
    }


def decode_melv_to_video(input_path: str | Path, output_path: str | Path, *, codec: str = "mp4v") -> dict[str, Any]:
    cv2 = _load_cv2()
    src = Path(input_path)
    out = Path(output_path)
    with zipfile.ZipFile(src, "r") as zf:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        frame_names = sorted(n for n in zf.namelist() if n.startswith("frames/") and n.endswith(".jpg"))
        fps = float(manifest.get("fps") or 24.0)
        width = int(manifest.get("width") or 0)
        height = int(manifest.get("height") or 0)
        writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*codec), fps, (width, height))
        if not writer.isOpened():
            raise RuntimeError(f"cannot create output video: {out}")
        frame_count = 0
        for name in frame_names:
            data = zf.read(name)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp.write(data)
                tmp_path = Path(tmp.name)
            frame = cv2.imread(str(tmp_path))
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            if frame is None:
                raise RuntimeError(f"failed to decode frame {name}")
            writer.write(frame)
            frame_count += 1
        writer.release()
    return {
        "input": str(src),
        "output": str(out),
        "fps": fps,
        "frames": frame_count,
        "width": width,
        "height": height,
    }


def extract_melv_frames(input_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    src = Path(input_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src, "r") as zf:
        frame_names = sorted(n for n in zf.namelist() if n.startswith("frames/") and n.endswith(".jpg"))
        for name in frame_names:
            target = out / Path(name).name
            target.write_bytes(zf.read(name))
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"input": str(src), "output": str(out), "frames": len(frame_names)}
