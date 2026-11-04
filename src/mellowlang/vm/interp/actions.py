"""The four actions an opcode family or a builtin group can hand back.

_PASS  this instruction / this builtin name is not mine
_STEP  handled, advance the program counter
_NEXT  handled, it already moved the counter (the original `continue`)
_HALT  stop the loop (the original `break`)
"""

from __future__ import annotations


class Action:
    """A dispatch action; identity, not value, is what the driver compares."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"<Action {self.name}>"


_PASS = Action("pass")
_STEP = Action("step")
_NEXT = Action("next")
_HALT = Action("halt")
