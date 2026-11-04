"""The background surface: scheduled jobs, triggers, webhooks, the queue, job listing and the runner loop."""

from __future__ import annotations

from typing import Any
import contextlib
import io
import json

from ...common import _cli_line, _json_print
from .deps import (
    Workflow, WorkflowRunner, WorkflowStep, add_job,
    agent_list_jobs, run_due_jobs, run_background_runner, read_runner_status,
    add_trigger, list_triggers, emit_event, add_webhook,
    list_webhooks, receive_webhook, submit_job, get_queue_item,
    list_queue, drain_queue, list_dead_letter, retry_queue_item,
    read_queue_log, queue_stats, start_webhook_server, read_webhook_server_status,
    read_job_api_status,
)
from .support import _make_agent_runtime, _parse_filters, _parse_jsonish, _run_agent_package

def _scheduled_job_callback(job: dict[str, Any]) -> dict[str, Any]:
    if str(job.get('kind') or 'run') == 'workflow':
        runtime = _make_agent_runtime(str(job.get('model') or 'rule-based'), str(job.get('memory') or '.mellow/agent_memory.jsonl'), str(job.get('obs') or '.mellow/agent_observability.jsonl'), ['search.docs', 'time.now'], [], job.get('rag_file'), sandbox=bool(job.get('sandbox')), allow_caps=list(job.get('allow_caps') or []), secrets=list(job.get('secrets') or []))
        steps = [
            WorkflowStep('recall-memory', 'memory', retries=int(job.get('retries') or 0), timeout_ms=job.get('timeout_ms')),
            WorkflowStep('retrieve-context', 'rag', retries=int(job.get('retries') or 0), timeout_ms=job.get('timeout_ms')),
        ]
        if job.get('parallel'):
            steps.append(WorkflowStep('parallel-context', 'parallel', {'steps': [
                {'name': 'search-docs', 'kind': 'tool', 'payload': {'tool': 'search.docs', 'input': {'query': job['task']}}, 'retries': int(job.get('retries') or 0), 'timeout_ms': job.get('timeout_ms')},
                {'name': 'stamp-time', 'kind': 'tool', 'payload': {'tool': 'time.now', 'input': {}}, 'retries': int(job.get('retries') or 0), 'timeout_ms': job.get('timeout_ms')},
            ]}, retries=int(job.get('retries') or 0), timeout_ms=job.get('timeout_ms')))
        else:
            steps.append(WorkflowStep('search-docs', 'tool', {'tool': 'search.docs', 'input': {'query': job['task']}}, retries=int(job.get('retries') or 0), timeout_ms=job.get('timeout_ms')))
        steps.append(WorkflowStep('generate-answer', 'model', retries=int(job.get('retries') or 0), timeout_ms=job.get('timeout_ms')))
        result = WorkflowRunner(runtime).run(Workflow(name=f"scheduled-{job['name']}", steps=steps), str(job['task']))
        return {'ok': True, 'kind': 'workflow', 'workflow': result}
    if job.get('package'):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = _run_agent_package(str(job['package']), str(job['task']), json_out=True, sandbox=bool(job.get('sandbox')), allow_caps=list(job.get('allow_caps') or []), secrets=list(job.get('secrets') or []), timeout_ms=job.get('timeout_ms'))
        raw = buf.getvalue().strip()
        try:
            payload = json.loads(raw.splitlines()[-1]) if raw else {'ok': code == 0}
        except Exception:
            payload = {'ok': code == 0, 'raw': raw}
        return payload
    runtime = _make_agent_runtime(str(job.get('model') or 'rule-based'), str(job.get('memory') or '.mellow/agent_memory.jsonl'), str(job.get('obs') or '.mellow/agent_observability.jsonl'), [], [], job.get('rag_file'), sandbox=bool(job.get('sandbox')), allow_caps=list(job.get('allow_caps') or []), secrets=list(job.get('secrets') or []))
    result = runtime.run(str(job['task']), timeout_ms=job.get('timeout_ms'))
    return {'ok': True, 'kind': 'run', 'answer': result.answer, 'structured': result.structured, 'run_id': result.debug.get('run_id')}

def _cmd_agent_schedule(action: str, *, name: str | None = None, cron: str | None = None, task: str | None = None, kind: str = 'run', package: str | None = None, model: str = 'rule-based', memory: str = '.mellow/agent_memory.jsonl', obs: str = '.mellow/agent_observability.jsonl', rag_file: str | None = None, retries: int = 1, timeout_ms: int | None = None, parallel: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, secrets: list[str] | None = None, backoff: dict[str, Any] | None = None, json_out: bool = False) -> int:
    if action == 'add':
        payload = add_job(str(name), str(cron), str(task), kind=kind, package=package, model=model, memory=memory, obs=obs, rag_file=rag_file, retries=retries, timeout_ms=timeout_ms, parallel=parallel, sandbox=sandbox, allow_caps=allow_caps, secrets=secrets, backoff=backoff)
    elif action == 'run-due':
        payload = run_due_jobs(callback=_scheduled_job_callback)
    else:
        payload = agent_list_jobs()
    if json_out:
        _json_print(payload)
    else:
        if action == 'add' and payload.get('ok'):
            job = payload['job']
            _cli_line('Scheduled agent job created', kind='ok')
            print(f"Job ID          : {job['id']}")
            print(f"Name            : {job['name']}")
            print(f"Cron            : {job['schedule']}")
            print(f"Next run        : {job['next_run']}")
        elif action == 'run-due' and payload.get('ok'):
            _cli_line(f"Executed {payload.get('count', 0)} scheduled job(s)", kind='ok')
            for item in payload.get('items') or []:
                print(f"- {item['name']} -> {json.dumps(item.get('result'), ensure_ascii=False)}")
        else:
            _cli_line(f"Scheduled jobs: {payload.get('count', 0)}", kind='ok')
            for item in payload.get('items') or []:
                print(f"- {item['name']} [{item['kind']}] cron={item['schedule']} next={item.get('next_run')} runs={item.get('run_count', 0)}")
    return 0 if payload.get('ok') else 1

