"""Mellow Magic Graphics: parse `mmg.app(...)` sources, describe the runtime and

run the window loop.

The machinery lives in `mellowlang/mmg_groups/`, one module per concern; this
module keeps the import path `mellowlang.mmg_runtime` that `mmg_gpu_runtime`, the
CLI media commands and the MMG tests already use."""

from __future__ import annotations

from .mmg_groups.parsing import (
    APP_RE,
    CALL_RE,
    KEEP_RE,
)

from .mmg_groups.spec import (
    dump_mmg_spec_json,
    parse_mmg_file,
    parse_mmg_spec,
)

from .mmg_groups.status import (
    mmg_status,
)

from .mmg_groups.launch import (
    launch_mmg,
)
