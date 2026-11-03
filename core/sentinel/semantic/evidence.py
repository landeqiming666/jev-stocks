from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sentinel.domain.classify import validate_probability
from sentinel.errors import EngineError

from .cache import DecisionRow
from .segment import TextSpan, split_sentences

MAX_EVIDENCE_SENTENCES = 40
EVIDENCE_MIN_PROBABILITY = 0.3
RELATION_RANK = {"overturn": 0, "weaken": 1, "uncertain": 2}
EvidenceKind = Literal["sentence", "passage", "title"]


@dataclass(frozen=True)
class EvidenceResult:
    kind: EvidenceKind
    start: int | None
    end: int | None
    text: str
    warn: str | None = None


def select_representative(rows: Sequence[DecisionRow]) -> DecisionRow | None:
    eligible = [r for r in rows if r.relation in RELATION_RANK]
    return min(
        eligible,
        key=lambda r: (RELATION_RANK[r.relation], -r.headline, r.seq, r.decision_id),
        default=None,
    )


def prepare_sentences(text: str) -> list[TextSpan]:
    return split_sentences(text)[:MAX_EVIDENCE_SENTENCES]


def fallback_evidence(text: str, content_status: str, *, warn: str | None = None) -> EvidenceResult:
    return EvidenceResult(
        "title" if content_status == "title_only" else "passage", None, None, text, warn
    )


def valid_evidence(
    kind: str | None,
    start: int | None,
    end: int | None,
    text: str,
    *,
    content_status: str = "full_text",
) -> bool:
    if not text.strip():
        return False
    if content_status == "title_only":
        return kind == "title" and start is None and end is None
    if kind == "passage":
        return start is None and end is None
    return (
        kind == "sentence"
        and type(start) is int
        and type(end) is int
        and 0 <= start < end <= len(text)
        and bool(text[start:end].strip())
    )


def evidence_from_score(
    text: str, sentences: Sequence[TextSpan], probabilities: Sequence[float]
) -> EvidenceResult:
    try:
        if not sentences or len(probabilities) != len(sentences):
            raise ValueError("evidence count differs")
        for value in probabilities:
            validate_probability(value)
    except (TypeError, ValueError):
        raise EngineError("MODEL_ERROR", detail="INVALID_EVIDENCE_RESPONSE") from None
    index = max(range(len(probabilities)), key=lambda i: probabilities[i])
    if probabilities[index] < EVIDENCE_MIN_PROBABILITY:
        return fallback_evidence(text, "full_text", warn="LOW_PROBABILITY")
    sentence = sentences[index]
    if (
        not valid_evidence("sentence", sentence.start, sentence.end, text)
        or text[sentence.start : sentence.end] != sentence.text
    ):
        return fallback_evidence(text, "full_text", warn="OFFSET_MISMATCH")
    return EvidenceResult("sentence", sentence.start, sentence.end, sentence.text)
