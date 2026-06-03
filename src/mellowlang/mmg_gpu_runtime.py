from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

from .mmg_runtime import parse_mmg_file

ROOT = Path(__file__).resolve().parents[2]
NATIVE_DIR = ROOT / "native" / "mmg_gpu"
BUILD_DIR = NATIVE_DIR / "build"
SCRIPTS_DIR = NATIVE_DIR / "scripts"
SHADERS_DIR = NATIVE_DIR / "shaders"
BIN_NAME = "mmg_gpu.exe" if os.name == "nt" else "mmg_gpu"


def _pkg_config_version(name: str) -> str | None:
    try:
        out = subprocess.check_output(["pkg-config", "--modversion", name], stderr=subprocess.DEVNULL, text=True).strip()
        return out or None
    except Exception:
        return None


def _find_program(name: str) -> str | None:
    return shutil.which(name)


def _engine_path(build_dir: Path | None = None) -> Path:
    base = build_dir or BUILD_DIR
    candidate = base / BIN_NAME
    if candidate.exists():
        return candidate
    rel = base / "Release" / BIN_NAME
    return rel if rel.exists() else candidate


def mmg_gpu_status() -> Dict[str, Any]:
    sdl2 = _pkg_config_version("sdl2")
    sdl2_image = _pkg_config_version("SDL2_image") or _pkg_config_version("sdl2_image")
    engine = _engine_path()
    return {
        "engine": "mmg-gpu-native",
        "backend": "sdl2-opengl-vbo",
        "platform": platform.system().lower(),
        "source_dir": str(NATIVE_DIR),
        "build_dir": str(BUILD_DIR),
        "binary": str(engine),
        "binary_exists": engine.exists(),
        "cmake": _find_program("cmake"),
        "sdl2_dev": bool(sdl2),
        "sdl2_version": sdl2,
        "png_loader": "sdl2_image" if sdl2_image else "bmp-fallback",
        "sprite_batching": True,
        "shader_pipeline": True,
        "vbo_renderer": True,
        "input_callbacks": True,
        "state_callbacks": True,
        "runtime_bridge": True,
        "shader_dir": str(SHADERS_DIR),
        "build_scripts": {
            "windows_bat": str(SCRIPTS_DIR / "build_windows.bat"),
            "windows_ps1": str(SCRIPTS_DIR / "build_windows.ps1"),
            "linux_sh": str(SCRIPTS_DIR / "build_linux.sh"),
        },
        "sdl2_image_version": sdl2_image,
        "note": "Native MMG GPU backend uses SDL2 + OpenGL, shader files, VBO sprite batches, and runtime callback metadata.",
    }


def build_mmg_gpu_backend(build_dir: Path | None = None, *, release: bool = True) -> Path:
    build_dir = build_dir or BUILD_DIR
    build_dir.mkdir(parents=True, exist_ok=True)
    cmake = _find_program("cmake")
    if not cmake:
        raise RuntimeError("cmake not found")
    cfg = "Release" if release else "Debug"
    subprocess.check_call([cmake, "-S", str(NATIVE_DIR), "-B", str(build_dir), f"-DCMAKE_BUILD_TYPE={cfg}"])
    subprocess.check_call([cmake, "--build", str(build_dir), "--config", cfg])
    engine = _engine_path(build_dir)
    if not engine.exists():
        raise RuntimeError(f"built engine not found at {engine}")
    return engine


def _hex_to_rgba(value: str) -> tuple[float, float, float, float]:
    raw = (value or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) == 6:
        raw += "ff"
    if len(raw) != 8:
        return (1.0, 1.0, 1.0, 1.0)
    return tuple(int(raw[i : i + 2], 16) / 255.0 for i in range(0, 8, 2))  # type: ignore[return-value]


