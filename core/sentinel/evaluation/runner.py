import hashlib
import math
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from decimal import Decimal

from sentinel import clock
from sentinel.domain.classify import classify
from sentinel.errors import ErrorCode, SentinelError, SourceError
from sentinel.semantic.base import PairInput, PassageInput, SemanticEngine, ThesisInput
from sentinel.semantic.pricing import PriceTable, cost_usd, load_price_table
from sentinel.semantic.questions import MAX_EVIDENCE_SENTENCES, NO, QUESTION_SET_VERSION, YES
from sentinel.semantic.segment import split_sentences
from sentinel.settings.models import MODEL_ID

from .bounded import BoundedCall, CallToken, Cancellation
from .dataset import Dataset, validate_dataset
from .metrics import POSITIVE_CLASSES, cohen_kappa, metric_pair, total_usage
from .models import BaselineReport, EvalReport, EvalSample, Gate, GoldQuality, PredictionRow
from .replay import MissingCassette, ReplayEngine


@dataclass(frozen=True)
class EvalConfig:
    dataset: Dataset
    split: str = "test"
    lang: str = "all"
    model_id: str = MODEL_ID
    timeout_sec: float = 60
    allow_tuned_test: bool = False
    gate: bool = False
    code_version: str = "NOT_CAPTURED"

    def __post_init__(self) -> None:
        validate_dataset(self.dataset)
        if self.split not in ("test", "tuning", "all") or self.lang not in ("zh", "en", "all"):
            raise ValueError("invalid split/lang")
        if self.split == "all" and not self.allow_tuned_test:
            raise ValueError("mix tuning/test requires allow_tuned_test")
        if self.gate and (self.split != "test" or self.lang != "all"):
            raise ValueError("gate requires untouched test split, both languages")
        if not math.isfinite(self.timeout_sec) or not 0 < self.timeout_sec <= 60:
            raise ValueError("timeout must be finite in (0, 60]")
        if self.model_id not in load_price_table():
            raise ValueError("unknown pinned pricing model")


def _gate(config: EvalConfig, report: EvalReport) -> Gate:
    if not config.gate:
        return Gate(status="NOT_REQUESTED", passed=None, reason="MVP-0 has no F1 release threshold")
    zh, en = report.by_lang["zh"].strict.f1, report.by_lang["en"].strict.f1
    experimental = (
        report.strict.f1 is not None
        and report.strict.f1 >= 0.8
        and zh is not None
        and en is not None
        and Decimal(str(en)) - Decimal(str(zh)) <= Decimal("0.05")
        and report.failed == 0
        and report.completed == report.samples
    )
    eligible = (
        config.dataset.mode == "real"
        and report.real_model_status == "COMPLETED"
        and report.gold_quality.kappa is not None
        and report.gold_quality.kappa >= 0.6
        and report.samples >= 200
        and report.strict.positive_count >= 60
    )
    return Gate(
        status=("PASS" if experimental else "FAIL") if eligible else "NOT_RUN",
        passed=eligible and experimental,
        experimental_passed=experimental,
        reason="v1/G2 experiment; formal eligibility requires real adjudication, recorded/live "
        "model and >=200 test pairs including >=60 positives",
    )


