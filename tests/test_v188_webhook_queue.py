from pathlib import Path
import shutil

from mellowlang.agents import add_webhook, receive_webhook, drain_queue, list_dead_letter, retry_queue_item, read_queue_log


def test_retry_and_dead_letter_cycle(tmp_path: Path):
    state = tmp_path / 'sched'
    add_webhook('inbound', 'push', task='handle push', token='abc', state_dir=state)
    rec = receive_webhook('inbound', {'kind': 'push'}, token='abc', state_dir=state)
    assert rec['ok'] and rec['matched'] == 1

    def fail(_item):
        return {'ok': False, 'error': 'boom'}

    first = drain_queue(state_dir=state, callback=fail)
    assert first['items'][0]['status'] == 'retry'
    second = drain_queue(state_dir=state, callback=fail)
    assert second['items'][0]['status'] == 'dead-letter'
    dlq = list_dead_letter(state)
    assert dlq['count'] == 1
    item_id = dlq['items'][0]['id']
    assert retry_queue_item(item_id, state_dir=state)['ok'] is True
    assert read_queue_log(state_dir=state, limit=20)['count'] >= 4
