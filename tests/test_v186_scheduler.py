
from datetime import datetime, timezone
from pathlib import Path

from mellowlang.agents.scheduler import add_job, list_jobs, run_due_jobs, run_background_runner, read_runner_status


def test_schedule_add_and_run_due(tmp_path: Path):
    now = datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc)
    res = add_job('daily-summary', '* * * * *', 'summarize docs', state_dir=tmp_path)
    assert res['ok'] is True
    listed = list_jobs(tmp_path)
    assert listed['count'] == 1
    due = run_due_jobs(state_dir=tmp_path, now=now, callback=lambda job: {'ok': True, 'task': job['task']})
    assert due['count'] == 1
    listed2 = list_jobs(tmp_path)
    assert listed2['items'][0]['run_count'] == 1
    assert listed2['items'][0]['last_result']['task'] == 'summarize docs'


def test_background_runner_status(tmp_path: Path):
    add_job('worker-job', '* * * * *', 'plan release', state_dir=tmp_path)
    res = run_background_runner(state_dir=tmp_path, interval_s=0, iterations=2, callback=lambda job: {'ok': True, 'name': job['name']})
    assert res['ok'] is True
    assert res['iterations'] == 2
    status = read_runner_status(tmp_path)
    assert status['running'] is False
    assert status['executed_jobs'] >= 1
