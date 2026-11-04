from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from sentinel.errors import EngineError, ErrorCode
from sentinel.messages import render

from ..base import EngineName, SemanticEngine


@dataclass(frozen=True)
class EngineFactories:
    jevdb: Callable[[], SemanticEngine]
    jev_direct: Callable[[], SemanticEngine]


@dataclass(frozen=True)
class EngineChange:
    from_engine: EngineName
    to_engine: EngineName
    reason: str


@dataclass(frozen=True)
class EngineSelection:
    engine: SemanticEngine
    changed: EngineChange | None = None


def select_engine(
    choice: Literal["auto", "jevdb", "jev_direct"], factories: EngineFactories
) -> EngineSelection:
    if choice == "jev_direct":
        return EngineSelection(factories.jev_direct())
    if choice == "jevdb":
        return EngineSelection(factories.jevdb())
    if choice != "auto":
        raise ValueError("unknown engine choice")
    try:
        return EngineSelection(factories.jevdb())
    except EngineError as exc:
        if exc.code != ErrorCode.ENGINE_UNAVAILABLE:
            raise
    engine = factories.jev_direct()
    return EngineSelection(engine, EngineChange("jevdb", "jev_direct", render("engine.changed")))
