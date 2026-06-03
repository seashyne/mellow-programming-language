from pathlib import Path
import sys

sys.path.insert(0, str((Path(__file__).resolve().parents[1] / 'src')))

from mellowlang.playground import run_playground_session, replay_recording


def test_v198_records_and_replays():
    payload = run_playground_session("print(\"hello replay\")\n", optimize=True, record_execution=True)
    assert payload['ok'] is True
    rec_id = payload['debugger']['recording_id']
    assert rec_id
    replayed = replay_recording(rec_id)
    assert replayed['ok'] is True
    assert 'hello replay' in replayed['stdout']
    assert replayed['debugger']['replayed_from_recording'] == rec_id


def test_v198_breakpoint_stop_metadata():
    payload = run_playground_session("print(\"a\")\nprint(\"b\")\n", optimize=True, break_lines='2', trace=True, record_execution=False)
    assert payload['ok'] is True
    dbg = payload['debugger']
    assert dbg['break_lines'] == '2'