def _cmd_agent_trigger(action: str, *, name: str | None = None, event: str | None = None, task: str | None = None, kind: str = 'run', package: str | None = None, model: str = 'rule-based', memory: str = '.mellow/agent_memory.jsonl', obs: str = '.mellow/agent_observability.jsonl', rag_file: str | None = None, retries: int = 1, timeout_ms: int | None = None, parallel: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, secrets: list[str] | None = None, filters: list[str] | None = None, payload: str | None = None, backoff: dict[str, Any] | None = None, json_out: bool = False) -> int:
    if action == 'add':
        data = add_trigger(str(name), str(event), str(task), kind=kind, package=package, model=model, memory=memory, obs=obs, rag_file=rag_file, retries=retries, timeout_ms=timeout_ms, parallel=parallel, sandbox=sandbox, allow_caps=allow_caps, secrets=secrets, filters=_parse_filters(filters), backoff=backoff)
    elif action == 'emit':
        data = emit_event(str(event), _parse_jsonish(payload))
    else:
        data = list_triggers()
    if json_out:
        _json_print(data)
    else:
        if action == 'add' and data.get('ok'):
            trig = data['trigger']
            _cli_line('Event trigger created', kind='ok')
            print(f"Trigger ID       : {trig['id']}")
            print(f"Name             : {trig['name']}")
            print(f"Event            : {trig['event']}")
        elif action == 'emit' and data.get('ok'):
            _cli_line(f"Queued {data.get('matched', 0)} job(s) for event {data.get('event')}", kind='ok')
        else:
            _cli_line(f"Event triggers: {data.get('count', 0)}", kind='ok')
            for item in data.get('items') or []:
                print(f"- {item['name']} event={item['event']} kind={item['kind']} runs={item.get('run_count', 0)}")
    return 0 if data.get('ok') else 1

def _cmd_agent_webhook(action: str, *, name: str | None = None, event: str | None = None, task: str | None = None, token: str | None = None, kind: str = 'run', package: str | None = None, model: str = 'rule-based', memory: str = '.mellow/agent_memory.jsonl', obs: str = '.mellow/agent_observability.jsonl', rag_file: str | None = None, retries: int = 1, timeout_ms: int | None = None, parallel: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, secrets: list[str] | None = None, payload: str | None = None, host: str = '127.0.0.1', port: int = 8788, token_header: str = 'X-Mellow-Webhook-Token', enable_job_api: bool = True, backoff: dict[str, Any] | None = None, json_out: bool = False) -> int:
    if action == 'add':
        data = add_webhook(str(name), str(event), token=token, task=str(task), kind=kind, package=package, model=model, memory=memory, obs=obs, rag_file=rag_file, retries=retries, timeout_ms=timeout_ms, parallel=parallel, sandbox=sandbox, allow_caps=allow_caps, secrets=secrets, backoff=backoff)
    elif action == 'receive':
        data = receive_webhook(str(name), _parse_jsonish(payload), token=token)
    elif action == 'serve':
        data = start_webhook_server(host=host, port=port, token_header=token_header, enable_job_api=enable_job_api)
    elif action == 'status':
        data = read_webhook_server_status()
    else:
        data = list_webhooks()
    if json_out:
        _json_print(data)
    else:
        if action == 'add' and data.get('ok'):
            hook = data.get('webhook') or {}
            _cli_line('Webhook job created', kind='ok')
            print(f"Name             : {hook.get('name')}")
            print(f"Event            : {hook.get('event')}")
            print(f"Token            : {hook.get('token')}")
        elif action == 'receive' and data.get('ok'):
            _cli_line(f"Webhook accepted, queued {data.get('matched', 0)} job(s)", kind='ok')
        elif action == 'serve' and data.get('ok'):
            _cli_line(f"Webhook server stopped: {data.get('url')}", kind='ok')
        elif action == 'status' and data.get('ok'):
            _cli_line('Webhook server status', kind='ok')
            print('Status          : ' + json.dumps(data, ensure_ascii=False))
        else:
            _cli_line(f"Webhooks: {data.get('count', 0)}", kind='ok')
            for item in data.get('items') or []:
                print(f"- {item['name']} event={item['event']} token={item['token']}")
    return 0 if data.get('ok') else 1

