"""The run, test, record, replay and diff commands.

The bodies live in `mellowlang/cli/commands/runtime_groups/`, one module per subject;
this module keeps the import path `mellowlang.cli.commands.runtime` that `cli/main.py`
already uses, so no caller needs a second home."""

from __future__ import annotations

from .runtime_groups.deps import pkg_auto_fetch_for_run
from .runtime_groups.golden import _cmd_diff, _cmd_record, _cmd_replay
from .runtime_groups.run import _cmd_run
from .runtime_groups.suite import _cmd_test
