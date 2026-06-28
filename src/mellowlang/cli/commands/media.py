from __future__ import annotations

import json

from ..common import _cli_line, _json_print, _lazy_attr

parse_window_file = _lazy_attr("mellowlang.desktop_host", "parse_window_file")
launch_window = _lazy_attr("mellowlang.desktop_host", "launch_window")
desktop_status = _lazy_attr("mellowlang.desktop_host", "desktop_status")
build_desktop_bundle = _lazy_attr("mellowlang.desktop_host", "build_desktop_bundle")
parse_mmg_file = _lazy_attr("mellowlang.mmg_runtime", "parse_mmg_file")
launch_mmg = _lazy_attr("mellowlang.mmg_runtime", "launch_mmg")
mmg_status = _lazy_attr("mellowlang.mmg_runtime", "mmg_status")
mmg_gpu_status = _lazy_attr("mellowlang.mmg_gpu_runtime", "mmg_gpu_status")
build_mmg_gpu_backend = _lazy_attr("mellowlang.mmg_gpu_runtime", "build_mmg_gpu_backend")
export_mmg_gpu_commands = _lazy_attr("mellowlang.mmg_gpu_runtime", "export_mmg_gpu_commands")
run_mmg_gpu_native = _lazy_attr("mellowlang.mmg_gpu_runtime", "run_mmg_gpu_native")
sm_encode_file = _lazy_attr("mellowlang.sm_codec", "encode_file")
sm_decode_file = _lazy_attr("mellowlang.sm_codec", "decode_file")
sm_inspect_file = _lazy_attr("mellowlang.sm_codec", "inspect_file")
encode_video_to_melv = _lazy_attr("mellowlang.melv_codec", "encode_video_to_melv")
decode_melv_to_video = _lazy_attr("mellowlang.melv_codec", "decode_melv_to_video")
inspect_melv = _lazy_attr("mellowlang.melv_codec", "inspect_melv")
extract_melv_frames = _lazy_attr("mellowlang.melv_codec", "extract_melv_frames")
validate_melv = _lazy_attr("mellowlang.melv_codec", "validate_melv")
encode_ppm_sequence_to_melv = _lazy_attr("mellowlang.melv_native_codec", "encode_ppm_sequence_to_melv")
inspect_native_melv = _lazy_attr("mellowlang.melv_native_codec", "inspect_native_melv")
extract_native_melv_frames = _lazy_attr("mellowlang.melv_native_codec", "extract_native_melv_frames")

def _cmd_mmg_status(json_out: bool = False) -> int:
    payload = mmg_status()
    payload["native"] = mmg_gpu_status()
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"mmg runtime: {payload['engine']}")
        print(f"backend: {payload['backend']}")
        print(f"platform: {payload['platform']}")
        print(f"display available: {payload['display_available']}")
        print(payload['note'])
        native = payload['native']
        print(f"native backend: {native['backend']}")
        print(f"native binary exists: {native['binary_exists']}")
        print(f"sdl2 dev: {native['sdl2_dev']}")
    return 0


def _cmd_mmg_run(file: str, dump_spec: bool = False) -> int:
    spec = parse_mmg_file(file)
    if dump_spec:
        print(json.dumps(spec, indent=2, ensure_ascii=False))
        return 0
    return int(launch_mmg(spec) or 0)


def _cmd_mmg_build_native(json_out: bool = False) -> int:
    status = mmg_gpu_status()
    try:
        engine = build_mmg_gpu_backend()
        payload = {**status, "built": True, "engine_path": str(engine)}
    except Exception as exc:
        payload = {**status, "built": False, "error": str(exc)}
        if json_out:
            _json_print(payload)
            return 1
        _cli_line(f"native MMG build failed: {exc}", kind="error")
        _cli_line("tip: install SDL2 development libraries and CMake on the target machine.", kind="hint")
        return 1
    if json_out:
        _json_print(payload)
    else:
        _cli_line(f"native MMG engine built: {payload['engine_path']}", kind="ok")
    return 0


def _cmd_mmg_export_native(file: str, out: str) -> int:
    spec = parse_mmg_file(file)
    path = export_mmg_gpu_commands(spec, out)
    _cli_line(f"exported native MMG scene: {path}", kind="ok")
    return 0


def _cmd_mmg_run_native(file: str, build_if_missing: bool = False, keep_scene: bool = False, scene_out: str | None = None) -> int:
    return int(run_mmg_gpu_native(file, build_if_missing=build_if_missing, keep_scene=keep_scene, scene_out=scene_out) or 0)


def _cmd_sm_pack(input_path: str, out_path: str | None, json_out: bool) -> int:
    payload = sm_encode_file(input_path, out_path)
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"packed {payload['input']} -> {payload['output']} ({payload['ratio']:.2%})")
    return 0


