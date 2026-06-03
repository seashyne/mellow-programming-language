from pathlib import Path

from mellowlang.agents import add_trigger, emit_event, list_queue, drain_queue, add_webhook, receive_webhook


def test_event_trigger_enqueue_and_drain(tmp_path: Path):
    add_trigger('doc-sync', 'docs.updated', 'summarize docs', state_dir=tmp_path)
    payload = emit_event('docs.updated', {'repo': 'mellow'}, state_dir=tmp_path)
    assert payload['matched'] == 1
    q = list_queue(tmp_path)
    assert q['queued'] == 1
    drained = drain_queue(state_dir=tmp_path)
    assert drained['count'] == 1


def test_webhook_enqueue(tmp_path: Path):
    created = add_webhook('incoming', 'webhook.received', task='handle webhook', state_dir=tmp_path)
    token = created['webhook']['token']
    payload = receive_webhook('incoming', {'kind': 'push'}, token=token, state_dir=tmp_path)
    assert payload['matched'] == 1
