"""The probe that decides a run may go to the standalone native binary,
and the one call that runs it."""

from __future__ import annotations

from pathlib import Path

from ....standalone_runtime import standalone_runtime_status


def _standalone_mellow_binary() -> Path | None:
    status = standalone_runtime_status()
    path = Path(str(status.get("binary_path") or ""))
    if status.get("binary_exists") and path.exists():
        return path
    return None


def _can_use_standalone_native(
    *,
    engine: str,
    json_out: bool,
    record_path: str | None,
    replay_path: str | None,
    profile: bool,
    trace: bool,
    step: bool,
    break_lines: str | None,
    watch: str | None,
    ai_timeline: str | None,
    sandbox_profile: str,
    project_mode: bool,
) -> bool:
    return (
        str(engine).lower().strip() == "c"
        and not json_out
        and not record_path
        and not replay_path
        and not profile
        and not trace
        and not step
        and not break_lines
        and not watch
        and not ai_timeline
        and str(sandbox_profile or "default").lower() == "default"
        and not project_mode
    )
