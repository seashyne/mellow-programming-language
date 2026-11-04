"""Traffic-split normalisation, per-revision status and the local
deployment lookup."""

from __future__ import annotations

from typing import Any, Dict


def _normalize_split(split: Dict[str, Any] | None) -> Dict[str, int]:
    raw = dict(split or {})
    stable = int(raw.get('stable', 100) or 0)
    canary = int(raw.get('canary', 0) or 0)
    if stable < 0:
        stable = 0
    if canary < 0:
        canary = 0
    total = stable + canary
    if total <= 0:
        return {'stable': 100, 'canary': 0}
    if total != 100:
        stable = round((stable / total) * 100)
        canary = 100 - stable
    return {'stable': int(stable), 'canary': int(canary)}


def _rev_status_for(item: Dict[str, Any], rev_no: int) -> str:
    current = int(item.get('current_revision') or 0)
    canary = item.get('canary') or {}
    canary_rev = int(canary.get('revision') or 0) if canary else 0
    split = _normalize_split(canary.get('traffic_split')) if canary else {'stable': 100, 'canary': 0}
    if canary_rev == rev_no and split.get('canary', 0) > 0:
        return 'canary'
    if current == rev_no:
        return 'active'
    return 'synced'


def _find_local_target(state: Dict[str, Any], ref: str) -> Dict[str, Any] | None:
    deployments = state.get('deployments') or {}
    for dep_id, item in deployments.items():
        if dep_id == ref or item.get('package', {}).get('name') == ref:
            return item
    return None
