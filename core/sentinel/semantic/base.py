from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal, Never, Protocol, runtime_checkable

from sentinel.domain.classify import Probabilities, Relation, validate_probability

JEV_CONCURRENCY = 4
EngineName = Literal["jevdb", "jev_direct"]


@runtime_checkable
class CancelToken(Protocol):
    def is_cancelled(self) -> bool: ...
    def raise_if_cancelled(self) -> None: ...


def validate_count(value: int, *, minimum: int = 0, maximum: int | None = None) -> None:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError("integer outside allowed range")


def _text(value: str, maximum: int | None = None) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or (maximum is not None and len(value) > maximum)
    ):
        raise ValueError("nonempty text outside allowed length")


@dataclass(frozen=True)
class ThesisInput:
    ref: str
    thesis_id: str
    version: int
    statement: str
    kill_condition: str | None
    content_hash: str

    def __post_init__(self) -> None:
        from .questions import MAX_KILL_CHARS, MAX_STATEMENT_CHARS, validate_ref

        validate_ref(self.ref)
        validate_count(self.version, minimum=1)
        _text(self.thesis_id)
        _text(self.content_hash)
        _text(self.statement, MAX_STATEMENT_CHARS)
        if self.kill_condition is not None:
            _text(self.kill_condition, MAX_KILL_CHARS)


@dataclass(frozen=True)
class PassageInput:
    passage_id: str
    text: str
    content_hash: str

    def __post_init__(self) -> None:
        from .questions import MAX_PASSAGE_CHARS

        _text(self.passage_id)
        _text(self.content_hash)
        _text(self.text, MAX_PASSAGE_CHARS)


@dataclass(frozen=True)
class PairInput:
    thesis: ThesisInput
    passage: PassageInput


@dataclass(frozen=True)
class PairScore:
    thesis_id: str
    version: int
    passage_id: str
    probabilities: Probabilities
    model_id: str
    input_tokens: int
    tokens_estimated: bool
    latency_ms: int

    def __post_init__(self) -> None:
        validate_count(self.version, minimum=1)
        validate_count(self.input_tokens)
        validate_count(self.latency_ms)
        if type(self.tokens_estimated) is not bool:
            raise ValueError("tokens_estimated must be bool")


class _FrozenProbabilities(list[float]):
    # 保持 06 的 list 字段契约，同时防止调用方修改已返回的证据概率。
    def _reject(self, *args: object, **kwargs: object) -> Never:
        raise TypeError("evidence probabilities are immutable")

    __setitem__ = __delitem__ = __iadd__ = __imul__ = _reject
    append = extend = insert = pop = remove = clear = reverse = sort = _reject

    def __copy__(self) -> "_FrozenProbabilities":
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> "_FrozenProbabilities":
        return self


@dataclass(frozen=True)
class EvidenceScore:
    sentence_probabilities: list[float]
    model_id: str
    input_tokens: int
    tokens_estimated: bool

    def __post_init__(self) -> None:
        from .questions import MAX_EVIDENCE_SENTENCES

        validate_count(len(self.sentence_probabilities), maximum=MAX_EVIDENCE_SENTENCES)
        for value in self.sentence_probabilities:
            validate_probability(value)
        object.__setattr__(
            self, "sentence_probabilities", _FrozenProbabilities(self.sentence_probabilities)
        )
        validate_count(self.input_tokens)
        if type(self.tokens_estimated) is not bool:
            raise ValueError("tokens_estimated must be bool")


@dataclass(frozen=True)
class EngineHealth:
    state: Literal["ok", "degraded", "unconfigured"]
    detail: str


@runtime_checkable
class SemanticEngine(Protocol):
    name: EngineName

    def health(self) -> EngineHealth: ...
    def score_pairs(
        self, company: str, pairs: Sequence[PairInput], cancel: CancelToken
    ) -> list[PairScore]: ...
    def score_event(
        self,
        company: str,
        theses: Sequence[ThesisInput],
        passages: Sequence[PassageInput],
        cancel: CancelToken,
    ) -> list[PairScore]: ...
    def locate_evidence(
        self, thesis: ThesisInput, relation: Relation, sentences: Sequence[str], cancel: CancelToken
    ) -> EvidenceScore: ...


def cartesian_pairs(
    theses: Iterable[ThesisInput], passages: Sequence[PassageInput]
) -> list[PairInput]:
    return [PairInput(thesis, passage) for thesis in theses for passage in passages]
