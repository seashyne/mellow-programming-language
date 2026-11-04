"""Agent package registry: sign, build, publish, resolve, install.

The machinery lives in `mellowlang/agents/registry_groups/`, one module per
concern; this module keeps the import path `mellowlang.agents.registry` that
`agents/__init__.py` and the tests already use."""

from __future__ import annotations

from .registry_groups.layout import (
    AGENT_ROOT,
    AGENT_REGISTRY_ROOT,
    AGENT_INSTALLED_ROOT,
    AGENT_CACHE_ROOT,
    ARCHIVE_EXT,
    LOCKFILE_NAME,
    REPRO_ZIP_TIMESTAMP,
    ensure_agent_dirs,
    normalize_agent_name,
)

from .registry_groups.integrity import (
    sign_agent_manifest,
    verify_agent_manifest_signature,
)

from .registry_groups.auth import (
    get_agent_registry_url,
    get_agent_auth_token,
    set_agent_auth_token,
    clear_agent_auth_token,
    agent_registry_whoami,
)

from .registry_groups.catalog import (
    agent_manifest_dict,
    list_local_agent_versions,
    search_agent_local,
)

from .registry_groups.archive import (
    build_agent_archive,
    publish_agent_from_dir,
)

from .registry_groups.graph import (
    agent_dependency_graph,
)

from .registry_groups.lock import (
    generate_agent_lock,
    write_agent_lock,
    read_agent_lock,
)

from .registry_groups.install import (
    install_agent_package,
    install_agent_with_lock,
    load_installed_agent,
)

from .registry_groups.remote import (
    search_agent_remote,
    publish_agent_remote,
    install_agent_remote,
)
