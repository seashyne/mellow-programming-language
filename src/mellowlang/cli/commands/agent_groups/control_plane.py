"""The hosted control plane - register, status, revisions, health, traffic, rollback, metrics and alerts - plus the capability policy sign/verify pair."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sys

from ...common import _cli_line, _json_print
from .deps import (
    load_signed_policy, load_deployment_manifest, sign_capability_policy, register_deployment,
    list_deployments, get_deployment_status, sync_deployment, list_revisions,
    rollout_revision, run_health_check, update_traffic_split, rollback_deployment,
    record_deployment_metrics, get_deployment_metrics, get_autoscaling_signals, set_alert_rules,
    evaluate_alerts,
)

def _cmd_agent_control_plane(action: str, ref: str | None, manifest: str | None, bundle_dir: str, control_plane: str | None, json_out: bool, token: str | None = None, revision: int | None = None, revision_notes: str | None = None, canary_percent: int | None = None, stable_percent: int | None = None, canary_split: int | None = None, rules_file: str | None = None, metrics: dict[str, Any] | None = None) -> int:
    if action == 'register' and manifest:
        payload = register_deployment(load_deployment_manifest(manifest), bundle_dir, control_plane=control_plane, manifest_path=manifest, revision_notes=revision_notes)
    elif action == 'sync' and manifest:
        payload = sync_deployment(load_deployment_manifest(manifest), bundle_dir, control_plane=control_plane, api_token=token, manifest_path=manifest, revision_notes=revision_notes)
    elif action == 'status' and ref:
        payload = get_deployment_status(ref, control_plane=control_plane, api_token=token)
    elif action == 'revisions' and ref:
        payload = list_revisions(ref, control_plane=control_plane, api_token=token)
    elif action == 'rollout' and ref and revision is not None:
        payload = rollout_revision(ref, revision, control_plane=control_plane, api_token=token, canary_percent=canary_percent)
    elif action == 'health' and ref:
        payload = run_health_check(ref, control_plane=control_plane, api_token=token)
    elif action == 'traffic' and ref and stable_percent is not None and canary_split is not None:
        payload = update_traffic_split(ref, stable_percent, canary_split, control_plane=control_plane, api_token=token)
    elif action == 'rollback' and ref:
        payload = rollback_deployment(ref, control_plane=control_plane, api_token=token, revision=revision)
    elif action == 'metrics' and ref:
        clean_metrics = {k: v for k, v in (metrics or {}).items() if v is not None}
        payload = record_deployment_metrics(ref, clean_metrics, control_plane=control_plane, api_token=token) if clean_metrics else get_deployment_metrics(ref, control_plane=control_plane, api_token=token)
    elif action == 'signals' and ref:
        payload = get_autoscaling_signals(ref, control_plane=control_plane, api_token=token)
    elif action == 'alert-rules' and ref:
        if rules_file:
            raw = json.loads(Path(rules_file).read_text(encoding='utf-8'))
            rules = raw.get('rules') if isinstance(raw, dict) else raw
            payload = set_alert_rules(ref, list(rules or []), control_plane=control_plane, api_token=token)
        else:
            status = get_deployment_status(ref, control_plane=control_plane, api_token=token)
            if status.get('ok'):
                dep = status['deployment']
                payload = {'ok': True, 'deployment': dep, 'rules': list(dep.get('alert_rules') or []), 'alerts': dep.get('alerts') or {'status': 'ok', 'count': 0}}
            else:
                payload = status
    elif action == 'alerts' and ref:
        payload = evaluate_alerts(ref, control_plane=control_plane, api_token=token)
    else:
        payload = list_deployments(control_plane=control_plane, api_token=token)
    if json_out:
        _json_print(payload)
    else:
        if action == 'status' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Hosted deployment: {dep['id']}", kind='ok')
            print(f"Package         : {dep['package']['name']}@{dep['package']['version']}")
            print(f"Provider        : {dep['provider']}")
            print(f"Status          : {dep['status']}")
            print(f"Current rev     : {dep.get('current_revision')}")
            print(f"Latest rev      : {dep.get('latest_revision')}")
            if dep.get('traffic_split'):
                print(f"Traffic split   : {json.dumps(dep.get('traffic_split'), ensure_ascii=False)}")
            if dep.get('health'):
                print(f"Health          : {json.dumps(dep.get('health'), ensure_ascii=False)}")
            print(f"Bundle dir      : {dep['bundle_dir']}")
        elif action == 'revisions' and payload.get('ok'):
            _cli_line(f"Revisions: {payload.get('count', 0)}", kind='ok')
            if payload.get('traffic_split'):
                print('Traffic split   : ' + json.dumps(payload.get('traffic_split'), ensure_ascii=False))
            for item in payload.get('items') or []:
                marker = '*' if int(item.get('revision', 0)) == int(payload.get('current_revision') or 0) else ' '
                print(f"{marker} rev {item['revision']} :: status={item.get('status')} created={item.get('created_at')} notes={item.get('notes') or ''}")
        elif action == 'health' and payload.get('ok'):
            _cli_line(f"Health check ok for {payload['deployment']['package']['name']}", kind='ok')
            print('Health          : ' + json.dumps(payload.get('health'), ensure_ascii=False))
        elif action == 'traffic' and payload.get('ok'):
            _cli_line(f"Traffic updated for {payload['deployment']['package']['name']}", kind='ok')
            print('Traffic split   : ' + json.dumps(payload.get('traffic_split'), ensure_ascii=False))
        elif action == 'rollout' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Rolled out revision {payload['revision']['revision']} for {dep['package']['name']}", kind='ok')
            print(f"Deployment ID   : {dep['id']}")
            print(f"Current rev     : {dep.get('current_revision')}")
            print(f"Status          : {dep.get('status')}")
            if dep.get('traffic_split'):
                print('Traffic split   : ' + json.dumps(dep.get('traffic_split'), ensure_ascii=False))
        elif action == 'rollback' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Rolled back deployment {dep['package']['name']}", kind='ok')
            print(f"Deployment ID   : {dep['id']}")
            print(f"Current rev     : {dep.get('current_revision')}")
            print(f"Status          : {dep.get('status')}")
        elif action == 'metrics' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Metrics for {dep['package']['name']}", kind='ok')
            print('Metrics         : ' + json.dumps(payload.get('metrics'), ensure_ascii=False))
            if payload.get('autoscaling'):
                print('Autoscaling     : ' + json.dumps(payload.get('autoscaling'), ensure_ascii=False))
            if payload.get('alerts'):
                print('Alerts          : ' + json.dumps(payload.get('alerts'), ensure_ascii=False))
        elif action == 'signals' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Autoscaling signals for {dep['package']['name']}", kind='ok')
            print('Signals         : ' + json.dumps(payload.get('autoscaling'), ensure_ascii=False))
        elif action == 'alert-rules' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Alert rules for {dep['package']['name']}", kind='ok')
            print('Rules           : ' + json.dumps(payload.get('rules') or [], ensure_ascii=False))
            print('Alerts          : ' + json.dumps(payload.get('alerts') or {'status': 'ok', 'count': 0}, ensure_ascii=False))
        elif action == 'alerts' and payload.get('ok'):
            dep = payload['deployment']
            _cli_line(f"Alert evaluation for {dep['package']['name']}", kind='ok')
            print('Alerts          : ' + json.dumps(payload.get('alerts'), ensure_ascii=False))
            if payload.get('rules') is not None:
                print('Rules           : ' + json.dumps(payload.get('rules'), ensure_ascii=False))
        elif action in ('status','revisions','rollout','health','traffic','rollback','metrics','signals','alert-rules','alerts'):
            _cli_line(payload.get('error', f'{action} failed'), kind='error', file=sys.stderr)
        else:
            items = payload.get('items') or ([payload.get('deployment')] if payload.get('deployment') else [])
            _cli_line(f"Hosted deployments: {len(items)}", kind='ok')
            for item in items:
                print(f"- {item['id']} :: {item['package']['name']}@{item['package']['version']} [{item['provider']}] status={item['status']} current_rev={item.get('current_revision')}")
    return 0 if payload.get('ok') else 1

def _cmd_agent_policy_sign(path: str, key: str, signer: str | None, json_out: bool) -> int:
    p = Path(path)
    payload = sign_capability_policy(json.loads(p.read_text(encoding='utf-8')), key, signer=signer)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
    res = {'ok': True, 'path': str(p), 'signed_by': signer}
    if json_out:
        _json_print(res)
    else:
        _cli_line(f'Capability policy signed: {p}', kind='ok')
    return 0

def _cmd_agent_policy_verify(path: str, key: str, json_out: bool) -> int:
    try:
        payload = load_signed_policy(path, verify_key=key)
        res = {'ok': True, 'path': str(path), 'signed_by': payload.get('signed_by')}
    except Exception as e:
        res = {'ok': False, 'path': str(path), 'error': str(e)}
    if json_out:
        _json_print(res)
    else:
        if res.get('ok'):
            _cli_line(f'Capability policy verified: {path}', kind='ok')
        else:
            _cli_line(f"Capability policy verify failed: {res.get('error')}", kind='error', file=sys.stderr)
    return 0 if res.get('ok') else 1
