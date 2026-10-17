from __future__ import annotations

from dataclasses import dataclass, field

from ..query.frame import QueryFrame


@dataclass
class Clarification:
    message: str
    field: str                 # metric | dimension | time
    options: list[str]         # flat column names the user can pick
    question: str              # the question to re-run with the choice applied


@dataclass
class Session:
    last_frame: QueryFrame | None = None
    pending: Clarification | None = None
    history: list[str] = field(default_factory=list)
