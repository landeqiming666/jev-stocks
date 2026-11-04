from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import traceback
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import duckdb
import pytest
from duckdb.func import FunctionNullHandling
from duckdb.sqltypes import DOUBLE, VARCHAR

from sentinel.errors import (
    CancelledError,
    EngineError,
    ErrorCode,
    InternalError,
    SourceError,
    UserError,
)
from sentinel.logging_setup import JsonFormatter
from sentinel.secrets.service import SecretsService
from sentinel.security.redact import MASK, clear_secrets, redact_text
from sentinel.semantic.base import (
    EvidenceScore,
    PairInput,
    PassageInput,
    SemanticEngine,
    ThesisInput,
)
from sentinel.semantic.budget import estimate_tokens
from sentinel.semantic.engines import jevdb
from sentinel.semantic.questions import build_evidence_questions, build_score_questions

FIXTURES = Path(__file__).parents[2] / "fixtures" / "jevdb"
KEY = "test-key-do-not-use"


class Token:
    def __init__(self) -> None:
        self.event = threading.Event()

    def is_cancelled(self) -> bool:
        return self.event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise CancelledError()


class Connection:
    # 真实 DuckDB 执行 SQL，只有扩展注册和概率是显式 synthetic 替身。
    def __init__(self) -> None:
        self.db = duckdb.connect(":memory:")
        self.statements: list[tuple[str, Any]] = []
        self.calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        self.rows: list[tuple[Any, ...]] = []
        self.description: Any = None
        self.override: list[tuple[Any, ...]] | None = None
        self.failure: str | None = None
        self.fail_prefix: str | None = None
        self.stats_failure = False
        self.block = False
        self.ignore_interrupt = False
        self.entered, self.release = threading.Event(), threading.Event()
        self.interrupts = self.closed = 0
        self.secret = False
        self.env_keys: list[str | None] = []

        def probability(question: str, left: str, right: str) -> float | None:
            a, b = json.loads(left), json.loads(right)
            if any(v is None for v in a.values()) or any(v is None for v in b.values()):
                return None
            self.calls.append((question, a, b))
            if "condition in `kill_condition`" in question:
                return 0.8
            if "directly contradicts" in question:
                return 0.7
            if "less likely" in question:
                return 0.6
            if "more likely" in question:
                return 0.2
            return 0.9

        self.db.create_function(
            "synthetic_probability",
            probability,
            [VARCHAR] * 3,
            DOUBLE,
            null_handling=FunctionNullHandling.SPECIAL,
            side_effects=True,
        )
        self.db.execute(
            "CREATE MACRO jev_probability(q,a,b) AS synthetic_probability(q,to_json(a),to_json(b))"
        )
        self.db.execute("CREATE MACRO jev_keys_overlap(a,b) AS list_has_any(a,b)")

    def execute(self, sql: str, parameters: Any = None) -> Connection:
        self.statements.append((sql, parameters))
        if self.fail_prefix and sql.startswith(self.fail_prefix):
            raise RuntimeError(KEY + " private input " + self.fail_prefix)
        if sql.startswith("LOAD") or sql.startswith("SET"):
            self.rows = []
        elif sql.startswith("CREATE SECRET"):
            self.env_keys.append(os.environ.get("JEV_API_KEY"))
            self.secret = True
        elif sql.startswith("DROP SECRET"):
            self.secret = False
        elif sql == "SELECT * FROM jevdb_stats()":
            if self.stats_failure:
                raise RuntimeError(KEY)
            self.description = [("requests",), ("body",), ("input_tokens",)]
            self.rows = [(len(self.calls), KEY, 0)]
        else:
            scoring = "jev_probability(" in sql
            if scoring:
                self.entered.set()
                if self.block:
                    assert self.release.wait(5)
                if self.failure:
                    raise RuntimeError(self.failure)
                if self.override is not None:
                    self.rows = self.override
                    return self
            result = self.db.execute(sql, parameters) if parameters else self.db.execute(sql)
            self.rows = result.fetchall()
            self.description = result.description
        return self

    def executemany(self, sql: str, parameters: Iterable[Sequence[Any]]) -> Connection:
        values = list(parameters)
        self.statements.append((sql, values))
        if self.fail_prefix and sql.startswith(self.fail_prefix):
            raise RuntimeError(KEY)
        self.db.executemany(sql, values)
        return self

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    def interrupt(self) -> None:
        self.interrupts += 1
        if not self.ignore_interrupt:
            self.release.set()
            self.failure = "INTERRUPT Error"

    def close(self) -> None:
        self.closed += 1
        self.db.close()


@pytest.fixture
def inputs() -> tuple[list[ThesisInput], list[PassageInput]]:
    return (
        [
            ThesisInput("t1", "th1", 1, "ZZAR expands research.", "Research stops.", "h1"),
            ThesisInput("t2", "th2", 2, "ZZAR expands sales.", None, "h2"),
        ],
        [PassageInput(f"p{i}", f"ZZAR document {i}.", f"p-h{i}") for i in range(1, 4)],
    )


@pytest.fixture
def setup_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    path = tmp_path / "extension with space.duckdb_extension"
    path.write_bytes(b"synthetic extension")
    con = Connection()
    factory_calls: list[tuple[Any, Any]] = []

    def factory(*args: Any, **kwargs: Any) -> Connection:
        factory_calls.append((args, kwargs))
        return con

    engine = jevdb.JevdbEngine(
        extension_path=path,
        model_id="jev-1.14.0",
        secret_provider=lambda: KEY,
        connection_factory=factory,
        endpoint="https://gateway.example/v1/systemone",
    )
    yield engine, con, factory_calls
    con.release.set()
    engine.close()


