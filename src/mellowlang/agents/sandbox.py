from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Set


@dataclass
class SandboxConfig:
    enabled: bool = False
    network: bool = False
    filesystem: str = 'none'  # none | read-only | read-write
    memory: bool = True
    allowed_secrets: Set[str] = field(default_factory=set)

    @classmethod
    def from_flags(
        cls,
        *,
        enabled: bool = False,
        network: bool = False,
        filesystem: str = 'none',
        memory: bool = True,
        allowed_secrets: Iterable[str] | None = None,
    ) -> 'SandboxConfig':
        fs = str(filesystem or 'none').strip().lower()
        if fs not in {'none', 'read-only', 'read-write'}:
            fs = 'none'
        return cls(
            enabled=bool(enabled),
            network=bool(network),
            filesystem=fs,
            memory=bool(memory),
            allowed_secrets=set(allowed_secrets or []),
        )
