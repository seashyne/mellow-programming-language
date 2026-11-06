"""Behaviour-tree and finite-state-machine ticks plus the emit() entry point."""

from __future__ import annotations

from typing import Any


class EventMixin:
    # ---------------- AI helpers (v1.2.0) ----------------
    def _bt_tick(self, node: Any, ctx: Any) -> str:
        """Behavior Tree tick.

        Node representation (dict):
          {"type": "selector"|"sequence"|"condition"|"action", ...}
        Condition/action nodes call host syscalls:
          {"type":"condition","sys":"game.sees_player","args":[...]}
          {"type":"action","sys":"game.move_to","args":[...]}

        Return status: "success"|"fail"|"running"
        """
        if node is None:
            return "fail"
        if not isinstance(node, dict):
            self._raise_runtime("bt_tick expects node map")
        t = str(node.get("type", ""))
        if t == "selector":
            children = node.get("children", [])
            if not isinstance(children, list):
                children = []
            for ch in children:
                st = self._bt_tick(ch, ctx)
                if st in ("success", "running"):
                    return st
            return "fail"
        if t == "sequence":
            children = node.get("children", [])
            if not isinstance(children, list):
                children = []
            for ch in children:
                st = self._bt_tick(ch, ctx)
                if st in ("fail", "running"):
                    return st
            return "success"
        if t == "condition":
            sysname = str(node.get("sys", ""))
            a = node.get("args", [])
            if not isinstance(a, list):
                a = [a]
            ok = self._syscall(sysname, a)
            return "success" if self._truthy(ok) else "fail"
        if t == "action":
            sysname = str(node.get("sys", ""))
            a = node.get("args", [])
            if not isinstance(a, list):
                a = [a]
            res = self._syscall(sysname, a)
            # allow host to return status string; otherwise treat truthy => success
            if isinstance(res, str) and res in ("success", "fail", "running"):
                return res
            return "success" if self._truthy(res) else "fail"
        return "fail"

    def _fsm_tick(self, fsm: Any, ctx: Any) -> Any:
        """Tiny FSM helper.

        fsm map:
          {"state":"idle", "on_tick": {"idle":"game.idle_tick", ...}}
        tick calls the current state's on_tick syscall, if present.
        """
        if fsm is None:
            self._raise_runtime("fsm_tick expects fsm map")
        if not isinstance(fsm, dict):
            self._raise_runtime("fsm_tick expects fsm map")
        state = str(fsm.get("state", ""))
        table = fsm.get("on_tick", {})
        if isinstance(table, dict) and state in table:
            sysname = str(table.get(state))
            if sysname:
                return self._syscall(sysname, [ctx] if ctx is not None else [])
        return None

    # ---------------- Events ----------------
    def emit(self, event_name: str, args: list | None = None):
        """Trigger an event handler registered via on("event"):. Returns handler return value."""
        args = args or []
        if event_name not in self.event_table:
            return None
        meta = self.event_table[event_name]
        self._replay.record_emit(event_name, args)

        # Push args onto stack
        pcount = int(meta.get("param_count", 0))
        for a in args:
            self.stack.append(a)
        for _ in range(pcount - len(args)):
            self.stack.append(None)

        # Set up call frame â€” use len(bytecode) as sentinel return address
        # When RETURN pops this address, pc will be out-of-range â†’ run() exits
        sentinel_pc = len(self.bytecode)
        self.call_stack.append(sentinel_pc)
        self.frame_stack.append({
            "name": f"event:{event_name}",
            "filename": self.filename,
            "line": None, "col": None
        })
        self.variables.append({})

        saved_pc = self.pc
        self.pc = int(meta["address"])
        self.run()  # runs until RETURN pops sentinel_pc â†’ pc = sentinel_pc â†’ loop exits

        result = self.stack.pop() if self.stack else None
        self.pc = saved_pc
        return result
