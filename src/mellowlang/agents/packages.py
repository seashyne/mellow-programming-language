from __future__ import annotations

from pathlib import Path

SAMPLE_AGENT_TOML = """[package]
name = "demo.agent"
version = "0.1.0"

[agent]
model = "rule-based"
prompt_file = "prompts/default.prompt"
tool_manifest = "tools/manifest.toml"
policy_file = "policies/capabilities.json"
memory_path = ".mellow/agent_memory.jsonl"
obs_path = ".mellow/agent_observability.jsonl"
tags = ["demo", "hosted"]

[capabilities]
allow = ["tools.search.docs", "tools.time.now"]
deny = []

[secrets]
required = ["OPENAI_API_KEY"]
scopes = { OPENAI_API_KEY = ["agent.run", "tool.search.docs"] }

[deployment]
provider = "local-http"
base_path = "/run"
health_path = "/health"
public_url = "http://127.0.0.1:8787"

[dependencies]
# "helper.agent" = "^1.0.0"
"""

SAMPLE_PROMPT = """You are the agent package {{ package_name }}.
Task: {{ task }}

{% if memory_summary %}Memory:
{{ memory_summary }}
{% endif %}

{% if rag_summary %}Retrieved context:
{{ rag_summary }}
{% endif %}

Tools available:
{% for tool in tools %}- {{ tool.name }}: {{ tool.description }}
{% endfor %}

Return a concise answer and a small execution plan.
"""

SAMPLE_TOOL_MANIFEST = """[[tools]]
name = "docs"
description = "Search bundled docs"
builtin = "search.docs"
policy = "allow"
defaults = { query = "Mellow agent package" }

[[tools]]
name = "clock"
description = "Get current UTC time"
builtin = "time.now"
policy = "allow"
"""

SAMPLE_CAPABILITY_POLICY = """{
  "capabilities": {
    "allow": ["tools.search.docs", "tools.time.now"],
    "deny": []
  },
  "tools": {
    "allow": ["search.docs", "time.now"],
    "deny": []
  }
}
"""


def init_agent_package(path: str | Path, *, name: str = 'demo.agent', force: bool = False) -> Path:
    root = Path(path)
    if root.exists() and any(root.iterdir()) and not force:
        raise FileExistsError(f'agent package directory is not empty: {root}')
    (root / 'prompts').mkdir(parents=True, exist_ok=True)
    (root / 'tools').mkdir(parents=True, exist_ok=True)
    (root / 'policies').mkdir(parents=True, exist_ok=True)
    (root / '.mellow').mkdir(parents=True, exist_ok=True)
    (root / 'agent.toml').write_text(SAMPLE_AGENT_TOML.replace('demo.agent', name), encoding='utf-8')
    (root / 'prompts' / 'default.prompt').write_text(SAMPLE_PROMPT, encoding='utf-8')
    (root / 'tools' / 'manifest.toml').write_text(SAMPLE_TOOL_MANIFEST, encoding='utf-8')
    (root / 'policies' / 'capabilities.json').write_text(SAMPLE_CAPABILITY_POLICY, encoding='utf-8')
    return root
