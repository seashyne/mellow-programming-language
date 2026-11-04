"""mellow-web: page/component source to TSX, plus the React dev-server app.

The machinery lives in `mellowlang/web_groups/`, one module per stage; this
module keeps the import path `mellowlang.web` that the `mellow web` commands
and the tests already use."""

from __future__ import annotations

from .web_groups.model import (
    MellowWebError,
    WebComponent,
    WebNode,
    WebState,
)

from .web_groups.parsing import (
    parse_web_source,
)

from .web_groups.emitting import (
    emit_tsx,
)

from .web_groups.devserver import (
    compile_file_to_tsx,
    prepare_react_dev_app,
    run_react_dev_app,
)
