"""The lazy import surface the run commands were written against.

One `_lazy_attr` alias per package-manager entry point, so `mellow run` does not
import the resolver until a project actually needs it."""

from __future__ import annotations

from ...common import _lazy_attr


pkg_auto_fetch_for_run = _lazy_attr("mellowlang.package_manager", "auto_fetch_for_run")