class EvaluationRunner:
    def __init__(self, config: EvalConfig, engine: SemanticEngine) -> None:
        self.config, self.engine = config, engine
        self.cancel = Cancellation()
        self._bounded = BoundedCall()
        self._prices: PriceTable = load_price_table()

    def _process(
        self,
        sample: EvalSample,
        row: PredictionRow,
        token: CallToken,
        publish: Callable[[PredictionRow], None],
    ) -> PredictionRow:
        row = row.model_copy(deep=True)
        thesis = ThesisInput(
            "t1",
            sample.id,
            1,
            sample.thesis.statement,
            sample.thesis.kill_condition,
            hashlib.sha256(sample.thesis.model_dump_json().encode()).hexdigest(),
        )
        passage = PassageInput(
            sample.passage.event_id + ":" + sample.id,
            sample.passage.text,
            hashlib.sha256(sample.passage.text.encode()).hexdigest(),
        )
        token.raise_if_cancelled()
        if not isinstance(self.engine, ReplayEngine) and os.environ.get("SENTINEL_OFFLINE") == "1":
            raise SourceError(ErrorCode.SOURCE_UNAVAILABLE, reason="OFFLINE")
        row.usage.calls += 1
        row.usage.complete = False
        publish(row)
        scores = self.engine.score_pairs(sample.instrument, [PairInput(thesis, passage)], token)
        if (
            len(scores) != 1
            or (scores[0].thesis_id, scores[0].version, scores[0].passage_id)
            != (thesis.thesis_id, thesis.version, passage.passage_id)
            or scores[0].model_id != self.config.model_id
        ):
            raise ValueError("incomplete/mismatched pair score")
        score = scores[0]
        row.probabilities = asdict(score.probabilities)
        row.relation = classify(score.probabilities, yes=YES, no=NO)
        row.usage.input_tokens += score.input_tokens
        row.usage.estimated |= score.tokens_estimated
        row.usage.cost_usd = cost_usd(row.usage.input_tokens, self.config.model_id, self._prices)
        row.usage.complete = True
        publish(row)
        if row.relation in POSITIVE_CLASSES | {"uncertain"}:
            row.evidence_kind, row.evidence_start, row.evidence_end = (
                "passage",
                0,
                len(passage.text),
            )
            if sample.passage.content_status == "title_only":
                row.evidence_kind = "title"
            else:
                spans = split_sentences(passage.text)[:MAX_EVIDENCE_SENTENCES]
                token.raise_if_cancelled()
                row.usage.calls += 1
                row.usage.complete = False
                publish(row)
                try:
                    evidence = self.engine.locate_evidence(
                        thesis, row.relation, [s.text for s in spans], token
                    )
                    if evidence.model_id != self.config.model_id or len(
                        evidence.sentence_probabilities
                    ) != len(spans):
                        raise ValueError("incomplete/mismatched evidence")
                    row.usage.input_tokens += evidence.input_tokens
                    row.usage.estimated |= evidence.tokens_estimated
                    row.usage.cost_usd = cost_usd(
                        row.usage.input_tokens, self.config.model_id, self._prices
                    )
                    row.usage.complete = True
                    index = max(range(len(spans)), key=lambda i: evidence.sentence_probabilities[i])
                    if evidence.sentence_probabilities[index] >= NO:
                        row.evidence_kind, row.evidence_sentence = "sentence", index + 1
                        row.evidence_start, row.evidence_end = spans[index].start, spans[index].end
                except Exception as exc:
                    if isinstance(exc, (MissingCassette, SentinelError)) and (
                        isinstance(exc, MissingCassette)
                        or exc.code
                        in (ErrorCode.CANCELLED, ErrorCode.TIMEOUT, ErrorCode.UNAUTHENTICATED)
                    ):
                        raise
                    row.evidence_error = (
                        exc.code.value if isinstance(exc, SentinelError) else "MODEL_ERROR"
                    )
        token.raise_if_cancelled()
        row.status = "ok"
        return row

    def run(self) -> EvalReport:
        config = self.config
        samples = [
            s
            for s in config.dataset.samples
            if (config.split == "all" or s.split == config.split)
            and (config.lang == "all" or s.lang == config.lang)
        ]
        rows: list[PredictionRow] = []
        stop: str | None = None
        for sample in samples:
            row = PredictionRow(
                id=sample.id,
                split=sample.split,
                lang=sample.lang,
                subsets=list(sample.subsets),
                gold=sample.label.relation,
                gold_evidence_sentence=sample.label.evidence_sentence,
                status="not_run",
                model_id=config.model_id,
                question_set_version=QUESTION_SET_VERSION,
                thresholds={"yes": YES, "no": NO},
                code_version=config.code_version,
                engine=self.engine.name,
            )
            if stop or self.cancel.is_cancelled():
                row.error = "CANCELLED" if self.cancel.is_cancelled() else stop
                rows.append(row)
                continue
            snapshot = [row.model_copy(deep=True)]

            def publish(current: PredictionRow, progress: list[PredictionRow] = snapshot) -> None:
                progress[0] = current.model_copy(deep=True)

            def process(
                token: CallToken,
                s: EvalSample = sample,
                r: PredictionRow = row,
                p: Callable[[PredictionRow], None] = publish,
            ) -> PredictionRow:
                return self._process(s, r, token, p)

            start = time.monotonic()
            try:
                row = self._bounded.call(
                    process,
                    self.cancel,
                    config.timeout_sec,
                )
            except Exception as exc:
                row = snapshot[0].model_copy(deep=True)
                row.status, row.relation = "failed", None
                row.error = (
                    "MISSING_CASSETTE"
                    if isinstance(exc, MissingCassette)
                    else exc.code.value
                    if isinstance(exc, SentinelError)
                    else "MODEL_ERROR"
                )
                if row.error in (
                    "MISSING_CASSETTE",
                    "UNAUTHENTICATED",
                    "CONFIG_REQUIRED",
                    "SOURCE_UNAVAILABLE",
                    "CANCELLED",
                ):
                    stop = row.error
                elif self._bounded.busy:
                    stop = "IN_FLIGHT_TIMEOUT"
            row.usage.latency_ms = int((time.monotonic() - start) * 1000)
            rows.append(row)
        pair = metric_pair(rows)
        by_lang = {lang: metric_pair([r for r in rows if r.lang == lang]) for lang in ("zh", "en")}
        by_subset = {
            tag: metric_pair([r for r in rows if tag in r.subsets])
            for tag in ("numeric", "title_only", "adversarial", "long", "multi_thesis")
        }
        valid = [r for r in rows if r.status == "ok"]
        evidence_rows = [
            r
            for r in valid
            if r.gold in POSITIVE_CLASSES and r.relation in POSITIVE_CLASSES | {"uncertain"}
        ]
        hits = sum(
            r.evidence_kind == "sentence" and r.evidence_sentence == r.gold_evidence_sentence
            for r in evidence_rows
        )
        synthetic = config.dataset.manifest.source == "synthetic"
        gold = GoldQuality(
            status="NOT_RUN" if synthetic else "COMPLETED",
            kappa=None
            if synthetic
            else cohen_kappa(samples, config.dataset.manifest.annotator_ids),
            reason="no independent human annotators"
            if synthetic
            else "declared independent adjudicated labels",
        )
        source = self.engine.source if isinstance(self.engine, ReplayEngine) else "live_api"
        warnings = (
            [
                "Synthetic fixtures exercise functionality; "
                "no model accuracy or cost advantage claim."
            ]
            if synthetic
            else []
        )
        if pair.strict.positive_count < 20:
            warnings.append(
                "Too few positive samples; intervals are wide and conclusions provisional."
            )
        report = EvalReport(
            samples=len(samples),
            completed=len(valid),
            failed=sum(r.status == "failed" for r in rows),
            rows=rows,
            strict=pair.strict,
            lenient=pair.lenient,
            by_lang=by_lang,
            by_subset=by_subset,
            uncertain_count=sum(r.relation == "uncertain" for r in valid),
            uncertain_rate=sum(r.relation == "uncertain" for r in valid) / len(valid)
            if valid
            else None,
            evidence={
                "denominator": len(evidence_rows),
                "hits": hits,
                "hitRate": hits / len(evidence_rows) if evidence_rows else None,
                "passageCount": sum(r.evidence_kind == "passage" for r in evidence_rows),
                "titleCount": sum(r.evidence_kind == "title" for r in evidence_rows),
            },
            usage=total_usage(rows),
            gold_quality=gold,
            real_model_status="COMPLETED"
            if not synthetic and source != "synthetic" and len(valid) == len(samples)
            else "NOT_RUN",
            gate=Gate(status="NOT_REQUESTED", passed=None, reason="not requested"),
            exit_code=4 if len(valid) != len(samples) else 0,
            source=config.dataset.manifest.source,
            annotation_status=config.dataset.manifest.annotation_status,
            prediction_source=source,
            dataset_hash=config.dataset.manifest.sha256,
            code_version=config.code_version,
            model_id=config.model_id,
            question_set_version=QUESTION_SET_VERSION,
            thresholds={"yes": YES, "no": NO},
            engine=self.engine.name,
            date=clock.to_iso(clock.now()),
            split=config.split,
            lang=config.lang,
            warnings=warnings,
            pricing={
                "inputUsdPerMtok": str(self._prices[config.model_id]),
                "source": "resources/pricing.toml",
            },
        )
        report.gate = _gate(config, report)
        if config.gate and report.exit_code == 0 and not report.gate.passed:
            report.exit_code = 3
        return report


def evaluate(config: EvalConfig, engine: SemanticEngine) -> EvalReport:
    return EvaluationRunner(config, engine).run()


def attach_baseline(report: EvalReport, baseline: BaselineReport) -> None:
    report.baseline = baseline
    if baseline.status == "PARTIAL":
        report.exit_code = 4