def pairs(inputs: tuple[list[ThesisInput], list[PassageInput]]) -> list[PairInput]:
    th, ps = inputs
    return [PairInput(th[0], ps[0]), PairInput(th[1], ps[1]), PairInput(th[0], ps[1])]


def test_score_pairs_returns_one_pairscore_per_requested_pair(
    setup_engine: Any, inputs: Any
) -> None:
    engine, con, _ = setup_engine
    requested = pairs(inputs)
    scores = engine.score_pairs("ZZAR", requested, Token())
    assert isinstance(engine, SemanticEngine)
    assert len(scores) == 3
    assert [(s.thesis_id, s.version, s.passage_id) for s in scores] == [
        (p.thesis.thesis_id, p.thesis.version, p.passage.passage_id) for p in requested
    ]
    assert all(s.tokens_estimated and s.model_id == "jev-1.14.0" for s in scores)
    assert len({s.latency_ms for s in scores}) == 1
    assert scores[1].probabilities.kill_met is None
    assert len(con.calls) == 14


def test_score_event_wraps_full_cartesian_product(setup_engine: Any, inputs: Any) -> None:
    engine, _, _ = setup_engine
    th, ps = inputs
    result = engine.score_event("ZZAR", th, ps, Token())
    assert [(s.thesis_id, s.passage_id) for s in result] == [
        (t.thesis_id, p.passage_id) for t in th for p in ps
    ]


def test_score_pairs_sql_joins_wanted_pairs(setup_engine: Any, inputs: Any) -> None:
    engine, con, _ = setup_engine
    engine.score_pairs("ZZAR", pairs(inputs), Token())
    sql = next(s for s, _ in con.statements if "jev_probability(" in s)
    assert "AS MATERIALIZED" in sql and "JOIN wanted_" in sql
    allowed = {(p.thesis.statement, p.passage.text) for p in pairs(inputs)}
    assert {(a["thesis"], b["document"]) for _, a, b in con.calls} == allowed
    assert len(con.calls) == 14


def test_score_sql_contains_no_user_text(setup_engine: Any, inputs: Any) -> None:
    engine, con, _ = setup_engine
    malicious = "'; DROP TABLE x; -- 中文🚀"
    thesis = ThesisInput("t1", "id", 1, malicious, malicious, "h")
    passage = PassageInput("pid", malicious, "h")
    engine.score_pairs(malicious, [PairInput(thesis, passage)], Token())
    assert all(malicious not in sql for sql, _ in con.statements)
    assert any(malicious in repr(parameters) for _, parameters in con.statements)
    assert con.db.execute("SELECT count(*) FROM duckdb_tables() WHERE temporary").fetchone()[0] == 0


def test_score_sql_uses_kill_met_struct_separately(setup_engine: Any, inputs: Any) -> None:
    engine, con, _ = setup_engine
    engine.score_pairs("ZZAR", pairs(inputs), Token())
    for question, left, _ in con.calls:
        assert ("kill_condition" in left) == ("condition in `kill_condition`" in question)
        assert "theses." not in question and "{id}" not in question
    templates = build_score_questions(inputs[0], flavor="jevdb")
    assert {q for q, _, _ in con.calls} == {s.instructions for s in templates.values()}


def test_score_pairs_treats_null_probability_as_model_error(setup_engine: Any, inputs: Any) -> None:
    engine, con, _ = setup_engine
    con.override = [("t1", "p1", 0.9, None, 0.1, 0.2, 0.3)]
    with pytest.raises(EngineError) as error:
        engine.score_pairs("ZZAR", [pairs(inputs)[0]], Token())
    assert error.value.code == ErrorCode.MODEL_ERROR


def test_missing_extension_raises_engine_unavailable(tmp_path: Path) -> None:
    called: list[Any] = []

    def factory(*args: Any, **kwargs: Any) -> Connection:
        called.append(args)
        raise AssertionError("missing path must not open a connection")

    engine = jevdb.JevdbEngine(
        extension_path=tmp_path / "missing.duckdb_extension",
        model_id="jev-1.14.0",
        secret_provider=lambda: KEY,
        connection_factory=factory,
    )
    with pytest.raises(EngineError) as error:
        engine.load()
    assert error.value.code == ErrorCode.ENGINE_UNAVAILABLE and not called


def test_auth_401_and_429_errors_are_distinct() -> None:
    auth = jevdb.map_jevdb_error((FIXTURES / "error_auth.txt").read_text())
    limited = jevdb.map_jevdb_error((FIXTURES / "error_rate_limit.txt").read_text())
    assert auth.code == ErrorCode.UNAUTHENTICATED and auth.reason == "INVALID_KEY"
    assert auth.retryable is False
    assert limited.code == ErrorCode.RATE_LIMITED and limited.params["retryAfterSec"] == 30
    assert "30" in str(limited.to_wire()["message"])


def test_evidence_probabilities_follow_sentence_order(setup_engine: Any, inputs: Any) -> None:
    engine, con, _ = setup_engine
    fixture = json.loads((FIXTURES / "evidence_rows.json").read_text())
    con.override = [tuple(r) for r in reversed(fixture["rows"])]
    result = engine.locate_evidence(inputs[0][0], "overturn", ["a", "b", "c", "d"], Token())
    assert isinstance(result, EvidenceScore) and result.tokens_estimated
    assert result.sentence_probabilities == [0.05, 0.91, 0.34, 0.02]