def _cmd_agent_queue(action: str, *, limit: int | None = None, item_id: str | None = None, workers: int = 1, json_out: bool = False) -> int:
    if action == 'run':
        data = drain_queue(limit=limit, callback=_scheduled_job_callback, workers=workers)
    elif action == 'stats':
        data = queue_stats()
    elif action == 'dead-letter':
        data = list_dead_letter()
    elif action == 'retry':
        data = retry_queue_item(str(item_id))
    elif action == 'log':
        data = read_queue_log(limit=limit or 50)
    else:
        data = list_queue()
    if json_out:
        _json_print(data)
    else:
        if action == 'run' and data.get('ok'):
            _cli_line(f"Processed {data.get('count', 0)} queued job(s)", kind='ok')
        elif action == 'stats' and data.get('ok'):
            _cli_line('Queue stats', kind='ok')
            print('Status          : ' + json.dumps(data, ensure_ascii=False))
        elif action == 'dead-letter' and data.get('ok'):
            _cli_line(f"Dead-letter items: {data.get('count', 0)}", kind='ok')
            for item in data.get('items') or []:
                print(f"- {item['id']} name={item.get('name')} error={item.get('last_error')}")
        elif action == 'retry' and data.get('ok'):
            _cli_line(f"Requeued dead-letter item {data.get('item', {}).get('id')}", kind='ok')
        elif action == 'log' and data.get('ok'):
            _cli_line(f"Queue log entries: {data.get('count', 0)}", kind='ok')
            for item in data.get('items') or []:
                print(json.dumps(item, ensure_ascii=False))
        else:
            _cli_line(f"Queue items: {data.get('count', 0)} (queued={data.get('queued', 0)}, done={data.get('done', 0)}, retry={data.get('retry', 0)}, dead-letter={data.get('dead_letter', 0)})", kind='ok')
            for item in data.get('items') or []:
                print(f"- {item['name']} status={item['status']} source={item.get('source')} event={item.get('event')}")
    return 0 if data.get('ok') else 1

def _cmd_agent_jobs(action: str, *, task: str | None = None, name: str | None = None, kind: str = 'run', package: str | None = None, model: str = 'rule-based', memory: str = '.mellow/agent_memory.jsonl', obs: str = '.mellow/agent_observability.jsonl', rag_file: str | None = None, retries: int = 1, timeout_ms: int | None = None, parallel: bool = False, sandbox: bool = False, allow_caps: list[str] | None = None, secrets: list[str] | None = None, payload: str | None = None, host: str = '127.0.0.1', port: int = 8788, job_id: str | None = None, backoff: dict[str, Any] | None = None, json_out: bool = False) -> int:
    if action == 'submit':
        data = submit_job(str(task), name=name, kind=kind, package=package, model=model, memory=memory, obs=obs, rag_file=rag_file, retries=retries, timeout_ms=timeout_ms, parallel=parallel, sandbox=sandbox, allow_caps=allow_caps, secrets=secrets, backoff=backoff, payload=_parse_jsonish(payload))
    elif action == 'get':
        data = get_queue_item(str(job_id))
    elif action == 'serve':
        data = start_webhook_server(host=host, port=port, enable_job_api=True)
    elif action == 'status':
        data = read_job_api_status()
    else:
        data = list_queue()
    if json_out:
        _json_print(data)
    else:
        if action == 'submit' and data.get('ok'):
            item = data.get('item') or {}
            _cli_line(f"Job submitted: {item.get('id')}", kind='ok')
            print('Status          : ' + json.dumps(item, ensure_ascii=False))
        elif action == 'get' and data.get('ok'):
            _cli_line(f"Job {job_id}", kind='ok')
            print('Status          : ' + json.dumps(data.get('item'), ensure_ascii=False))
        elif action == 'serve' and data.get('ok'):
            _cli_line(f"Job API server stopped: {data.get('url')}", kind='ok')
        elif action == 'status' and data.get('ok'):
            _cli_line('Job API server status', kind='ok')
            print('Status          : ' + json.dumps(data, ensure_ascii=False))
        else:
            _cli_line(f"Jobs in queue: {data.get('count', 0)}", kind='ok')
            for item in data.get('items') or []:
                print(f"- {item.get('id')} name={item.get('name')} status={item.get('status')}")
    return 0 if data.get('ok') else 1

def _cmd_agent_runner(action: str, *, interval_s: float = 1.0, iterations: int = 1, queue_backed: bool = False, queue_limit: int | None = None, workers: int = 1, json_out: bool = False) -> int:
    payload = run_background_runner(interval_s=interval_s, iterations=iterations, callback=_scheduled_job_callback, queue_backed=queue_backed, queue_limit=queue_limit, workers=workers) if action == 'start' else read_runner_status()
    if json_out:
        _json_print(payload)
    else:
        if action == 'start' and payload.get('ok'):
            _cli_line('Background agent runner finished', kind='ok')
            print('Status          : ' + json.dumps(payload, ensure_ascii=False))
        else:
            _cli_line('Background agent runner status', kind='ok')
            print('Status          : ' + json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get('ok', True) else 1
