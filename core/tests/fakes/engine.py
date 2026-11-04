from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sentinel.domain.classify import Probabilities, Relation
from sentinel.errors import CancelledError, EngineError
from sentinel.semantic.base import (
    CancelToken,
    EngineHealth,
    EngineName,
    EvidenceScore,
    PairInput,
    PairScore,
    PassageInput,
    ThesisInput,
    cartesian_pairs,
)
from sentinel.semantic.questions import build_evidence_questions


@dataclass
class FakeCancelToken:
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True

    def is_cancelled(self) -> bool:
        return self.cancelled

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledError()


class FakeEngine:
    def __init__(
        self,
        *,
        name: EngineName = "jev_direct",
        error: Exception | None = None,
        evidence_error: Exception | None = None,
        fail_after: int | None = None,
        before_pair: Callable[[int], None] | None = None,
    ) -> None:
        self.name = name
        self.error, self.evidence_error = error, evidence_error
        self.fail_after, self.before_pair = fail_after, before_pair
        self.score_calls = self.evidence_calls = self.requested_pairs = self.completed_pairs = 0
        self.pair_calls: list[tuple[PairInput, ...]] = []

    def health(self) -> EngineHealth:
        return EngineHealth("ok", "offline synthetic fake")

    def score_pairs(
        self, company: str, pairs: Sequence[PairInput], cancel: CancelToken
    ) -> list[PairScore]:
        cancel.raise_if_cancelled()
        self.score_calls += 1
        self.requested_pairs += len(pairs)
        self.pair_calls.append(tuple(pairs))
        if self.error is not None:
            raise self.error
        scores = []
        for index, pair in enumerate(pairs):
            if self.before_pair is not None:
                self.before_pair(index)
            cancel.raise_if_cancelled()
            if self.fail_after is not None and index >= self.fail_after:
                raise EngineError("MODEL_ERROR", detail="synthetic partial batch failure")
            p = Probabilities(
                0.97, 0.89, 0.84, 0.93 if pair.thesis.kill_condition is not None else None, 0.03
            )
            scores.append(
                PairScore(
                    pair.thesis.thesis_id,
                    pair.thesis.version,
                    pair.passage.passage_id,
                    p,
                    "jev-1.14.0",
                    10,
                    self.name == "jevdb",
                    0,
                )
            )
            self.completed_pairs += 1
        cancel.raise_if_cancelled()
        return scores

    def score_event(
        self,
        company: str,
        theses: Sequence[ThesisInput],
        passages: Sequence[PassageInput],
        cancel: CancelToken,
    ) -> list[PairScore]:
        return self.score_pairs(company, cartesian_pairs(theses, passages), cancel)

    def locate_evidence(
        self, thesis: ThesisInput, relation: Relation, sentences: Sequence[str], cancel: CancelToken
    ) -> EvidenceScore:
        cancel.raise_if_cancelled()
        build_evidence_questions(
            relation, len(sentences), has_kill=thesis.kill_condition is not None, flavor="direct"
        )
        self.evidence_calls += 1
        if self.evidence_error is not None:
            raise self.evidence_error
        return EvidenceScore([0.9] * len(sentences), "jev-1.14.0", 10, self.name == "jevdb")
