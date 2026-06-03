# frinds/replay.py (v3)
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

@dataclass
class ReplayConfig:
    mode: str = "off"   # 'off' | 'record' | 'replay'
    path: Optional[str] = None

class ReplayLog:
    """Deterministic replay log (JSONL).
    Records:
      - seed
      - syscalls (name, args, result)
      - random results
      - event emits (event, args)
    In replay mode, syscalls/random will return logged results.
    """
    def __init__(self, cfg: ReplayConfig):
        self.cfg = cfg
        self._fh = None
        self._events: List[Dict[str, Any]] = []
        self._i = 0

        if cfg.mode == "record":
            if not cfg.path:
                raise ValueError("ReplayLog(record) requires path")
            self._fh = open(cfg.path, "w", encoding="utf-8")
        elif cfg.mode == "replay":
            if not cfg.path:
                raise ValueError("ReplayLog(replay) requires path")
            with open(cfg.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._events.append(json.loads(line))

    def close(self):
        if self._fh:
            self._fh.close()
            self._fh = None

    def _write(self, obj: Dict[str, Any]):
        if self._fh:
            self._fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self._fh.flush()

    def record_seed(self, seed: int):
        if self.cfg.mode == "record":
            self._write({"type": "seed", "seed": int(seed)})

    def record_syscall(self, name: str, args: List[Any], result: Any):
        if self.cfg.mode == "record":
            self._write({"type": "syscall", "name": name, "args": args, "result": result})

    def record_random(self, low: int, high: int, result: int):
        if self.cfg.mode == "record":
            self._write({"type": "random", "low": int(low), "high": int(high), "result": int(result)})

    def record_randfloat(self, result: float):
        if self.cfg.mode == "record":
            self._write({"type": "randfloat", "result": float(result)})

    def record_emit(self, event: str, args: List[Any]):
        if self.cfg.mode == "record":
            self._write({"type": "emit", "event": event, "args": args})

    def _next(self) -> Dict[str, Any]:
        if self._i >= len(self._events):
            raise RuntimeError("REPLAY: log exhausted")
        ev = self._events[self._i]
        self._i += 1
        return ev

    def next_seed(self) -> int:
        ev = self._next()
        if ev.get("type") != "seed":
            raise RuntimeError(f"REPLAY: expected seed, got {ev.get('type')}")
        return int(ev.get("seed", 0))

    def next_syscall_result(self, name: str, args: List[Any]) -> Any:
        ev = self._next()
        if ev.get("type") != "syscall":
            raise RuntimeError(f"REPLAY: expected syscall, got {ev.get('type')}")
        if ev.get("name") != name:
            raise RuntimeError(f"REPLAY: syscall name mismatch: {ev.get('name')} != {name}")
        # Args mismatch could happen due to benign formatting; keep strict by default
        if ev.get("args") != args:
            raise RuntimeError(f"REPLAY: syscall args mismatch for {name}")
        return ev.get("result")

    def next_random_result(self, low: int, high: int) -> int:
        ev = self._next()
        if ev.get("type") != "random":
            raise RuntimeError(f"REPLAY: expected random, got {ev.get('type')}")
        if int(ev.get("low")) != int(low) or int(ev.get("high")) != int(high):
            raise RuntimeError("REPLAY: random range mismatch")
        return int(ev.get("result"))

    def next_randfloat(self) -> float:
        ev = self._next()
        if ev.get("type") != "randfloat":
            raise RuntimeError(f"REPLAY: expected randfloat, got {ev.get('type')}")
        return float(ev.get("result"))
