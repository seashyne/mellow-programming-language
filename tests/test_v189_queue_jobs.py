from __future__ import annotations

import json
from pathlib import Path

from mellowlang.agents.scheduler import submit_job, drain_queue, get_queue_item, queue_stats


def test_submit_job_and_fetch(tmp_path: Path):
    res = submit_job('hello world', state_dir=tmp_path)
    assert res['ok'] is True
    job_id = res['item']['id']
    fetched = get_queue_item(job_id, state_dir=tmp_path)
    assert fetched['ok'] is True
    assert fetched['item']['task'] == 'hello world'


def test_backoff_retry_sets_available_at(tmp_path: Path):
    res = submit_job('retry me', state_dir=tmp_path, retries=2, backoff={'strategy': 'fixed', 'initial_delay_ms': 1000, 'max_delay_ms': 1000})
    job_id = res['item']['id']

    def fail(_item):
        return {'ok': False, 'error': 'boom'}

    out = drain_queue(state_dir=tmp_path, callback=fail)
    assert out['count'] == 1
    fetched = get_queue_item(job_id, state_dir=tmp_path)
    assert fetched['item']['status'] == 'retry'
    assert fetched['item']['available_at']
    assert fetched['item']['next_retry_delay_ms'] == 1000


def test_queue_stats(tmp_path: Path):
    submit_job('one', state_dir=tmp_path)
    data = queue_stats(state_dir=tmp_path)
    assert data['queued'] == 1
    assert data['count'] == 1