def test_cancel_calls_interrupt_and_raises_cancelled(setup_engine: Any, inputs: Any) -> None:
    engine, con, _ = setup_engine
    con.block = True
    token = Token()

    def cancel_when_entered() -> None:
        con.entered.wait(2)
        token.event.set()

    timer = threading.Thread(target=cancel_when_entered)
    timer.start()
    with pytest.raises(CancelledError):
        engine.score_pairs("ZZAR", pairs(inputs), token)
    timer.join(2)
    engine.close()
    assert con.interrupts == 1 and con.closed == 1 and not con.secret


def test_temp_tables_are_dropped_on_failure(setup_engine: Any, inputs: Any) -> None:
    engine, con, _ = setup_engine
    con.failure = "HTTP 503 synthetic error"
    with pytest.raises(EngineError):
        engine.score_pairs("ZZAR", pairs(inputs), Token())
    assert sum(s.startswith("DROP TABLE IF EXISTS") for s, _ in con.statements) == 3
    assert con.db.execute("SELECT count(*) FROM duckdb_tables() WHERE temporary").fetchone()[0] == 0
    assert not con.secret


def test_repeated_close_is_idempotent(setup_engine: Any) -> None:
    engine, con, calls = setup_engine
    engine.load()
    engine.load()
    engine.close()
    engine.close()
    assert len(calls) == con.closed == 1


@pytest.mark.parametrize("bad", [None, -0.1, 1.1, float("nan"), float("inf"), True, "0.5"])
@pytest.mark.parametrize("column", [2, 3, 4, 6])
def test_invalid_score_probabilities_fail_whole_batch(
    setup_engine: Any, inputs: Any, bad: Any, column: int
) -> None:
    engine, con, _ = setup_engine
    row: list[Any] = ["t1", "p1", 0.9, 0.8, 0.7, 0.8, 0.1]
    row[column] = bad
    con.override = [tuple(row)]
    with pytest.raises(EngineError, match="MODEL_ERROR"):
        engine.score_pairs("ZZAR", [pairs(inputs)[0]], Token())


@pytest.mark.parametrize("rows", [[], [("t9", "p9", 0.9, 0.8, 0.7, 0.8, 0.1)], [("t1", "p1")]])
def test_missing_extra_and_malformed_rows_fail(setup_engine: Any, inputs: Any, rows: Any) -> None:
    engine, con, _ = setup_engine
    con.override = rows
    with pytest.raises(EngineError, match="MODEL_ERROR"):
        engine.score_pairs("ZZAR", [pairs(inputs)[0]], Token())


def test_duplicate_rows_fail_but_duplicate_requested_pairs_preserve_count(
    setup_engine: Any, inputs: Any
) -> None:
    engine, con, _ = setup_engine
    pair = pairs(inputs)[0]
    assert len(engine.score_pairs("ZZAR", [pair, pair], Token())) == 2
    assert len(con.calls) == 5
    con.override = [("t1", "p1", 0.9, 0.8, 0.7, 0.8, 0.1)] * 2
    with pytest.raises(EngineError, match="MODEL_ERROR"):
        engine.score_pairs("ZZAR", [pair], Token())


def test_token_estimates_count_actual_question_instructions(setup_engine: Any, inputs: Any) -> None:
    engine, _, _ = setup_engine
    requested = pairs(inputs)
    scores = engine.score_pairs("ZZAR", requested, Token())
    for pair, score in zip(requested, scores, strict=True):
        th, ps = pair.thesis, pair.passage
        questions = build_score_questions([th], flavor="jevdb")
        chars = len(th.statement) + len(th.kill_condition or "") + len(ps.text)
        assert score.input_tokens == estimate_tokens(
            chars + sum(len(q.instructions) for q in questions.values())
        )


@pytest.mark.parametrize("suffix", ["", "a" * 21, "UPPER", "a;drop", "a-b", "'", "中文"])
def test_sql_suffix_validation(suffix: str, inputs: Any) -> None:
    for builder, questions in [
        (jevdb.build_score_sql, build_score_questions(inputs[0], flavor="jevdb")),
        (
            jevdb.build_evidence_sql,
            build_evidence_questions("weaken", 1, has_kill=False, flavor="jevdb"),
        ),
    ]:
        with pytest.raises(ValueError):
            builder(questions, suffix)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://gateway.example/v1/systemone",
        "https://user:secret@gateway.example/v1/systemone",
        "https://gateway.example/v1/systemone?",
        "https://gateway.example/v1/systemone#",
        "https://gateway.example/v1/",
        "https://gateway.example:0/v1/systemone",
        "https://gateway.example:/v1/systemone",
        "https://bad_host/v1/systemone",
        "https://gateway.example/\nv1/systemone",
    ],
)
def test_endpoint_rejects_unsafe_values(setup_engine: Any, endpoint: str) -> None:
    engine, _, _ = setup_engine
    with pytest.raises(ValueError, match="invalid JEV endpoint"):
        jevdb.JevdbEngine(
            extension_path=engine.extension_path,
            model_id="jev-1.14.0",
            secret_provider=lambda: KEY,
            endpoint=endpoint,
        )


