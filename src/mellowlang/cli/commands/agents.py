"""The `mellow agent ...` command handlers.

The bodies live in `cli/commands/agent_groups/`, one module per subject; this module keeps the
import path `mellowlang.cli.main` already uses, so neither the lazy name block nor a command
handler needs a second home."""

from __future__ import annotations

from .agent_groups.deps import (
    pkg_get_registry_url, serve_playground, build_static_playground, _AG, AgentRuntime,
    MemoryStore, ObservationLog, PolicyEngine, SimpleRAGIndex, Workflow,
    WorkflowRunner, WorkflowStep, builtin_tool_registry, resolve_model_adapter, render_prompt_file,
    load_tool_manifest, load_agent_package, init_agent_package, apply_tool_manifest, build_agent_archive,
    publish_agent_from_dir, install_agent_package, search_agent_local, publish_agent_remote, install_agent_remote,
    search_agent_remote, load_installed_agent, agent_dependency_graph, generate_agent_lock, write_agent_lock,
    install_agent_with_lock, set_agent_auth_token, clear_agent_auth_token, agent_registry_whoami, SandboxConfig,
    set_secret, remove_secret, list_secrets, resolve_secret_env, read_observation_file,
    load_signed_policy, build_deployment_manifest, load_deployment_manifest, write_deployment_bundle, sign_capability_policy,
    register_deployment, list_deployments, get_deployment_status, sync_deployment, list_revisions,
    rollout_revision, run_health_check, update_traffic_split, rollback_deployment, record_deployment_metrics,
    get_deployment_metrics, get_autoscaling_signals, set_alert_rules, evaluate_alerts, add_job,
    agent_list_jobs, run_due_jobs, run_background_runner, read_runner_status, add_trigger,
    list_triggers, emit_event, add_webhook, list_webhooks, receive_webhook,
    submit_job, get_queue_item, list_queue, drain_queue, list_dead_letter,
    retry_queue_item, read_queue_log, queue_stats, start_webhook_server, read_webhook_server_status,
    read_job_api_status,
)
from .agent_groups.support import (
    _load_rag_index, _make_agent_runtime, _agent_prompt_context, _run_agent_package, _print_graph,
    _resolve_agent_package_ref, _parse_jsonish, _parse_filters, _build_backoff,
)
from .agent_groups.runtime import (
    _cmd_agent_run, _cmd_agent_workflow, _cmd_agent_demo, _cmd_agent_inspect_log,
)
from .agent_groups.lifecycle import (
    _cmd_agent_package_init, _cmd_agent_package_lock, _cmd_agent_registry_login, _cmd_agent_registry_logout, _cmd_agent_registry_whoami,
    _cmd_agent_package_build, _cmd_agent_package_publish, _cmd_agent_package_install, _cmd_agent_package_graph, _cmd_agent_package_search,
    _cmd_agent_secret,
)
from .agent_groups.inspection import (
    _cmd_agent_prompt, _cmd_agent_trace, _cmd_agent_preview, _cmd_agent_prompt_debug,
)
from .agent_groups.serve import (
    _cmd_playground, _cmd_agent_playground, _cmd_agent_serve, _cmd_agent_marketplace, _cmd_agent_deploy,
)
from .agent_groups.control_plane import (
    _cmd_agent_control_plane, _cmd_agent_policy_sign, _cmd_agent_policy_verify,
)
from .agent_groups.automation import (
    _scheduled_job_callback, _cmd_agent_schedule, _cmd_agent_trigger, _cmd_agent_webhook, _cmd_agent_queue,
    _cmd_agent_jobs, _cmd_agent_runner,
)
