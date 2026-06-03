# Mellow 1.7.0 — AI Native Language

Mellow 1.7.0 adds a practical first-party agent runtime layer on top of the existing language, CLI, package manager, and LSP work.

## Highlights
- `mellow agent run` for single-turn AI-native agent execution
- `mellow agent workflow` for built-in multi-step workflows
- Memory store backed by JSONL
- Simple RAG index with local text-file ingestion
- Tool registry with built-in tools (`time.now`, `calc.eval`, `search.docs`)
- Policy engine for tool allow/deny controls
- Structured output coercion for machine-readable results
- Observability log for tracing agent runs and tool calls
- Provider-agnostic model adapter abstraction

## Example commands
```bash
mellow agent demo
mellow agent run --task "plan a support workflow" --tool search.docs
mellow agent workflow --task "design an agent with memory" --rag-file examples/agents/demo_rag.txt
mellow agent inspect-log .mellow/agent_observability.jsonl
```

## Scope
This release establishes the runtime foundation. It is intentionally offline-first and deterministic by default. Hosted-model adapters, richer package ecosystems, stronger policy DSLs, and full production tracing can build on this surface in later versions.
