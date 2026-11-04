"""The three containers every tree is built from: a program body and the
statement and expression roots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


# --------- Program / Statements ---------

@dataclass
class Program:
    body: List["Stmt"]


class Stmt: ...


# --------- Expressions ---------

class Expr: ...
