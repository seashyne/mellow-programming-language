"""Desktop host: window specs, the Tk/ttk runtime and portable bundles.

The machinery lives in `mellowlang/desktop_host_groups/`, one module per
concern; this module keeps the import path `mellowlang.desktop_host` that the
`mellow desktop` commands and the tests already use."""

from __future__ import annotations

from .desktop_host_groups.parsing import (
    CALL_RE,
    STATE_RE,
    WINDOW_RE,
    parse_window_spec,
)

from .desktop_host_groups.files import (
    dump_spec_json,
    parse_window_file,
)

from .desktop_host_groups.runtime import (
    DesktopRuntime,
    launch_window,
)

from .desktop_host_groups.bundle import (
    build_desktop_bundle,
)

from .desktop_host_groups.status import (
    desktop_status,
)
