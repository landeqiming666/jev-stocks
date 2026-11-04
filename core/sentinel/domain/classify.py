from dataclasses import dataclass
from math import isfinite
from typing import Literal

Relation = Literal["none", "support", "weaken", "overturn", "uncertain"]


def validate_probability(value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= value <= 1
        or not isfinite(value)
    ):
        raise ValueError("probability must be a finite number in [0, 1]")


@dataclass(frozen=True)
class Probabilities:
    relevant: float
    against: float
    contradicts: float
    kill_met: float | None
    supports: float

    def __post_init__(self) -> None:
        for value in (self.relevant, self.against, self.contradicts, self.supports):
            validate_probability(value)
        if self.kill_met is not None:
            validate_probability(self.kill_met)


def classify(p: Probabilities, yes: float = 0.7, no: float = 0.3) -> Relation:
    validate_probability(yes)
    validate_probability(no)
    if no >= yes:
        raise ValueError("thresholds must satisfy 0 <= no < yes <= 1")
    signals = (p.against, p.contradicts) + (() if p.kill_met is None else (p.kill_met,))
    if p.relevant < no:
        return "none"
    if p.contradicts >= yes or (p.kill_met is not None and p.kill_met >= yes):
        return "overturn"
    if p.against >= yes:
        return "weaken"
    if any(no <= value < yes for value in signals):
        return "uncertain"
    if p.supports >= yes and p.against < no:
        return "support"
    return "none"


def headline(p: Probabilities) -> float:
    return max(p.against, p.contradicts, p.kill_met if p.kill_met is not None else 0.0)