def _cmd_sm_unpack(input_path: str, out_path: str | None, json_out: bool) -> int:
    payload = sm_decode_file(input_path, out_path)
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"unpacked {payload['input']} -> {payload['output']}")
    return 0


def _cmd_sm_inspect(input_path: str, json_out: bool) -> int:
    payload = sm_inspect_file(input_path)
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f".sm codec: {payload['codec']}")
        print(f"dictionary entries: {payload['dictionary_entries']}")
        print(f"original size: {payload['original_size']}")
        print(f"compressed size: {payload['compressed_size']}")
    return 0


def _cmd_melv_encode(input_path: str, out_path: str, fps: float | None, max_frames: int | None, json_out: bool) -> int:
    payload = encode_video_to_melv(input_path, out_path, fps=fps, max_frames=max_frames)
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"encoded {payload['input']} -> {payload['output']} ({payload['frames']} frames)")
    return 0


def _cmd_melv_pack_frames(frame_paths: list[str], out_path: str, fps: float | None, json_out: bool) -> int:
    payload = encode_ppm_sequence_to_melv(frame_paths, out_path, fps=float(fps or 24.0))
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"packed {payload['frames']} PPM frames -> {payload['output']} ({payload['codec']}, native C-readable)")
    return 0


def _cmd_melv_decode(input_path: str, out_path: str, json_out: bool) -> int:
    payload = decode_melv_to_video(input_path, out_path)
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"decoded {payload['input']} -> {payload['output']} ({payload['frames']} frames)")
    return 0


def _cmd_melv_extract_native(input_path: str, out_dir: str, json_out: bool) -> int:
    payload = extract_native_melv_frames(input_path, out_dir)
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"extracted {payload['frames']} native MELV frames to {payload['output']}")
    return 0


def _cmd_melv_extract(input_path: str, out_dir: str, json_out: bool) -> int:
    payload = extract_melv_frames(input_path, out_dir)
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"extracted {payload['frames']} frames to {payload['output']}")
    return 0


def _cmd_melv_inspect(input_path: str, json_out: bool) -> int:
    try:
        payload = inspect_native_melv(input_path)
    except Exception:
        payload = inspect_melv(input_path)
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f".melv codec: {payload['codec']}")
        print(f"size: {payload['width']}x{payload['height']} @ {payload['fps']} fps")
        print(f"frames: {payload['frames']}")
        if payload.get("native"):
            print("backend: native C-readable")
    return 0


def _cmd_melv_validate(input_path: str, strict: bool, json_out: bool) -> int:
    try:
        payload = inspect_native_melv(input_path)
        payload.setdefault("errors", [])
        payload.setdefault("warnings", [])
        payload["ok"] = bool(payload.get("ok", True))
    except Exception:
        payload = validate_melv(input_path, strict=strict)
    if strict and payload.get("warnings"):
        payload["ok"] = False
    if json_out:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        if payload.get("ok"):
            print(f"valid MELV: {input_path}")
        else:
            print(f"invalid MELV: {input_path}")
            for err in payload.get("errors") or []:
                print(f"- {err}")
        for warning in payload.get("warnings") or []:
            print(f"! {warning}")
        if payload.get("native"):
            print("backend: native C-readable")
    return 0 if payload.get("ok") else 1


def _cmd_desktop_status(json_out: bool = False) -> int:
    payload = desktop_status()
    if json_out:
        _json_print(payload)
    else:
        print(f"desktop host: {payload['engine']}")
        print("supported: " + ", ".join(payload.get('supported') or []))
        print("platforms: " + ", ".join(payload.get('cross_platform') or []))
        print(f"builder: {payload.get('builder')}")
    return 0


def _cmd_desktop_build(file: str, out: str, name: str | None, *, onefile: bool, console: bool, json_out: bool) -> int:
    payload = build_desktop_bundle(file, out_dir=out, name=name, onefile=onefile, windowed=not console)
    if json_out:
        _json_print(payload)
    else:
        print(f"bundle: {payload['name']}")
        print(f"entry: {payload['entry']}")
        print(f"out: {payload['out_dir']}")
        print(f"builder: {payload['builder']}")
        print(f"spec: {payload['spec_file']}")
        if payload.get('note'):
            print(payload['note'])
        elif payload.get('built'):
            print('build completed')
    return 0


def _cmd_desktop_run(file: str, dump_spec: bool = False) -> int:
    spec = parse_window_file(file)
    if dump_spec:
        print(json.dumps(spec, ensure_ascii=False, indent=2))
        return 0
    return int(launch_window(spec) or 0)