def test_settings_endpoint_env_restoration_and_secret_lifetime(
    setup_engine: Any, inputs: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, con, calls = setup_engine
    monkeypatch.setenv("JEV_API_KEY", "unrelated-parent-key")
    snapshot = dict(os.environ)
    engine.load()
    assert not con.secret
    engine.score_pairs("ZZAR", pairs(inputs), Token())
    assert dict(os.environ) == snapshot
    assert con.env_keys == [KEY] and not con.secret
    assert calls == [((":memory:",), {"config": {"allow_unsigned_extensions": "true"}})]
    assert ("SET jevdb_endpoint = ?", ["https://gateway.example/v1/"]) in con.statements
    assert ("SET jevdb_model = ?", ["jev-1.14.0"]) in con.statements
    assert all(KEY not in sql for sql, _ in con.statements)


def test_unconfigured_engine_constructs_loads_but_cannot_score(
    setup_engine: Any, inputs: Any
) -> None:
    engine, con, _ = setup_engine
    engine.secret_provider = lambda: ""
    assert engine.health().state == "unconfigured"
    engine.load()
    with pytest.raises(UserError) as error:
        engine.score_pairs("ZZAR", pairs(inputs), Token())
    assert error.value.code == ErrorCode.CONFIG_REQUIRED
    assert error.value.params == {"missing": ["jevKey"]}
    assert not con.calls and not con.secret
    assert engine.health().state == "unconfigured"


def test_current_key_is_consumed_on_each_score(setup_engine: Any, inputs: Any) -> None:
    engine, con, _ = setup_engine
    keys = iter([KEY, "new-test-key"])
    engine.secret_provider = lambda: next(keys)
    engine.score_pairs("ZZAR", pairs(inputs), Token())
    engine.score_pairs("ZZAR", pairs(inputs), Token())
    assert con.env_keys == [KEY, "new-test-key"] and not con.secret


def test_offline_blocks_before_model_query(
    setup_engine: Any, inputs: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, con, _ = setup_engine
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    with pytest.raises(SourceError) as error:
        engine.score_pairs("ZZAR", pairs(inputs), Token())
    assert error.value.code == ErrorCode.SOURCE_UNAVAILABLE
    assert not con.calls and not con.secret


def test_stats_are_numeric_only_and_failure_is_nonfatal(
    setup_engine: Any, inputs: Any, caplog: pytest.LogCaptureFixture
) -> None:
    engine, con, _ = setup_engine
    caplog.set_level("DEBUG")
    assert len(engine.score_pairs("ZZAR", pairs(inputs), Token())) == 3
    assert "requests" in caplog.text and KEY not in caplog.text
    con.stats_failure = True
    assert len(engine.score_pairs("ZZAR", pairs(inputs), Token())) == 3
    assert KEY not in caplog.text


@pytest.mark.parametrize(
    "message,code,reason",
    [
        ("HTTP 401 synthetic", ErrorCode.UNAUTHENTICATED, "INVALID_KEY"),
        ("HTTP 403 synthetic", ErrorCode.UNAUTHENTICATED, "FORBIDDEN"),
        ("HTTP 429 Retry-After: 12", ErrorCode.RATE_LIMITED, None),
        ("timed out", ErrorCode.TIMEOUT, None),
        ("HTTP 503 synthetic", ErrorCode.MODEL_ERROR, None),
    ],
)
def test_query_error_mapping(
    setup_engine: Any, inputs: Any, message: str, code: ErrorCode, reason: str | None
) -> None:
    engine, con, _ = setup_engine
    con.failure = message + " " + KEY
    with pytest.raises(EngineError) as error:
        engine.score_pairs("ZZAR", pairs(inputs), Token())
    assert error.value.code == code and error.value.reason == reason
    assert KEY not in repr(error.value.to_wire())
    if code == ErrorCode.RATE_LIMITED:
        assert error.value.params["retryAfterSec"] == 12


@pytest.mark.parametrize(
    "stage",
    ["LOAD", "SET jevdb_model", "CREATE TEMP TABLE ps_", "INSERT INTO ps_", "CREATE SECRET"],
)
def test_setup_failures_cleanup_and_redact(setup_engine: Any, inputs: Any, stage: str) -> None:
    engine, con, _ = setup_engine
    con.fail_prefix = stage
    with pytest.raises(EngineError) as error:
        engine.score_pairs("ZZAR", pairs(inputs), Token())
    assert KEY not in repr(error.value.to_wire())
    assert not con.secret
    if stage.startswith(("LOAD", "SET")):
        assert con.closed == 1
        assert error.value.code == ErrorCode.ENGINE_UNAVAILABLE
    else:
        assert (
            con.db.execute("SELECT count(*) FROM duckdb_tables() WHERE temporary").fetchone()[0]
            == 0
        )


def test_deadline_retains_slot_until_uninterruptible_query_finishes(
    setup_engine: Any, inputs: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, con, _ = setup_engine
    monkeypatch.setattr(jevdb, "JEVDB_TIMEOUT_SEC", 0.1)
    con.block = con.ignore_interrupt = True
    started = time.monotonic()
    with pytest.raises(EngineError, match="TIMEOUT"):
        engine.score_pairs("ZZAR", pairs(inputs), Token())
    assert time.monotonic() - started < 0.5
    count = len(con.statements)
    with pytest.raises(EngineError, match="TIMEOUT"):
        engine.score_pairs("ZZAR", pairs(inputs), Token())
    assert len(con.statements) == count and con.interrupts == 1
    con.block = False
    con.release.set()
    engine.close()
    assert con.closed == 1 and not con.secret


def test_cancelled_lock_wait_does_not_interrupt_other_call(setup_engine: Any, inputs: Any) -> None:
    engine, con, _ = setup_engine
    con.block = True
    outcomes: list[Any] = []
    thread = threading.Thread(
        target=lambda: outcomes.append(engine.score_pairs("ZZAR", pairs(inputs), Token()))
    )
    thread.start()
    assert con.entered.wait(2)
    token = Token()
    token.event.set()
    with pytest.raises(CancelledError):
        engine.score_pairs("ZZAR", pairs(inputs), token)
    assert con.interrupts == 0
    con.release.set()
    thread.join(2)
    assert len(outcomes) == 1


@pytest.mark.parametrize(
    "relation,kill",
    [("overturn", True), ("overturn", False), ("weaken", True), ("uncertain", False)],
)
def test_evidence_uses_complete_independent_template(
    setup_engine: Any, inputs: Any, relation: Any, kill: bool
) -> None:
    engine, con, _ = setup_engine
    thesis = inputs[0][0 if kill else 1]
    result = engine.locate_evidence(
        thesis, relation, ["ZZAR sentence one.", "ZZAR sentence two."], Token()
    )
    template = build_evidence_questions(relation, 2, has_kill=kill, flavor="jevdb")
    assert len(result.sentence_probabilities) == 2
    assert {q for q, _, _ in con.calls} == {q.instructions for q in template.values()}
    assert all(
        ("kill_condition" in a) == (kill and relation == "overturn") for _, a, _ in con.calls
    )
    assert not con.secret


def test_evidence_failure_drops_table(setup_engine: Any, inputs: Any) -> None:
    engine, con, _ = setup_engine
    con.failure = "HTTP 503 synthetic"
    with pytest.raises(EngineError):
        engine.locate_evidence(inputs[0][0], "weaken", ["a"], Token())
    assert sum(s.startswith("DROP TABLE IF EXISTS ev_") for s, _ in con.statements) == 1
    assert not con.secret


def test_score_fixture_is_explicitly_synthetic(setup_engine: Any, inputs: Any) -> None:
    engine, con, _ = setup_engine
    fixture = json.loads((FIXTURES / "score_rows.json").read_text())
    assert fixture["source"] == "synthetic; not a model recording"
    con.override = [tuple(r) for r in fixture["rows"]]
    result = engine.score_event("ZZAR", *inputs, Token())
    assert len(result) == 6


@pytest.mark.parametrize(
    "name", ["relative", "quote'", 'quote"', "newline\n", "wrong.bin", "directory"]
)
def test_invalid_extension_paths_never_open_connections(tmp_path: Path, name: str) -> None:
    path = tmp_path / (name if name in ("wrong.bin", "directory") else name + ".duckdb_extension")
    if name == "directory":
        path.mkdir()
    else:
        path.write_bytes(b"synthetic")
    if name == "relative":
        path = Path(path.name)

    def factory(*a: Any, **k: Any) -> Connection:
        raise AssertionError("invalid path opened connection")

    engine = jevdb.JevdbEngine(
        extension_path=path,
        model_id="jev-1.14.0",
        secret_provider=lambda: KEY,
        connection_factory=factory,
    )
    with pytest.raises(EngineError, match="ENGINE_UNAVAILABLE"):
        engine.load()
    engine.close()


def test_wrong_duckdb_version_is_loading_error(
    setup_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _, calls = setup_engine
    monkeypatch.setattr(duckdb, "__version__", "1.4.2")
    with pytest.raises(EngineError, match="ENGINE_UNAVAILABLE"):
        engine.load()
    assert not calls


@pytest.mark.parametrize("model", ["jev-latest", "jev-1.14", "jev-１.14.0", "jev-1.14.0';--"])
def test_fixed_model_validation(setup_engine: Any, model: str) -> None:
    engine, _, _ = setup_engine
    with pytest.raises(ValueError):
        jevdb.JevdbEngine(
            extension_path=engine.extension_path, model_id=model, secret_provider=lambda: KEY
        )


@pytest.mark.parametrize("bad_key", ["", " ", "test key", "test\nkey", "非ascii", None])
def test_invalid_keys_are_unconfigured_without_requests(
    setup_engine: Any, inputs: Any, bad_key: Any
) -> None:
    engine, con, _ = setup_engine
    engine.secret_provider = lambda: bad_key
    assert engine.health().state == "unconfigured"
    with pytest.raises(UserError, match="CONFIG_REQUIRED"):
        engine.score_pairs("ZZAR", pairs(inputs), Token())
    assert not con.calls and not con.secret


def test_provider_exception_is_sanitized_in_health_and_score(
    setup_engine: Any, inputs: Any
) -> None:
    engine, _, _ = setup_engine

    def provider() -> str:
        raise RuntimeError(KEY)

    engine.secret_provider = provider
    for invoke in (engine.health, lambda: engine.score_pairs("ZZAR", pairs(inputs), Token())):
        with pytest.raises(InternalError) as error:
            invoke()
        assert error.value.reason == "SECRET_PROVIDER_FAILED"
        assert KEY not in repr(error.value.to_wire("provider-request"))
        assert error.value.__context__ is None


def test_empty_and_precancelled_inputs_never_open_connection(
    setup_engine: Any, inputs: Any
) -> None:
    engine, _, calls = setup_engine
    assert engine.score_pairs("ZZAR", [], Token()) == []
    token = Token()
    token.event.set()
    with pytest.raises(CancelledError):
        engine.score_pairs("ZZAR", pairs(inputs), token)
    assert not calls


def test_conflicting_thesis_and_passage_identity_fail_before_query(
    setup_engine: Any, inputs: Any
) -> None:
    engine, _, calls = setup_engine
    pair = pairs(inputs)[0]
    other = ThesisInput("t1", "different-id", 2, "ZZAR other thesis", None, "hash")
    for bad in [
        PairInput(other, pair.passage),
        PairInput(pair.thesis, PassageInput("p1", "other", "h")),
    ]:
        with pytest.raises(ValueError, match="conflicting input identity"):
            engine.score_pairs("ZZAR", [pair, bad], Token())
    assert not calls


@pytest.mark.parametrize(
    "rows", [[], [("s1", None)], [("s1", 1.1)], [("s1", 0.1)] * 2, [("s9", 0.1)], [("s1",)]]
)
def test_evidence_incomplete_duplicate_or_invalid_rows_fail(
    setup_engine: Any, inputs: Any, rows: Any
) -> None:
    engine, con, _ = setup_engine
    con.override = rows
    with pytest.raises(EngineError, match="MODEL_ERROR"):
        engine.locate_evidence(inputs[0][0], "weaken", ["a"], Token())
    assert not con.secret


@pytest.mark.parametrize(
    "sentences,relation",
    [
        ([], "weaken"),
        (["a"] * 41, "weaken"),
        ([" "], "weaken"),
        (["a" * 1201], "weaken"),
        (["a"], "support"),
    ],
)
def test_invalid_evidence_input_never_opens_connection(
    setup_engine: Any, inputs: Any, sentences: Any, relation: Any
) -> None:
    engine, _, calls = setup_engine
    with pytest.raises(ValueError):
        engine.locate_evidence(inputs[0][0], relation, sentences, Token())
    assert not calls


def test_cleanup_failure_disposes_connection(setup_engine: Any, inputs: Any) -> None:
    engine, con, _ = setup_engine
    con.fail_prefix = "DROP TABLE IF EXISTS ps_"
    with pytest.raises(EngineError) as error:
        engine.score_pairs("ZZAR", pairs(inputs), Token())
    assert error.value.reason == "CLEANUP_FAILED" and con.closed == 1
    assert not con.secret and engine._connection is None
    assert sum(s.startswith("DROP TABLE IF EXISTS") for s, _ in con.statements) == 3


def test_offline_switch_during_setup_blocks_query(
    setup_engine: Any, inputs: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, con, _ = setup_engine
    assert isinstance(con, Connection)
    original = con.executemany

    def insert(sql: str, values: Any) -> Connection:
        result = original(sql, values)
        monkeypatch.setenv("SENTINEL_OFFLINE", "1")
        return result

    monkeypatch.setattr(con, "executemany", insert)
    with pytest.raises(SourceError):
        engine.score_pairs("ZZAR", pairs(inputs), Token())
    assert not con.calls and not con.secret


def test_query_can_reuse_connection_only_after_late_cleanup(
    setup_engine: Any, inputs: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, con, calls = setup_engine
    monkeypatch.setattr(jevdb, "JEVDB_TIMEOUT_SEC", 0.08)
    con.block = con.ignore_interrupt = True
    with pytest.raises(EngineError, match="TIMEOUT"):
        engine.score_pairs("ZZAR", pairs(inputs), Token())
    assert engine._job is not None and not engine._job.done.is_set()
    con.release.set()
    assert engine._job.done.wait(2)
    assert not con.secret
    con.block = False
    monkeypatch.setattr(jevdb, "JEVDB_TIMEOUT_SEC", 60)
    assert len(engine.score_pairs("ZZAR", pairs(inputs), Token())) == 3
    assert len(calls) == 1


def test_secret_environment_is_restored_when_creation_fails(
    setup_engine: Any, inputs: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, con, _ = setup_engine
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    con.fail_prefix = "CREATE SECRET"
    before = dict(os.environ)
    with pytest.raises(EngineError):
        engine.score_pairs("ZZAR", pairs(inputs), Token())
    assert dict(os.environ) == before and not con.secret


def test_close_defers_disposal_of_uninterruptible_query(
    setup_engine: Any, inputs: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, con, _ = setup_engine
    monkeypatch.setattr(jevdb, "JEVDB_TIMEOUT_SEC", 0.08)
    con.block = con.ignore_interrupt = True
    with pytest.raises(EngineError, match="TIMEOUT"):
        engine.score_pairs("ZZAR", pairs(inputs), Token())
    engine.close()
    assert con.closed == 0
    con.release.set()
    assert engine._job is not None and engine._job.done.wait(2)
    assert con.closed == 1
    with pytest.raises(EngineError, match="ENGINE_UNAVAILABLE"):
        engine.score_pairs("ZZAR", pairs(inputs), Token())


def test_cancel_while_env_lock_waiting_never_creates_secret(setup_engine: Any, inputs: Any) -> None:
    engine, con, _ = setup_engine
    token = Token()
    outcome: list[BaseException] = []

    def score() -> None:
        try:
            engine.score_pairs("ZZAR", pairs(inputs), token)
        except BaseException as error:
            outcome.append(error)

    with jevdb._ENV_LOCK:
        thread = threading.Thread(target=score)
        thread.start()
        token.event.set()
        thread.join(2)
    assert len(outcome) == 1 and isinstance(outcome[0], CancelledError)
    engine.close()
    assert not con.env_keys and not con.calls


def test_stored_error_has_no_raw_exception_context(setup_engine: Any, inputs: Any) -> None:
    engine, con, _ = setup_engine
    con.failure = "HTTP 401 body contains " + KEY
    with pytest.raises(EngineError):
        engine.score_pairs("ZZAR", pairs(inputs), Token())
    assert engine._job is not None and engine._job.error is not None
    assert engine._job.error.__context__ is None
    assert engine._job.error.__cause__ is None


@pytest.mark.parametrize("status", [400, 413, 422])
def test_invalid_request_mapper_returns_internal_without_remote_body(status: int) -> None:
    error = jevdb.map_jevdb_error(f"Jev HTTP {status}; synthetic invalid timeout option {KEY}")
    assert isinstance(error, InternalError)
    assert error.code == ErrorCode.INTERNAL and error.reason == "INVALID_REQUEST"
    assert error.retryable is True
    assert KEY not in repr(error.to_wire("invalid-request"))
    assert error.__context__ is error.__cause__ is None


@pytest.mark.parametrize("status", [400, 413, 422])
@pytest.mark.parametrize("operation", ["score", "evidence"])
def test_invalid_request_propagates_internal_and_cleans_up(
    setup_engine: Any, inputs: Any, status: int, operation: str
) -> None:
    engine, con, _ = setup_engine
    con.failure = f"HTTP {status} synthetic invalid request {KEY}"
    with pytest.raises(InternalError) as error:
        if operation == "score":
            engine.score_pairs("ZZAR", pairs(inputs), Token())
        else:
            engine.locate_evidence(inputs[0][0], "weaken", ["ZZAR sentence"], Token())
    assert error.value.reason == "INVALID_REQUEST"
    assert KEY not in repr(error.value.to_wire("invalid-request"))
    assert error.value.__context__ is error.value.__cause__ is None
    assert not con.secret
    assert con.db.execute("SELECT count(*) FROM duckdb_tables() WHERE temporary").fetchone()[0] == 0


@pytest.mark.parametrize("operation", ["health", "score", "evidence"])
def test_secrets_service_keyring_failure_keeps_internal_code(
    setup_engine: Any, inputs: Any, operation: str
) -> None:
    engine, con, _ = setup_engine

    class BrokenStore:
        def get(self, account: str) -> str | None:
            raise RuntimeError("synthetic private keyring failure " + KEY)

        def set(self, account: str, value: str) -> None:
            raise AssertionError("unexpected key write")

        def delete(self, account: str) -> None:
            raise AssertionError("unexpected key delete")

    from sentinel import clock

    service = SecretsService(BrokenStore(), clock.now)
    engine.secret_provider = lambda: service.get_jev_key() or ""
    with pytest.raises(InternalError) as error:
        if operation == "health":
            engine.health()
        elif operation == "score":
            engine.score_pairs("ZZAR", pairs(inputs), Token())
        else:
            engine.locate_evidence(inputs[0][0], "weaken", ["ZZAR sentence"], Token())
    assert error.value.code == ErrorCode.INTERNAL
    assert error.value.message_key == "settings.keyring_unavailable"
    assert "钥匙串" in str(error.value.to_wire("keyring-request")["message"])
    assert "missing" not in error.value.params
    assert KEY not in repr(error.value.to_wire("keyring-request"))
    assert error.value.__context__ is error.value.__cause__ is None
    assert not con.calls and not con.secret


@pytest.mark.parametrize("operation", ["health", "score", "evidence"])
def test_pure_provider_key_is_registered_for_remote_error_logging(
    setup_engine: Any, inputs: Any, operation: str
) -> None:
    engine, con, _ = setup_engine
    key = "s04-pure-provider-key-do-not-use"
    clear_secrets()
    try:
        assert redact_text(key) == key
        engine.secret_provider = lambda: key
        con.failure = "HTTP 401 synthetic remote body " + key
        if operation == "health":
            assert engine.health().state == "ok"
        else:
            with pytest.raises(EngineError) as error:
                if operation == "score":
                    engine.score_pairs("ZZAR", pairs(inputs), Token())
                else:
                    engine.locate_evidence(inputs[0][0], "weaken", ["ZZAR sentence"], Token())
            assert key not in "".join(traceback.format_exception(error.value))
        assert redact_text(key) == MASK
        record = logging.LogRecord(
            "sentinel.semantic.engines.jevdb",
            logging.ERROR,
            __file__,
            1,
            "synthetic remote error context %s",
            (key,),
            None,
        )
        formatted = JsonFormatter().format(record)
        assert key not in formatted and MASK in formatted
        assert not con.secret
    finally:
        clear_secrets()


@pytest.mark.parametrize("operation", ["health", "score"])
def test_provider_sentinel_error_metadata_is_sanitized(
    setup_engine: Any, inputs: Any, operation: str
) -> None:
    engine, _, _ = setup_engine
    key = "s04-provider-metadata-key-do-not-use"
    clear_secrets()
    try:
        engine.secret_provider = lambda: key
        assert engine.health().state == "ok"

        def provider() -> str:
            raise InternalError(
                message_key="settings.keyring_unavailable",
                reason="KEYRING_UNAVAILABLE",
                detail="synthetic provider body " + key,
                params={"diagnostic": key, "operation": "read", "token": key},
            )

        engine.secret_provider = provider
        with pytest.raises(InternalError) as error:
            if operation == "health":
                engine.health()
            else:
                engine.score_pairs("ZZAR", pairs(inputs), Token())
        assert error.value.reason == "KEYRING_UNAVAILABLE"
        wire = error.value.to_wire("provider-request")
        assert key not in repr(wire)
        assert key not in "".join(traceback.format_exception(error.value))
        assert error.value.__context__ is error.value.__cause__ is None
    finally:
        clear_secrets()


def test_native_close_has_bounded_wait(setup_engine: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    engine, con, _ = setup_engine
    engine.load()
    assert isinstance(con, Connection)
    original = con.close
    release = threading.Event()

    def slow_close() -> None:
        assert release.wait(2)
        original()

    monkeypatch.setattr(con, "close", slow_close)
    monkeypatch.setattr(jevdb, "JEVDB_TIMEOUT_SEC", 0.05)
    timer = threading.Timer(0.4, release.set)
    timer.start()
    started = time.monotonic()
    engine.close()
    elapsed = time.monotonic() - started
    timer.join(1)
    assert elapsed < 0.2
    assert engine._job is not None and engine._job.done.wait(1)
    assert con.closed == 1


def test_real_static_load_null_sql_binding_and_zero_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = os.environ.get("SENTINEL_JEVDB_TEST_EXTENSION")
    if path is None:
        pytest.skip("explicit verified static artifact required")
    extension = Path(path)
    assert (
        hashlib.sha256(extension.read_bytes()).hexdigest()
        == "d9f3f1d613847900436af87422f0cc7c3e8e9268934559f207433e6e6d3ffd9a"
    )
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    engine = jevdb.JevdbEngine(
        extension_path=extension,
        model_id="jev-1.14.0",
        secret_provider=lambda: "",
        endpoint="https://gateway.example/v1/systemone",
    )
    engine.load()
    con = engine._connection
    assert con is not None
    assert con.execute(
        "SELECT jev_keys_overlap(['batch'],['batch']), "
        "jev_keys_overlap([],['batch']), jev_keys_overlap(NULL,['batch'])"
    ).fetchone() == (True, False, True)
    th = ThesisInput("t1", "th", 1, "ZZAR thesis", "ZZAR kill", "h")
    for sql in [
        "CREATE TEMP TABLE th_probe"
        "(ref VARCHAR,thesis VARCHAR,kill_condition VARCHAR,keys VARCHAR[])",
        "CREATE TEMP TABLE ps_probe(pid VARCHAR,document VARCHAR,keys VARCHAR[])",
        "CREATE TEMP TABLE wanted_probe(ref VARCHAR,pid VARCHAR)",
        "INSERT INTO th_probe VALUES ('t1',NULL,NULL,['batch'])",
        "INSERT INTO ps_probe VALUES ('p1','ZZAR document',['batch'])",
        "INSERT INTO wanted_probe VALUES ('t1','p1')",
    ]:
        con.execute(sql)
    row = con.execute(
        jevdb.build_score_sql(build_score_questions([th], flavor="jevdb"), "probe")
    ).fetchone()
    assert row == ("t1", "p1", None, None, None, None, None)
    con.execute(
        "CREATE TEMP TABLE ev_probe"
        "(sid VARCHAR,sentence VARCHAR,thesis VARCHAR,kill_condition VARCHAR)"
    )
    con.execute("INSERT INTO ev_probe VALUES ('s1','ZZAR sentence',NULL,NULL)")
    q = build_evidence_questions("overturn", 1, has_kill=True, flavor="jevdb")
    assert con.execute(jevdb.build_evidence_sql(q, "probe")).fetchone() == ("s1", None)
    for table in ["th", "ps", "wanted", "ev"]:
        con.execute(f"DROP TABLE {table}_probe")
    result = con.execute("SELECT * FROM jevdb_stats()")
    stats_row = result.fetchone()
    assert stats_row is not None
    stats = dict(zip([d[0] for d in result.description], stats_row, strict=True))
    assert len(stats) == 32
    assert stats["requests"] == stats["retries"] == stats["input_tokens"] == stats["errors"] == 0
    assert con.execute("SELECT current_setting('jevdb_endpoint')").fetchone() == (
        "https://gateway.example/v1/",
    )
    assert con.execute("SELECT count(*) FROM duckdb_secrets()").fetchone() == (0,)
    engine.secret_provider = lambda: KEY
    before = dict(os.environ)
    monkeypatch.setenv("SENTINEL_OFFLINE", "0")
    engine._secret(con, Token(), threading.Event(), time.monotonic() + 5)
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    assert dict(os.environ) == before
    assert con.execute("SELECT persistent FROM duckdb_secrets()").fetchone() == (False,)
    engine._cleanup(con, [])
    assert con.execute("SELECT count(*) FROM duckdb_secrets()").fetchone() == (0,)
    monkeypatch.setattr(jevdb, "JEVDB_TIMEOUT_SEC", 0.05)

    def cpu_query(stop: threading.Event, deadline: float) -> None:
        con.execute("SELECT sum(i::HUGEINT) FROM range(10000000000) r(i)")

    with pytest.raises(EngineError, match="TIMEOUT"):
        engine._run(cpu_query)
    assert engine._job is not None and engine._job.done.wait(2)
    assert con.execute("SELECT 42").fetchone() == (42,)
    monkeypatch.setattr(jevdb, "JEVDB_TIMEOUT_SEC", 60)
    engine.close()
