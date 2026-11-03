from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import Field

from sentinel.domain.classify import Probabilities, Relation
from sentinel.semantic.base import (
    CancelToken,
    EngineHealth,
    EvidenceScore,
    PairInput,
    PairScore,
    PassageInput,
    ThesisInput,
    cartesian_pairs,
)
from sentinel.semantic.questions import MAX_EVIDENCE_SENTENCES, QUESTION_SET_VERSION
from sentinel.semantic.segment import split_sentences

from .dataset import Dataset, input_hash
from .models import Model


class MissingCassette(Exception):
    pass


class Frame(Model):
    id: str
    input_hash: str
    probabilities: dict[str, float | None]
    sentence_probabilities: list[float]
    input_tokens: int = Field(ge=0)
    evidence_input_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)


class Cassette(Model):
    source: Literal["synthetic", "recorded"]
    dataset_hash: str
    model_id: str
    question_set_version: str
    frames: list[Frame]


class ReplayEngine:
    name: Literal["jev_direct"] = "jev_direct"

    def __init__(self, directory: Path, dataset: Dataset, model_id: str) -> None:
        self.model_id = model_id
        self.frames: dict[str, Frame] = {}
        self.source: Literal["synthetic", "recorded"] = "synthetic"
        sources = set()
        known = {s.id: s for s in dataset.samples}
        for path in sorted(directory.glob("*.json")):
            cassette = Cassette.model_validate_json(path.read_text())
            if (
                cassette.dataset_hash != dataset.manifest.sha256
                or cassette.model_id != model_id
                or cassette.question_set_version != QUESTION_SET_VERSION
            ):
                raise ValueError("cassette provenance/version mismatch")
            sources.add(cassette.source)
            for frame in cassette.frames:
                if frame.id in self.frames or frame.id not in known:
                    raise ValueError("duplicate or unknown cassette id")
                sample = known[frame.id]
                p = Probabilities(**frame.probabilities)  # type: ignore[arg-type]
                if (
                    (p.kill_met is None) != (sample.thesis.kill_condition is None)
                    or frame.input_hash != input_hash(sample)
                    or len(frame.sentence_probabilities)
                    != min(MAX_EVIDENCE_SENTENCES, len(split_sentences(sample.passage.text)))
                ):
                    raise ValueError("cassette input/evidence binding mismatch")
                EvidenceScore(
                    frame.sentence_probabilities, model_id, frame.evidence_input_tokens, True
                )
                self.frames[frame.id] = frame
        if len(sources) > 1:
            raise ValueError("mixed cassette sources")
        if sources:
            self.source = sources.pop()

    def health(self) -> EngineHealth:
        return EngineHealth("ok", "offline replay")

    def _frame(self, thesis: ThesisInput) -> Frame:
        if thesis.thesis_id not in self.frames:
            raise MissingCassette()
        return self.frames[thesis.thesis_id]

    def score_pairs(
        self, company: str, pairs: Sequence[PairInput], cancel: CancelToken
    ) -> list[PairScore]:
        cancel.raise_if_cancelled()
        result = []
        for pair in pairs:
            frame = self._frame(pair.thesis)
            result.append(
                PairScore(
                    pair.thesis.thesis_id,
                    pair.thesis.version,
                    pair.passage.passage_id,
                    Probabilities(**frame.probabilities),  # type: ignore[arg-type]
                    self.model_id,
                    frame.input_tokens,
                    self.source == "synthetic",
                    frame.latency_ms,
                )
            )
        return result

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
        frame = self._frame(thesis)
        return EvidenceScore(
            frame.sentence_probabilities,
            self.model_id,
            frame.evidence_input_tokens,
            self.source == "synthetic",
        )
