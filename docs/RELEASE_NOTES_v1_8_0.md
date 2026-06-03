# Mellow 1.8.0 Agent Platform

## Highlights

### 1. Agent Security Layer
- Sandbox-aware runtime
- Capability permissions for tools and sensitive actions
- Secret store with CLI management and selective injection

### 2. Agent Runtime Engine
- Workflow retries
- Per-step timeout checks
- Parallel workflow steps
- Runtime debug payload with run id and token estimates

### 3. Observability + Debugging
- Structured run ids and event sequences
- Token usage estimates
- Tool latency logging
- `mellow agent trace` and improved `inspect-log`

### 4. Developer Platform & Ecosystem
- `mellow agent preview`
- `mellow agent prompt-debug`
- `mellow agent playground`
- `mellow agent serve`
- `mellow agent marketplace`
- `mellow agent deploy`

## Example commands

```bash
mellow agent secret set OPENAI_API_KEY sk-demo
mellow agent run --task "search docs" --tool search.docs --sandbox --allow-cap tools.search.docs --debug
mellow agent workflow --task "plan release" --parallel --retries 2 --timeout-ms 2000 --sandbox --allow-cap tools.search.docs --allow-cap tools.time.now
mellow agent preview my.agent
mellow agent prompt-debug my-agent/prompts/default.prompt --task "summarize docs"
mellow agent playground --out .mellow/playground/index.html
mellow agent marketplace agent
mellow agent deploy my.agent
```
