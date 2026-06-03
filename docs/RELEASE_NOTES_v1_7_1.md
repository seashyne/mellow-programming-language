
# Mellow 1.7.1 — Agent Packages + Prompt DSL + Tool Manifest

Highlights:
- Agent package spec via `agent.toml`
- Prompt DSL with `{{ var }}`, `{% if %}`, and `{% for %}`
- Tool manifest mapping package-local tool names to builtin tools
- CLI commands for package init/run and prompt rendering

Examples:
- `mellow agent package init my-agent --name my.agent`
- `mellow agent package run my-agent --task "plan a workflow"`
- `mellow agent run --task "summarize" --prompt-file prompts/default.prompt --tool-manifest tools/manifest.toml`
