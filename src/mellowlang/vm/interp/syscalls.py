"""The host syscall bridge: budget, argument check, dispatch, result push."""

from __future__ import annotations

import sqlite3
from ...data_core import DataCoreError


class SyscallMixin:
    # ---------------- Syscall ----------------
    def _syscall(self, name: str, args: list):
        if not isinstance(name, str):
            self._raise_sandbox("syscall name must be string")

        if name in ("std.io.println", "std.print"):
            print(" ".join(self.format_value(arg) for arg in args))
            return None

        if name == "std.io.write":
            import sys as _sys
            _sys.stdout.write(" ".join(self.format_value(arg) for arg in args))
            _sys.stdout.flush()
            return None

        if name == "std.io.input":
            if not self.config.get("allow_ask", False):
                self._raise_sandbox("input() is disabled")
            prompt = "" if not args else self.format_value(args[0])
            raw = input(prompt)
            self._enforce_value_limits(raw)
            return raw

        if name == "std.sys.args":
            return list(self.config.get("argv", []))

        if name == "std.sys.cwd":
            import os as _os
            return _os.getcwd()

        if name == "std.sys.sleep_ms":
            if not self.config.get("allow_wait", True):
                self._raise_sandbox("sleep_ms() is disabled")
            import time as _time
            _time.sleep(float(args[0]) / 1000.0 if args else 0.0)
            return None

        if name == "std.sys.exit":
            code = int(args[0]) if args else 0
            raise SystemExit(code)

        if name == "std.gc.collect":
            if args:
                self._raise_runtime("gc_collect expects no arguments")
            self._native_foundation_stats["collections"] += 1
            return 0

        if name == "std.gc.stats":
            if args:
                self._raise_runtime("gc_stats expects no arguments")
            stats = dict(self._native_foundation_stats)
            stats["mode"] = "python-nonrelease-runtime"
            return stats

        if name == "std.thread.spawn":
            if len(args) != 1:
                self._raise_runtime("spawn expects one function argument")
            self._native_foundation_stats["spawned"] += 1
            return self._native_foundation_stats["spawned"]

        if name == "std.thread.yield":
            if args:
                self._raise_runtime("yield expects no arguments")
            self._native_foundation_stats["yielded"] += 1
            return None

        if name == "std.chan.channel":
            if args:
                self._raise_runtime("channel expects no arguments")
            self._native_foundation_stats["channels"] += 1
            return {"type": "channel", "queue": []}

        if name == "std.chan.send":
            if len(args) != 2 or not isinstance(args[0], dict) or args[0].get("type") != "channel":
                self._raise_runtime("send expects channel and value")
            args[0].setdefault("queue", []).append(args[1])
            return True

        if name == "std.chan.recv":
            if len(args) != 1 or not isinstance(args[0], dict) or args[0].get("type") != "channel":
                self._raise_runtime("recv expects channel")
            queue = args[0].setdefault("queue", [])
            if not queue:
                self._native_foundation_stats["yielded"] += 1
                return None
            return queue.pop(0)

        if name.startswith("std.data."):
            try:
                if name == "std.data.open_jsonl":
                    return self._data.open_jsonl(args[0], args[1] if len(args) > 1 else 100)
                if name == "std.data.open_csv":
                    return self._data.open_csv(args[0], args[1] if len(args) > 1 else 100)
                if name == "std.data.next":
                    return self._data.next_batch(args[0])
                if name == "std.data.close":
                    return self._data.close(args[0])
                if name == "std.data.cancel":
                    return self._data.cancel(args[0])
                if name == "std.data.info":
                    return self._data.stream_info(args[0])
                if name == "std.data.project":
                    return self._data.project(args[0], args[1])
                if name == "std.data.where":
                    return self._data.where(args[0], args[1], args[2], args[3])
                if name == "std.data.sum":
                    return self._data.sum_field(args[0], args[1])
                if name == "std.data.sqlite_query":
                    return self._data.sqlite_query(
                        args[0],
                        args[1],
                        args[2] if len(args) > 2 else [],
                        args[3] if len(args) > 3 else None,
                    )
                if name == "std.data.sqlite_execute":
                    return self._data.sqlite_execute(args[0], args[1], args[2] if len(args) > 2 else [])
                if name == "std.data.sqlite_open":
                    return self._data.sqlite_open(args[0] if args else ":memory:", args[1] if len(args) > 1 else False)
                if name == "std.data.sqlite_close":
                    return self._data.sqlite_close(args[0])
                self._raise_sandbox(f"syscall not allowed: {name}")
            except (DataCoreError, OSError, ValueError, sqlite3.Error) as exc:
                self._raise_runtime(str(exc))

        # --- v1.4.7: emit() â€” fire event to on-handler ---
        if name == "std.event.emit":
            event_name = str(args[0]) if len(args) >= 1 else ""
            event_args = list(args[1]) if len(args) >= 2 and isinstance(args[1], list) else args[1:]
            return self.emit(event_name, event_args)

        # --- Built-in AI helpers (v1.2.0) ---
        if name in ("std.ai.decide", "ai.decide"):
            label = str(args[0]) if len(args) >= 1 else ""
            reason = str(args[1]) if len(args) >= 2 else ""
            if self._ai_trace:
                line, col = self._pos()
                self._ai_events.append({
                    "t": int(self._steps),
                    "line": int(line) if line else None,
                    "col": int(col) if col else None,
                    "label": label,
                    "reason": reason,
                })
            return label

        if name == "std.ai.utility_choose":
            # args: list of {"score": number, "value": any}
            opts = args[0] if args else []
            if not isinstance(opts, list):
                self._raise_runtime("utility_choose expects list")
            best = None
            best_score = None
            for it in opts:
                if not isinstance(it, dict):
                    continue
                sc = it.get("score", 0)
                try:
                    scf = float(sc)
                except Exception:
                    scf = 0.0
                if best is None or scf > float(best_score):
                    best = it
                    best_score = scf
            return None if best is None else best.get("value")

        if name == "std.ai.bt_tick":
            tree = args[0] if len(args) >= 1 else None
            ctx = args[1] if len(args) >= 2 else {}
            return self._bt_tick(tree, ctx)

        if name == "std.ai.fsm_tick":
            fsm = args[0] if len(args) >= 1 else None
            ctx = args[1] if len(args) >= 2 else {}
            return self._fsm_tick(fsm, ctx)
        if not self.host.has(name):
            self._raise_sandbox(f"syscall not allowed: {name}")

        cost = int(self.host.get_cost(name))
        self._budget -= cost
        if self._budget < 0:
            self._raise_sandbox("syscall budget exceeded")

        # Replay mode: return recorded result without calling host
        if self._replay.cfg.mode == "replay":
            res = self._replay.next_syscall_result(name, args)
            self._enforce_value_limits(res)
            return res

        res = self.host.call(name, args)
        self._enforce_value_limits(res)
        self._replay.record_syscall(name, args, res)
        return res
