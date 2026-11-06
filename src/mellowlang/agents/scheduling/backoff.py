"""Retry backoff settings, normalised once and turned into a delay per attempt."""

from __future__ import annotations

import math
import random
from typing import Any, Dict


def _normalize_backoff(backoff: Dict[str, Any] | None = None) -> Dict[str, Any]:
    raw = dict(backoff or {})
    strategy = str(raw.get('strategy') or 'fixed').lower()
    if strategy not in {'fixed', 'exponential', 'jitter'}:
        strategy = 'fixed'
    initial = max(0, int(raw.get('initial_delay_ms') or 0))
    max_delay = max(initial, int(raw.get('max_delay_ms') or initial or 0))
    jitter_pct = max(0.0, min(1.0, float(raw.get('jitter_pct') or 0.15)))
    return {
        'strategy': strategy,
        'initial_delay_ms': initial,
        'max_delay_ms': max_delay,
        'jitter_pct': jitter_pct,
    }


def _compute_backoff_delay_ms(backoff: Dict[str, Any], attempt: int) -> int:
    policy = _normalize_backoff(backoff)
    base = int(policy.get('initial_delay_ms') or 0)
    if base <= 0:
        return 0
    strategy = str(policy.get('strategy') or 'fixed')
    if strategy == 'fixed':
        delay = base
    else:
        exp = max(0, int(attempt) - 1)
        delay = base * int(math.pow(2, exp))
        delay = min(delay, int(policy.get('max_delay_ms') or delay))
        if strategy == 'jitter':
            jitter_pct = float(policy.get('jitter_pct') or 0.15)
            low = max(0, int(delay * (1.0 - jitter_pct)))
            high = max(low, int(delay * (1.0 + jitter_pct)))
            delay = random.randint(low, high)
    return int(delay)
