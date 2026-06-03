# Mellow 1.7 AI Native Overview

## Capability map
- Agent System: runtime orchestration, model selection, memory, tools, retrieval
- Tool System: built-in registry and policy-gated invocation
- Workflow: repeatable multi-step execution graph
- Memory: JSONL store with simple recall and summaries
- RAG: local text ingestion and token-overlap retrieval
- Model abstraction: provider-neutral adapter interface
- Structured output: best-effort coercion into JSON-like dicts
- Package ecosystem: starter package folders for agents/tools/workflows
- Policy system: allow-list / deny-list for tools
- Observability: JSONL event stream for runs and tool calls

## Commands
```bash
mellow agent demo
mellow agent run --task "draft a response" --model rule-based --tool search.docs
mellow agent workflow --task "build a support playbook"
mellow agent inspect-log .mellow/agent_observability.jsonl
```
