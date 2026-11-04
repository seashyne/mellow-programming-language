"""The class the compiler imports, assembled from the machine and its two chains."""

from __future__ import annotations

from .driver import LoweringDriverMixin
from .expressions import ExpressionMixin
from .statements import StatementMixin


class IRLowerer(LoweringDriverMixin, StatementMixin, ExpressionMixin):
    pass
