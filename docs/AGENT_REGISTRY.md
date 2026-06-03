# Agent Registry Quickstart

## Create a package

```bash
mellow agent package init my-agent --name my.agent
```

## Build an archive

```bash
mellow agent package build my-agent
```

## Publish locally

```bash
mellow agent package publish my-agent
```

## Search locally

```bash
mellow agent package search agent
```

## Install locally

```bash
mellow agent package install my.agent
```

## Run installed package

```bash
mellow agent package run my.agent --task "plan a launch"
```

## Remote mode

```bash
mellow login --token <token>
mellow agent package publish my-agent --online --registry https://registry.example.com
mellow agent package search my --online --registry https://registry.example.com
mellow agent package install my.agent --online --registry https://registry.example.com
```

## File layout

```text
agent.toml
prompts/default.prompt
tools/manifest.toml
```
