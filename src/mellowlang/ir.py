from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class IRInstruction:
    op: str
    args: tuple[Any, ...] = ()
    line: int = 0
    col: int = 1


@dataclass(frozen=True)
class IRFunction:
    name: str
    entry_label: str
    params: List[str] = field(default_factory=list)
    kind: str = "skill"


@dataclass(frozen=True)
class IRProgram:
    instructions: List[IRInstruction]
    functions: Dict[str, IRFunction] = field(default_factory=dict)
    events: Dict[str, IRFunction] = field(default_factory=dict)
    filename: Optional[str] = None
