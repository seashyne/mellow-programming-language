"""The record, replay and diff trio over a run log - each of them a
`mellow run` with the recording flag already set."""

from __future__ import annotations

from ...common import _json_print

from .run import _cmd_run


def _cmd_replay(file: str, *, replay_path: str, engine: str, json_out: bool) -> int:
    return _cmd_run(
        file,
        json_out=json_out,
        engine=engine,
        record_path=None,
        replay_path=replay_path,
        seed=None,
        global_seed=None,
        allow_ask=False,
        no_wait=False,
        allow_storage=True,
        storage_dir=None,
        allow_unsafe_fs=False,
        max_steps=None,
        max_ms=None,
        syscall_budget=None,
        profile=False,
        trace=False,
        step=False,
        break_lines=None,
        watch=None,
        ai_timeline=None,
        color=False,
        no_color=False,
        registry=None,
        no_resolve=False,
        sandbox_profile="default",
        allow_data_write=False,
        data_max_batch_size=None,
        data_max_query_rows=None,
        data_max_record_bytes=None,
        data_max_open_streams=None,
        native_required=False,
    )


def _cmd_record(
    file: str,
    *,
    record_path: str,
    engine: str,
    seed: int | None,
    global_seed: int | None,
    json_out: bool,
) -> int:
    return _cmd_run(
        file,
        json_out=json_out,
        engine=engine,
        record_path=record_path,
        replay_path=None,
        seed=seed,
        global_seed=global_seed,
        allow_ask=False,
        no_wait=False,
        allow_storage=True,
        storage_dir=None,
        allow_unsafe_fs=False,
        max_steps=None,
        max_ms=None,
        syscall_budget=None,
        profile=False,
        trace=False,
        step=False,
        break_lines=None,
        watch=None,
        ai_timeline=None,
        color=False,
        no_color=False,
        registry=None,
        no_resolve=False,
        sandbox_profile="default",
        allow_data_write=False,
        data_max_batch_size=None,
        data_max_query_rows=None,
        data_max_record_bytes=None,
        data_max_open_streams=None,
        native_required=False,
    )


def _cmd_diff(a: str, b: str, *, json_out: bool) -> int:
    import json
    def load(path: str) -> list[dict[str, Any]]:
        out = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
    la = load(a)
    lb = load(b)
    n = min(len(la), len(lb))
    first = None
    for i in range(n):
        if la[i] != lb[i]:
            first = {"index": i, "a": la[i], "b": lb[i]}
            break
    if first is None and len(la) != len(lb):
        first = {"index": n, "a": la[n] if len(la) > n else None, "b": lb[n] if len(lb) > n else None, "note": "length mismatch"}
    ok = first is None
    out = {"ok": ok, "first_diff": first, "len_a": len(la), "len_b": len(lb)}
    if json_out:
        _json_print(out)
    else:
        if ok:
            print("logs are identical")
        else:
            print(f"first difference at index {first['index']}")
    return 0 if ok else 1
