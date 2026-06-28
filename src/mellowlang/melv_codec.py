from __future__ import annotations

import json
import hashlib
import tempfile
import zipfile
from pathlib import Path
from typing import Any

MAGIC = b"MELV1"
FORMAT_VERSION = 1
DEFAULT_CODEC = "jpeg-sequence"


def _load_cv2():
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "MELV video encode/decode requires opencv-python. "
            "Install it with: python -m pip install opencv-python"
        ) from exc
    return cv2


def _frame_names(zf: zipfile.ZipFile) -> list[str]:
    return sorted(n for n in zf.namelist() if n.startswith("frames/") and n.endswith(".jpg"))


def _read_manifest(zf: zipfile.ZipFile) -> dict[str, Any]:
    try:
        return json.loads(zf.read("manifest.json").decode("utf-8"))
    except KeyError as exc:
        raise ValueError("not a MELV file: missing manifest.json") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("not a MELV file: invalid manifest.json") from exc


def _ensure_parent(path: Path) -> None:
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)


def _replace_output(tmp: Path, out: Path) -> None:
    try:
        tmp.replace(out)
    except PermissionError:
        out.write_bytes(tmp.read_bytes())
        try:
            tmp.unlink(missing_ok=True)
        except PermissionError:
            pass


def inspect_melv(path: str | Path) -> dict[str, Any]:
    src = Path(path)
    with zipfile.ZipFile(src, "r") as zf:
        manifest = _read_manifest(zf)
        entries = _frame_names(zf)
        checksums = ((manifest.get("checksums") or {}).get("sha256") or {})
    return {
        "path": str(src),
        "format": manifest.get("magic") or manifest.get("container"),
        "format_version": manifest.get("format_version", 0),
        "codec": manifest.get("codec"),
        "fps": manifest.get("fps"),
        "width": manifest.get("width"),
        "height": manifest.get("height"),
        "frames": len(entries),
        "expected_frames": manifest.get("frames"),
        "duration_seconds": (len(entries) / float(manifest.get("fps") or 24.0)) if entries else 0.0,
        "bytes": src.stat().st_size,
        "checksum_frames": len(checksums),
        "source": manifest.get("source"),
    }


def validate_melv(path: str | Path, *, strict: bool = False) -> dict[str, Any]:
    src = Path(path)
    errors: list[str] = []
    warnings: list[str] = []
    info: dict[str, Any] = {"path": str(src), "ok": False, "errors": errors, "warnings": warnings}
    if not src.exists():
        errors.append(f"file does not exist: {src}")
        return info
    try:
        with zipfile.ZipFile(src, "r") as zf:
            names = set(zf.namelist())
            if "magic.bin" not in names:
                errors.append("missing magic.bin")
            else:
                try:
                    if zf.read("magic.bin") != MAGIC:
                        errors.append("invalid magic.bin")
                except Exception as exc:
                    errors.append(f"cannot read magic.bin: {exc}")
            try:
                manifest = _read_manifest(zf)
            except ValueError as exc:
                errors.append(str(exc))
                manifest = {}
            frames = _frame_names(zf)
            checksum_map = ((manifest.get("checksums") or {}).get("sha256") or {})
            expected_frames = manifest.get("frames")
            if manifest:
                if (manifest.get("magic") or manifest.get("container")) != "MELV1":
                    errors.append("manifest magic is not MELV1")
                if manifest.get("codec") != DEFAULT_CODEC:
                    errors.append(f"unsupported codec: {manifest.get('codec')}")
                if float(manifest.get("fps") or 0) <= 0:
                    errors.append("fps must be greater than zero")
                if int(manifest.get("width") or 0) <= 0 or int(manifest.get("height") or 0) <= 0:
                    errors.append("width and height must be greater than zero")
                if expected_frames is not None and int(expected_frames) != len(frames):
                    errors.append(f"manifest frames={expected_frames} but archive contains {len(frames)} frames")
            if not frames:
                warnings.append("archive contains no frames")
            expected_names = [f"frames/{idx:06d}.jpg" for idx in range(len(frames))]
            if frames and frames != expected_names:
                warnings.append("frame sequence is not contiguous from 000000.jpg")
            validated = 0
            if checksum_map:
                for name in frames:
                    expected = checksum_map.get(name)
                    if not expected:
                        errors.append(f"missing checksum for {name}")
                        continue
                    actual = hashlib.sha256(zf.read(name)).hexdigest()
                    if actual != expected:
                        errors.append(f"checksum mismatch for {name}")
                    validated += 1
            else:
                warnings.append("manifest has no frame checksums")
            info.update(
                {
                    "codec": manifest.get("codec"),
                    "fps": manifest.get("fps"),
                    "width": manifest.get("width"),
                    "height": manifest.get("height"),
                    "frames": len(frames),
                    "expected_frames": expected_frames,
                    "checksum_frames": validated,
                }
            )
    except zipfile.BadZipFile:
        errors.append("not a zip-based MELV file")
    except Exception as exc:
        errors.append(str(exc))
    info["ok"] = not errors and not (strict and warnings)
    return info


def encode_video_to_melv(input_path: str | Path, output_path: str | Path, *, fps: float | None = None, max_frames: int | None = None, jpeg_quality: int = 85) -> dict[str, Any]:
    cv2 = _load_cv2()
    src = Path(input_path)
    out = Path(output_path)
    _ensure_parent(out)
    if not 1 <= int(jpeg_quality) <= 100:
        raise ValueError("jpeg_quality must be between 1 and 100")
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {src}")
    detected_fps = float(cap.get(cv2.CAP_PROP_FPS) or 24.0)
    use_fps = float(fps or detected_fps or 24.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    count = 0
    checksums: dict[str, str] = {}
    tmp_out = out.with_suffix(out.suffix + ".tmp")
    with zipfile.ZipFile(tmp_out, "w", compression=zipfile.ZIP_STORED) as zf:
        manifest = {
            "magic": "MELV1",
            "format_version": FORMAT_VERSION,
            "codec": DEFAULT_CODEC,
            "fps": use_fps,
            "width": width,
            "height": height,
            "source": src.name,
            "jpeg_quality": int(jpeg_quality),
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
            name = f"frames/{count:06d}.jpg"
            data = buf.tobytes()
            checksums[name] = hashlib.sha256(data).hexdigest()
            zf.writestr(name, data)
            count += 1
        manifest["frames"] = count
        manifest["checksums"] = {"sha256": checksums}
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    cap.release()
    _replace_output(tmp_out, out)
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
    _ensure_parent(out)
    validation = validate_melv(src)
    if validation["errors"]:
        raise ValueError("invalid MELV file: " + "; ".join(validation["errors"]))
    with zipfile.ZipFile(src, "r") as zf:
        manifest = _read_manifest(zf)
        frame_names = _frame_names(zf)
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
    validation = validate_melv(src)
    if validation["errors"]:
        raise ValueError("invalid MELV file: " + "; ".join(validation["errors"]))
    with zipfile.ZipFile(src, "r") as zf:
        frame_names = _frame_names(zf)
        for name in frame_names:
            target = out / Path(name).name
            target.write_bytes(zf.read(name))
        manifest = _read_manifest(zf)
        (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"input": str(src), "output": str(out), "frames": len(frame_names)}
