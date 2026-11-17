from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from sentinel.domain.classify import Relation
from sentinel.semantic.questions import MAX_KILL_CHARS, MAX_PASSAGE_CHARS, MAX_STATEMENT_CHARS

Gold = Literal["none", "support", "weaken", "overturn"]
Subset = Literal["numeric", "title_only", "adversarial", "long", "multi_thesis"]
Mode = Literal["fixture", "real"]


class Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class ThesisRef(Model):
    statement: str = Field(min_length=1, max_length=MAX_STATEMENT_CHARS)
    kill_condition: str | None = Field(max_length=MAX_KILL_CHARS)

    @field_validator("statement", "kill_condition")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("blank thesis text")
        return value


class PassageRef(Model):
    event_id: str = Field(pattern=r"^us:[0-9]{10}-[0-9]{2}-[0-9]{6}$")
    form_type: Literal["8-K", "6-K"]
    text: str = Field(min_length=1, max_length=MAX_PASSAGE_CHARS)
    content_status: Literal["full_text", "title_only"]

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank passage text")
        return value


class Label(Model):
    relation: Gold
    evidence_sentence: int | None = Field(ge=1)

    @model_validator(mode="after")
    def evidence_required(self) -> "Label":
        if (self.relation in ("weaken", "overturn")) != (self.evidence_sentence is not None):
            raise ValueError("evidenceSentence must identify one positive sentence")
        return self


class AnnotatorLabel(Label):
    id: str = Field(min_length=1)


class EvalSample(Model):
    id: str = Field(pattern=r"^p-[0-9]{4}$")
    split: Literal["tuning", "test"]
    lang: Literal["zh", "en"]
    subsets: list[Subset]
    event_state: Literal["planned", "completed", "cancelled", "na"]
    instrument: str = Field(pattern=r"^us:ZZ(?:AR|FD|CL|BK|EN|MD)$")
    thesis: ThesisRef
    passage: PassageRef
    label: Label
    annotators: list[AnnotatorLabel]
    adjudicated: bool
    notes: str


class SplitCounts(Model):
    total: int
    labels: dict[str, int]
    languages: dict[str, int]
    subsets: dict[str, int]


class Counts(Model):
    total: int
    positive: int
    negative: int
    splits: dict[str, SplitCounts]


class Manifest(Model):
    source: Literal["synthetic", "human"]
    annotation_status: Literal["unadjudicated", "adjudicated"]
    annotator_ids: list[str]
    independent_annotation: bool
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    split_seed: int
    generation: str
    counts: Counts


class Usage(Model):
    calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    cost_usd: Decimal = Field(default=Decimal("0.000000"), ge=0)
    estimated: bool = False
    complete: bool = True


class PredictionRow(Model):
    id: str
    split: Literal["tuning", "test"]
    lang: Literal["zh", "en"]
    subsets: list[str]
    gold: Gold
    gold_evidence_sentence: int | None = None
    relation: Relation | None = None
    status: Literal["ok", "failed", "not_run"]
    error: str | None = None
    probabilities: dict[str, float | None] | None = None
    evidence_kind: Literal["sentence", "passage", "title"] | None = None
    evidence_sentence: int | None = None
    evidence_start: int | None = None
    evidence_end: int | None = None
    evidence_error: str | None = None
    usage: Usage = Field(default_factory=Usage)
    model_id: str | None = None
    question_set_version: str | None = None
    thresholds: dict[str, float] = Field(default_factory=dict)
    code_version: str | None = None
    engine: str | None = None


class Metrics(Model):
    n: int
    positive_count: int
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float | None
    recall: float | None
    f1: float | None
    precision_ci: tuple[float, float] | None
    recall_ci: tuple[float, float] | None
    f1_ci: tuple[float, float] | None
    matrix: list[list[int]]


class MetricPair(Model):
    strict: Metrics
    lenient: Metrics


class GoldQuality(Model):
    status: Literal["NOT_RUN", "COMPLETED"]
    kappa: float | None = None
    reason: str


class Gate(Model):
    status: Literal["NOT_REQUESTED", "NOT_RUN", "FAIL", "PASS"]
    passed: bool | None
    experimental_passed: bool | None = None
    reason: str


class BaselineReport(Model):
    status: Literal["NOT_RUN", "COMPLETED", "PARTIAL"] = "NOT_RUN"
    reason: str = "not_configured"
    rows: list[PredictionRow] = Field(default_factory=list)
    usage: Usage = Field(default_factory=lambda: Usage(complete=False))
    p95_latency_ms: float = 0
    metrics: MetricPair | None = None
    model_id: str | None = None
    source: str = "not_run"
    pricing: dict[str, str] = Field(default_factory=dict)


class EvalReport(Model):
    samples: int
    completed: int
    failed: int
    rows: list[PredictionRow]
    strict: Metrics
    lenient: Metrics
    by_lang: dict[str, MetricPair]
    by_subset: dict[str, MetricPair]
    uncertain_count: int
    uncertain_rate: float | None
    evidence: dict[str, int | float | None]
    usage: Usage
    baseline: BaselineReport = Field(default_factory=BaselineReport)
    gold_quality: GoldQuality
    real_model_status: Literal["NOT_RUN", "COMPLETED"]
    native_eval_status: Literal["NOT_RUN"] = "NOT_RUN"
    evidence_policy: str = (
        "Reviewed S-05 policy: passage fallback only for MODEL_ERROR/TIMEOUT/RATE_LIMITED; "
        "other errors and global deadline fail the sample, preserving known score usage."
    )
    gate: Gate
    exit_code: int
    source: str
    annotation_status: str
    prediction_source: str
    dataset_hash: str
    code_version: str
    model_id: str
    question_set_version: str
    thresholds: dict[str, float]
    engine: str
    date: str
    split: str
    lang: str
    warnings: list[str]
    pricing_verification: str = "TODO-VERIFY(G0-JEV)"
    pricing: dict[str, str] = Field(default_factory=dict)
    usage_basis: str = (
        "attempted API operations; failed remote usage may be unknown; "
        "Jev output tokens unavailable; retries are not observable via SemanticEngine"
    )
    cache_enabled: bool = False
