"""Agent control plane: deployments, revisions, rollouts, metrics and alerts.

The machinery lives in `mellowlang/agents/control_plane_groups/`, one module
per concern; this module keeps the import path
`mellowlang.agents.control_plane` that `agents/__init__.py`, the CLI and the
tests already use."""

from __future__ import annotations

from .control_plane_groups.state import (
    CONTROL_PLANE_HOME,
)

from .control_plane_groups.deploy import (
    register_deployment,
    sync_deployment,
)

from .control_plane_groups.inspection import (
    get_deployment_status,
    list_deployments,
    list_revisions,
    run_health_check,
)

from .control_plane_groups.rollout import (
    rollback_deployment,
    rollout_revision,
    update_traffic_split,
)

from .control_plane_groups.observability import (
    evaluate_alerts,
    get_autoscaling_signals,
    get_deployment_metrics,
    record_deployment_metrics,
    set_alert_rules,
)