def _esc(text: Any) -> str:
    s = str(text)
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def export_mmg_gpu_commands(spec: Dict[str, Any], out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("MMGSCENE 3")
    lines.append(f'APP "{_esc(spec.get("title", "MMG App"))}" {int(spec.get("width", 960))} {int(spec.get("height", 640))}')
    r, g, b, a = _hex_to_rgba(str(spec.get("clear", "#101418")))
    lines.append(f"CLEAR {r:.6f} {g:.6f} {b:.6f} {a:.6f}")
    cam = spec.get("camera") or {}
    lines.append(f"CAMERA {float(cam.get('x', 0.0)):.3f} {float(cam.get('y', 0.0)):.3f} {float(cam.get('zoom', 1.0)):.3f}")
    frame = spec.get("frame") or {}
    lines.append(f"FRAME {int(frame.get('fps', spec.get('fps', 60)) or 60)}")
    lines.append("PIPELINE sprite_batching=1 shader_pipeline=1 input_callbacks=1 state_callbacks=1 runtime_bridge=1")
    lines.append(f'SHADER "sprite" "{_esc((SHADERS_DIR / "sprite.vert").as_posix())}" "{_esc((SHADERS_DIR / "sprite.frag").as_posix())}"')
    lines.append(f'SHADER "color" "{_esc((SHADERS_DIR / "color.vert").as_posix())}" "{_esc((SHADERS_DIR / "color.frag").as_posix())}"')

    state = spec.get("state") or {}
    if state:
        for key, value in state.items():
            if isinstance(value, bool):
                kind, payload = "bool", ("1" if value else "0")
            elif isinstance(value, int) and not isinstance(value, bool):
                kind, payload = "int", str(value)
            elif isinstance(value, float):
                kind, payload = "float", repr(value)
            else:
                kind, payload = "str", _esc(value)
            lines.append(f'STATE "{_esc(key)}" {kind} "{payload}"')
            lines.append(f'BRIDGE_STATE "{_esc(key)}" {kind} "{payload}"')

    for tex in spec.get("textures") or []:
        lines.append(f'TEXTURE "{_esc(tex.get("id", "tex"))}" "{_esc(tex.get("source", ""))}"')

    draws: list[dict[str, Any]] = []
    draws.extend(spec.get("draw") or [])
    for scene in spec.get("scenes") or []:
        lines.append(f'SCENE "{_esc(scene.get("id", "main"))}" {1 if scene.get("active", True) else 0}')
        draws.extend(scene.get("draw") or [])
        batch_count = 0
        batch_texture = ""
        for sprite in scene.get("sprites") or []:
            rr, gg, bb, aa = _hex_to_rgba(str(sprite.get("fill", "#ffffff")))
            tex_id = str(sprite.get("texture", ""))
            lines.append(
                f'SPRITE "{_esc(sprite.get("id", "sprite"))}" "{_esc(tex_id)}" '
                f'{float(sprite.get("x", 0)):.3f} {float(sprite.get("y", 0)):.3f} '
                f'{float(sprite.get("w", 64)):.3f} {float(sprite.get("h", 64)):.3f} '
                f'{rr:.6f} {gg:.6f} {bb:.6f} {aa:.6f}'
            )
            batch_count += 1
            batch_texture = batch_texture or tex_id
        if batch_count:
            lines.append(f'BATCH_GROUP "{_esc(scene.get("id", "main"))}" "{_esc(batch_texture)}" {batch_count}')

    for item in draws:
        kind = item.get("type")
        if kind == "rect":
            rr, gg, bb, aa = _hex_to_rgba(str(item.get("fill", "#ffffff")))
            lines.append(
                f'RECT {float(item.get("x", 0)):.3f} {float(item.get("y", 0)):.3f} {float(item.get("w", 0)):.3f} {float(item.get("h", 0)):.3f} '
                f'{rr:.6f} {gg:.6f} {bb:.6f} {aa:.6f}'
            )
        elif kind == "line":
            rr, gg, bb, aa = _hex_to_rgba(str(item.get("stroke", "#ffffff")))
            lines.append(
                f'LINE {float(item.get("x1", 0)):.3f} {float(item.get("y1", 0)):.3f} {float(item.get("x2", 0)):.3f} {float(item.get("y2", 0)):.3f} '
                f'{rr:.6f} {gg:.6f} {bb:.6f} {aa:.6f} {float(item.get("width", 1)):.3f}'
            )
        elif kind == "circle":
            rr, gg, bb, aa = _hex_to_rgba(str(item.get("fill", "#ffffff")))
            lines.append(
                f'CIRCLE {float(item.get("x", 0)):.3f} {float(item.get("y", 0)):.3f} {float(item.get("r", 0)):.3f} '
                f'{rr:.6f} {gg:.6f} {bb:.6f} {aa:.6f}'
            )
        elif kind == "text":
            rr, gg, bb, aa = _hex_to_rgba(str(item.get("fill", "#ffffff")))
            lines.append(
                f'TEXT {float(item.get("x", 0)):.3f} {float(item.get("y", 0)):.3f} {int(item.get("size", 16))} '
                f'{rr:.6f} {gg:.6f} {bb:.6f} {aa:.6f} "{_esc(item.get("text", ""))}"'
            )

    for evt in spec.get("events") or []:
        event = str(evt.get("event") or "")
        match = str(evt.get("match") or "")
        action = evt.get("action") or {}
        action_type = str(action.get("type") or "noop")
        payload = _esc(action.get("message") or action.get("key") or action.get("value") or action.get("script") or "")
        if event == "key":
            lines.append(f'ON_KEY "{_esc(match)}" {action_type.upper()} "{payload}"')
            lines.append(f'BRIDGE_EVENT "key" "{_esc(match)}" {action_type.upper()} "{payload}"')
        elif event == "mouse":
            lines.append(f'ON_MOUSE "{_esc(match)}" {action_type.upper()} "{payload}"')
            lines.append(f'BRIDGE_EVENT "mouse" "{_esc(match)}" {action_type.upper()} "{payload}"')

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def run_mmg_gpu_native(path: str | Path, *, build_if_missing: bool = False, keep_scene: bool = False, scene_out: str | Path | None = None) -> int:
    spec = parse_mmg_file(path)
    if scene_out is None:
        tmp = tempfile.NamedTemporaryFile(prefix="mellow_mmg_", suffix=".mmgscene", delete=False)
        tmp.close()
        scene_path = Path(tmp.name)
    else:
        scene_path = Path(scene_out)
    export_mmg_gpu_commands(spec, scene_path)
    engine = _engine_path()
    if not engine.exists():
        if build_if_missing:
            engine = build_mmg_gpu_backend()
        else:
            raise RuntimeError("MMG GPU engine binary not found. Run `mellow mmg build-native` first.")
    try:
        proc = subprocess.run([str(engine), str(scene_path)], check=False)
        return int(proc.returncode)
    finally:
        if (not keep_scene) and scene_out is None:
            try:
                scene_path.unlink(missing_ok=True)
            except Exception:
                pass
