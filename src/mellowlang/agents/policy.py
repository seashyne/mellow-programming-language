from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Set

from .sandbox import SandboxConfig


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str


@dataclass
class CapabilityPolicy:
    allow: Set[str] = field(default_factory=set)
    deny: Set[str] = field(default_factory=set)
    allowed_tools: Set[str] = field(default_factory=set)
    denied_tools: Set[str] = field(default_factory=set)
    signed_by: str | None = None
    signature: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            'capabilities': {
                'allow': sorted(self.allow),
                'deny': sorted(self.deny),
            },
            'tools': {
                'allow': sorted(self.allowed_tools),
                'deny': sorted(self.denied_tools),
            },
        }
        if self.signed_by:
            data['signed_by'] = self.signed_by
        if self.signature:
            data['signature'] = self.signature
        return data


def _canonical_policy_dict(data: Dict[str, Any]) -> bytes:
    base = dict(data)
    base.pop('signature', None)
    return json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def sign_capability_policy(policy: Dict[str, Any] | CapabilityPolicy, signing_key: str, *, signer: str | None = None) -> Dict[str, Any]:
    payload = policy.to_dict() if isinstance(policy, CapabilityPolicy) else dict(policy)
    payload.pop('signature', None)
    if signer:
        payload['signed_by'] = signer
    payload['signature'] = hashlib.sha256(signing_key.encode('utf-8') + b'|' + _canonical_policy_dict(payload)).hexdigest()
    return payload


def verify_capability_policy(policy: Dict[str, Any], signing_key: str) -> bool:
    sig = str(policy.get('signature') or '')
    if not sig or not signing_key:
        return False
    expected = hashlib.sha256(signing_key.encode('utf-8') + b'|' + _canonical_policy_dict(policy)).hexdigest()
    return expected == sig


def load_signed_policy(path: str | Path, verify_key: str | None = None) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if verify_key and not verify_capability_policy(data, verify_key):
        raise PermissionError(f'capability policy signature verification failed: {path}')
    return data


class PolicyEngine:
    def __init__(
        self,
        *,
        allowed_tools: Iterable[str] | None = None,
        denied_tools: Iterable[str] | None = None,
        allowed_capabilities: Iterable[str] | None = None,
        denied_capabilities: Iterable[str] | None = None,
        sandbox: SandboxConfig | None = None,
        signed_policy: Dict[str, Any] | None = None,
        default_deny_tools: bool = True,
    ):
        self.allowed_tools: Set[str] = set(allowed_tools or [])
        self.denied_tools: Set[str] = set(denied_tools or [])
        self.allowed_capabilities: Set[str] = set(allowed_capabilities or [])
        self.denied_capabilities: Set[str] = set(denied_capabilities or [])
        self.sandbox = sandbox or SandboxConfig()
        self.signed_policy: Dict[str, Any] | None = None
        self.default_deny_tools = bool(default_deny_tools)
        if signed_policy:
            self.apply_signed_policy(signed_policy)

    def apply_signed_policy(self, signed_policy: Dict[str, Any]) -> None:
        self.signed_policy = dict(signed_policy)
        caps = signed_policy.get('capabilities') or {}
        tools = signed_policy.get('tools') or {}
        self.allowed_capabilities.update(str(x) for x in (caps.get('allow') or []))
        self.denied_capabilities.update(str(x) for x in (caps.get('deny') or []))
        self.allowed_tools.update(str(x) for x in (tools.get('allow') or []))
        self.denied_tools.update(str(x) for x in (tools.get('deny') or []))

    def check_capability(self, capability: str) -> PolicyDecision:
        if capability in self.denied_capabilities:
            return PolicyDecision(False, f'capability `{capability}` denied by policy')
        if self.allowed_capabilities and capability not in self.allowed_capabilities:
            return PolicyDecision(False, f'capability `{capability}` not in allow-list')
        if self.sandbox.enabled:
            if capability.startswith('tools.') and not self.allowed_capabilities:
                return PolicyDecision(False, f'capability `{capability}` not in allow-list')
            if capability.startswith('network.') and not self.sandbox.network:
                return PolicyDecision(False, 'network access denied by sandbox')
            if capability == 'memory.read' and not self.sandbox.memory:
                return PolicyDecision(False, 'memory access denied by sandbox')
            if capability == 'filesystem.read' and self.sandbox.filesystem not in {'read-only', 'read-write'}:
                return PolicyDecision(False, 'filesystem read denied by sandbox')
            if capability == 'filesystem.write' and self.sandbox.filesystem != 'read-write':
                return PolicyDecision(False, 'filesystem write denied by sandbox')
        return PolicyDecision(True, 'allowed')

    def check_tool(self, tool_name: str, capabilities: Iterable[str] | None = None) -> PolicyDecision:
        if tool_name in self.denied_tools:
            return PolicyDecision(False, f'tool `{tool_name}` denied by policy')
        if self.allowed_tools and tool_name not in self.allowed_tools:
            return PolicyDecision(False, f'tool `{tool_name}` not in allow-list')
        if self.default_deny_tools and not self.allowed_tools:
            return PolicyDecision(False, f'tool `{tool_name}` denied by default; add it to the allow-list')
        for capability in list(capabilities or []):
            decision = self.check_capability(capability)
            if not decision.allowed:
                return decision
        return PolicyDecision(True, 'allowed')

    def check_secret(self, secret_name: str) -> PolicyDecision:
        if self.sandbox.enabled and self.sandbox.allowed_secrets and secret_name not in self.sandbox.allowed_secrets:
            return PolicyDecision(False, f'secret `{secret_name}` denied by sandbox')
        return PolicyDecision(True, 'allowed')
