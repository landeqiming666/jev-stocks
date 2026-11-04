from __future__ import annotations

import importlib
import json
import logging
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from email.utils import format_datetime
from pathlib import Path
from typing import Any, cast

import httpx2
import pytest
import typesafe_sdk as sdk

from sentinel.errors import (
    CancelledError,
    EngineError,
    ErrorCode,
    InternalError,
    SourceError,
    UserError,
)
from sentinel.semantic.base import PairInput, PassageInput, SemanticEngine, ThesisInput

MODEL = "jev-1.14.0"
KEY = "test-key-do-not-use"
FIXTURES = Path(__file__).parents[2] / "fixtures" / "jev_direct"


def direct() -> Any:
    return importlib.import_module("sentinel.semantic.engines.jev_direct")


class Token:
    def __init__(self) -> None:
        self.event = threading.Event()

    def is_cancelled(self) -> bool:
        return self.event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise CancelledError()


def thesis(i: int = 1, *, kill: bool = False) -> ThesisInput:
    return ThesisInput(
        f"t{i}",
        f"thesis-{i}",
        1,
        "ZZAR keeps R&D spending high.",
        "R&D spending falls." if kill else None,
        f"hash-{i}",
    )


def passage(i: int = 1) -> PassageInput:
    return PassageInput(f"p{i}", f"ZZAR disclosure paragraph {i}.", f"passage-hash-{i}")


class Client:
    def __init__(self, handler: Callable[..., Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.handler = handler
        self.lock = threading.Lock()

    def call(self, **kwargs: Any) -> Any:
        with self.lock:
            self.calls.append(kwargs)
        if self.handler:
            return self.handler(**kwargs)
        return direct().SystemOneResponse(MODEL, {name: 0.2 for name in kwargs["questions"]}, 11, 3)


def engine(client: Client, **kwargs: Any) -> Any:
    return direct().JevDirectEngine(
        api_key=KEY, model_id=MODEL, client_factory=lambda key: client, **kwargs
    )


def test_score_pairs_packs_only_requested_pairs() -> None:
    client = Client()
    t1, t2, p1, p2 = thesis(), thesis(2), passage(), passage(2)
    pairs = [PairInput(t2, p2), PairInput(t1, p1), PairInput(t2, p1)]
    scores = engine(client).score_pairs("ZZAR", pairs, Token())
    assert [(s.thesis_id, s.passage_id) for s in scores] == [
        (p.thesis.thesis_id, p.passage.passage_id) for p in pairs
    ]
    assert len(client.calls) == 2
    states = {c["state"]["document"]: c["state"]["theses"] for c in client.calls}
    assert list(states[p1.text]) == ["t1", "t2"]
    assert list(states[p2.text]) == ["t2"]
    assert sum(s.input_tokens for s in scores) == 22


def test_score_event_wraps_full_cartesian_product() -> None:
    client = Client()
    e = engine(client)
    received = []
    original = e.score_pairs

    def spy(company: str, pairs: list[PairInput], cancel: Token) -> Any:
        received.extend(pairs)
        return original(company, pairs, cancel)

    e.score_pairs = spy
    scores = e.score_event(
        "ZZAR", [thesis(), thesis(2)], [passage(), passage(2), passage(3)], Token()
    )
    assert len(received) == len(scores) == 6
    assert len(client.calls) == 3


def test_score_pairs_does_not_emit_partial_results() -> None:
    def handler(**kw: Any) -> Any:
        if kw["state"]["document"] == passage(2).text:
            raise EngineError(ErrorCode.MODEL_ERROR)
        return direct().SystemOneResponse(MODEL, dict.fromkeys(kw["questions"], 0.2), 7, 0)

    with pytest.raises(EngineError, match="MODEL_ERROR"):
        engine(Client(handler)).score_event("ZZAR", [thesis()], [passage(), passage(2)], Token())


def test_missing_answer_maps_to_model_error() -> None:
    def handler(**kw: Any) -> Any:
        answers = dict.fromkeys(kw["questions"], 0.2)
        del answers["t1__supports"]
        return direct().SystemOneResponse(MODEL, answers, 7, 0)

    with pytest.raises(EngineError) as caught:
        engine(Client(handler)).score_pairs("ZZAR", [PairInput(thesis(), passage())], Token())
    assert caught.value.code == ErrorCode.MODEL_ERROR
    assert "INCOMPLETE_RESPONSE" in (caught.value.detail or "")


def test_auth_401_and_403_have_distinct_reasons() -> None:
    d = direct()
    for status, cls, reason in [
        (401, sdk.TypeSafeAuthenticationError, "INVALID_KEY"),
        (403, sdk.TypeSafePermissionDeniedError, "FORBIDDEN"),
    ]:
        error = d.map_sdk_exception(
            cls(
                status, {"message": "denied"}, httpx2.Headers({"x-typesafe-request-id": "req-safe"})
            )
        )
        assert isinstance(error, EngineError)
        assert error.code == ErrorCode.UNAUTHENTICATED
        assert error.reason == reason
        assert "req-safe" in (error.detail or "")


def test_rate_limit_carries_retry_after_seconds() -> None:
    error = direct().map_sdk_exception(
        sdk.TypeSafeRateLimitError(429, {}, httpx2.Headers({"retry-after-ms": "2500"}))
    )
    assert error.code == ErrorCode.RATE_LIMITED
    assert error.to_wire()["data"]["retryAfterSec"] == 3


def test_context_limit_splits_multi_thesis_request_once() -> None:
    def handler(**kw: Any) -> Any:
        if len(kw["state"]["theses"]) == 4:
            raise sdk.TypeSafeBadRequestError(
                400, {"message": "context maximum tokens"}, httpx2.Headers()
            )
        return direct().SystemOneResponse(MODEL, dict.fromkeys(kw["questions"], 0.2), 11, 0)

    client = Client(handler)
    scores = engine(client).score_event(
        "ZZAR", [thesis(i) for i in range(1, 5)], [passage()], Token()
    )
    assert [len(c["state"]["theses"]) for c in client.calls] == [4, 2, 2]
    assert [s.input_tokens for s in scores] == [6, 5, 6, 5]


def test_evidence_returns_probabilities_in_sentence_order() -> None:
    fixture = json.loads((FIXTURES / "success_evidence.json").read_text())
    assert fixture["synthetic"] is True
    values = [0.05, 0.91, 0.34, 0.02]
    client = Client(
        lambda **kw: direct().SystemOneResponse(
            MODEL, dict(zip(["s1", "s2", "s3", "s4"], values, strict=True)), 19, 0
        )
    )
    result = engine(client).locate_evidence(thesis(), "weaken", ["a", "b", "c", "d"], Token())
    assert result.sentence_probabilities == values
    assert list(client.calls[0]["state"]["sentences"]) == ["s1", "s2", "s3", "s4"]


def test_cancel_before_request_sends_nothing() -> None:
    token, client = Token(), Client()
    token.event.set()
    with pytest.raises(CancelledError):
        engine(client).score_pairs("ZZAR", [PairInput(thesis(), passage())], token)
    assert client.calls == []


def test_allocate_tokens_preserves_total() -> None:
    d = direct()
    assert d.allocate_tokens(10, 3) == [4, 3, 3]
    for total in range(15):
        for count in range(1, 6):
            assert sum(d.allocate_tokens(total, count)) == total


def test_engine_never_stores_or_logs_api_key(caplog: pytest.LogCaptureFixture) -> None:
    def handler(**kw: Any) -> Any:
        raise sdk.TypeSafeAuthenticationError(
            401, {"message": KEY}, httpx2.Headers({"x-typesafe-request-id": KEY})
        )

    caplog.set_level(logging.DEBUG)
    e = engine(Client(handler))
    with pytest.raises(EngineError) as caught:
        e.score_pairs("ZZAR", [PairInput(thesis(), passage())], Token())
    assert KEY not in repr(e) + repr(vars(e)) + caplog.text + str(caught.value.detail)


def wire(questions: dict[str, Any], *, tokens: int = 11) -> dict[str, Any]:
    return {
        "model": MODEL,
        "usage": {"input_tokens": tokens, "output_tokens": 3},
        "answers": {name: {"type": "noul", "noul": 0.2} for name in questions},
    }


def sdk_engine(handler: Callable[[httpx2.Request], httpx2.Response], **kwargs: Any) -> Any:
    return direct().JevDirectEngine(
        api_key=KEY,
        model_id=MODEL,
        client_factory=direct().sdk_client_factory(transport=httpx2.MockTransport(handler)),
        **kwargs,
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://gateway.example",
        "https://gateway.example/",
        "https://gateway.example/v1/systemone",
        "https://gateway.example/v1/systemone/",
    ],
)
def test_real_sdk_factory_wire_endpoint_questions_and_usage(
    endpoint: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    monkeypatch.setenv("TYPESAFE_BASE_URL", "https://unrelated.example")
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == "https://gateway.example/v1/systemone"
        assert request.headers["authorization"] == "Bearer " + KEY
        body = json.loads(request.content)
        calls.append(body)
        fixture = json.loads((FIXTURES / "success_packed.json").read_text())
        assert fixture["synthetic"] is True and "0.7.5" in fixture["source"]
        return httpx2.Response(200, json=fixture["response"])

    factory = direct().sdk_client_factory(
        endpoint=endpoint, transport=httpx2.MockTransport(handler)
    )
    e = direct().JevDirectEngine(api_key=KEY, model_id=MODEL, client_factory=factory)
    assert isinstance(cast(object, e), SemanticEngine)
    scores = e.score_pairs(
        "ZZAR", [PairInput(thesis(kill=True), passage()), PairInput(thesis(2), passage())], Token()
    )
    assert [s.input_tokens for s in scores] == [6, 5]
    assert all(not s.tokens_estimated and s.model_id == MODEL for s in scores)
    expected = direct().question_set.build_score_questions(
        [thesis(kill=True), thesis(2)], flavor="direct"
    )
    assert calls[0]["model"] == MODEL
    assert len(calls[0]["questions"]) == 9
    for name, spec in expected.items():
        assert calls[0]["questions"][name] == {
            "type": "noul",
            "instructions": spec.instructions,
            "criteria": {"true": spec.true_text, "false": spec.false_text},
        }
    assert calls[0]["state"]["document"] == passage().text
    assert "kill_condition" not in calls[0]["state"]["theses"]["t2"]
    e._client.close()


def test_default_factory_uses_official_endpoint_without_environment_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    d = direct()
    monkeypatch.setenv("TYPESAFE_BASE_URL", "https://unrelated.example")
    e = d.JevDirectEngine(api_key=KEY, model_id=MODEL)
    assert e._client._sdk._config.base_url == "https://api.typesafe.ai"
    assert e.health().state == "ok"
    e._client.close()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://gateway.example/v1/systemone",
        "https://user:pw@gateway.example",
        "https://gateway.example/v1/systemone?key=fake",
        "https://gateway.example/v1/systemone#secret",
        "https://gateway.example/v1/",
        "https://gateway.example:bad",
        "https://gateway.example/\n",
        "bad",
    ],
)
def test_invalid_endpoint_rejected(endpoint: str) -> None:
    with pytest.raises(ValueError):
        direct().JevDirectEngine(api_key=KEY, model_id=MODEL, endpoint=endpoint)


@pytest.mark.parametrize("key", [None, "", " ", "has space", "has\ttab", "non-ascii-密钥"])
def test_missing_or_invalid_key_is_unconfigured_without_sdk_or_environment_fallback(
    key: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", KEY)
    calls = []
    e = direct().JevDirectEngine(
        api_key=key, model_id=MODEL, client_factory=lambda k: calls.append(k)
    )
    assert e.health().state == "unconfigured"
    with pytest.raises(UserError) as caught:
        e.score_pairs("ZZAR", [PairInput(thesis(), passage())], Token())
    assert caught.value.code == ErrorCode.CONFIG_REQUIRED
    assert caught.value.to_wire()["message"] == "还需要完成设置：Jev 密钥。"
    assert calls == []


@pytest.mark.parametrize("workers", [True, False, 0, 5, -1, 1.5, "4", None])
def test_max_workers_rejects_bool_nonint_and_out_of_range(workers: object) -> None:
    with pytest.raises(ValueError):
        engine(Client(), max_workers=workers)


@pytest.mark.parametrize(
    "model", ["jev-latest", "jev-preview", "other-1.14.0", "jev-1.14", "", None]
)
def test_model_requires_exact_version(model: object) -> None:
    with pytest.raises(ValueError):
        direct().JevDirectEngine(api_key=KEY, model_id=model)


@pytest.mark.parametrize(
    "field,value",
    [
        ("ref", "t2"),
        ("version", 2),
        ("statement", "Different"),
        ("kill_condition", "Different"),
        ("content_hash", "Different"),
    ],
)
def test_same_thesis_identity_must_have_consistent_ref_version_hash_and_content(
    field: str,
    value: Any,
) -> None:
    client = Client()
    with pytest.raises(ValueError):
        engine(client).score_pairs(
            "ZZAR",
            [
                PairInput(thesis(), passage()),
                PairInput(replace(thesis(), **{field: value}), passage(2)),
            ],
            Token(),
        )
    assert client.calls == []


@pytest.mark.parametrize("field,value", [("text", "Different"), ("content_hash", "Different")])
def test_passage_identity_rejects_inconsistent_hash_or_text(field: str, value: str) -> None:
    client = Client()
    with pytest.raises(ValueError):
        engine(client).score_pairs(
            "ZZAR",
            [
                PairInput(thesis(), passage()),
                PairInput(thesis(2), replace(passage(), **{field: value})),
            ],
            Token(),
        )
    assert client.calls == []


def test_duplicate_pair_ref_collision_and_more_than_five_theses_rejected() -> None:
    for pairs in [
        [PairInput(thesis(), passage())] * 2,
        [PairInput(thesis(), passage()), PairInput(replace(thesis(2), ref="t1"), passage(2))],
        [PairInput(thesis(i), passage(i)) for i in range(1, 7)],
        [],
    ]:
        client = Client()
        with pytest.raises(ValueError):
            engine(client).score_pairs("ZZAR", pairs, Token())
        assert client.calls == []


def test_unpacked_mode_preserves_sparse_pairs_and_counts_each_request_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(direct().question_set, "PACK_THESES", False)
    client = Client()
    pairs = [
        PairInput(thesis(2), passage(2)),
        PairInput(thesis(), passage()),
        PairInput(thesis(2), passage()),
    ]
    result = engine(client).score_pairs("ZZAR", pairs, Token())
    assert len(result) == len(client.calls) == 3
    assert [s.input_tokens for s in result] == [11, 11, 11]
    assert all(len(c["state"]["theses"]) == 1 for c in client.calls)


@pytest.mark.parametrize(
    "total,count", [(True, 1), (-1, 1), (1.1, 1), (10, True), (10, 0), (10, 1.1)]
)
def test_allocate_tokens_rejects_invalid_counts(total: object, count: object) -> None:
    with pytest.raises(ValueError):
        direct().allocate_tokens(total, count)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.1, True, "0.2", None])
def test_nonfinite_bool_or_invalid_probability_fails_whole_batch(value: object) -> None:
    def handler(**kw: Any) -> Any:
        answers: dict[str, Any] = dict.fromkeys(kw["questions"], 0.2)
        answers["t1__relevant"] = value
        return direct().SystemOneResponse(MODEL, answers, 1, 0)

    with pytest.raises(EngineError) as caught:
        engine(Client(handler)).score_pairs("ZZAR", [PairInput(thesis(), passage())], Token())
    assert caught.value.code == ErrorCode.MODEL_ERROR


@pytest.mark.parametrize(
    "model,input_tokens,output_tokens",
    [
        ("jev-1.13.0", 1, 0),
        (MODEL, None, 0),
        (MODEL, True, 0),
        (MODEL, -1, 0),
        (MODEL, 1.5, 0),
        (MODEL, 1, None),
        (MODEL, 1, True),
        (MODEL, 1, -1),
    ],
)
def test_model_and_usage_are_strict(
    model: str, input_tokens: object, output_tokens: object
) -> None:
    client = Client(
        lambda **kw: direct().SystemOneResponse(
            model, dict.fromkeys(kw["questions"], 0.2), input_tokens, output_tokens
        )
    )
    with pytest.raises(EngineError) as caught:
        engine(client).score_pairs("ZZAR", [PairInput(thesis(), passage())], Token())
    assert caught.value.code == ErrorCode.MODEL_ERROR


@pytest.mark.parametrize(
    "status,code,reason",
    [
        (404, ErrorCode.UNAUTHENTICATED, "MODEL_NOT_FOUND"),
        (400, ErrorCode.INTERNAL, "INVALID_REQUEST"),
        (413, ErrorCode.INTERNAL, "INVALID_REQUEST"),
        (422, ErrorCode.INTERNAL, "INVALID_REQUEST"),
        (500, ErrorCode.MODEL_ERROR, "SDK_FAILURE"),
        (529, ErrorCode.MODEL_ERROR, "SDK_FAILURE"),
    ],
)
def test_actual_sdk_http_exception_mapping_and_safe_summary(
    status: int, code: ErrorCode, reason: str
) -> None:
    d = direct()
    exception = sdk.TypeSafeAPIError(
        status,
        {"message": "Private document " + KEY},
        httpx2.Headers({"x-typesafe-request-id": "safe-id"}),
    )
    error = d.map_sdk_exception(exception)
    assert error.code == code and error.reason == reason
    assert isinstance(error, InternalError if code == ErrorCode.INTERNAL else EngineError)
    assert "safe-id" in (error.detail or "")
    assert "Private document" not in (error.detail or "") and KEY not in (error.detail or "")


@pytest.mark.parametrize(
    "exc,code",
    [
        (sdk.TypeSafeAPITimeoutError(60.0), ErrorCode.TIMEOUT),
        (sdk.TypeSafeAPIConnectionError("denied"), ErrorCode.MODEL_ERROR),
        (
            sdk.TypeSafeAPIResponseValidationError(200, {}, httpx2.Headers(), "answers"),
            ErrorCode.MODEL_ERROR,
        ),
        (httpx2.ReadTimeout("blocked"), ErrorCode.TIMEOUT),
    ],
)
def test_sdk_transport_and_validation_errors(exc: BaseException, code: ErrorCode) -> None:
    assert direct().map_sdk_exception(exc).code == code


@pytest.mark.parametrize(
    "request_id",
    [KEY, "req-" + KEY, "sk-secret12345", "bad\nheader", "x" * 129, "echo private prose", "a" * 64],
)
def test_request_id_secret_and_untrusted_text_are_dropped(request_id: str) -> None:
    d = direct()
    d.register_secret(KEY)
    error = d.map_sdk_exception(
        sdk.TypeSafeAPIError(
            401, {"message": KEY}, httpx2.Headers({"x-typesafe-request-id": request_id})
        )
    )
    assert request_id not in error.detail
    assert "local-" in error.detail and len(error.detail) <= 200


def test_no_raw_exception_chain_survives_sdk_failure() -> None:
    def handler(**kw: Any) -> Any:
        try:
            raise sdk.TypeSafeAuthenticationError(401, {"message": KEY}, httpx2.Headers())
        except sdk.TypeSafeAPIError as original:
            raise EngineError(ErrorCode.MODEL_ERROR, detail="failed " + KEY) from original

    with pytest.raises(EngineError) as caught:
        engine(Client(handler)).score_pairs("ZZAR", [PairInput(thesis(), passage())], Token())
    text = "".join(traceback.format_exception(caught.value))
    assert KEY not in text and caught.value.__cause__ is None and caught.value.__context__ is None


@pytest.mark.parametrize("status", [400, 422])
def test_context_split_stops_after_one_level_and_422_never_splits(status: int) -> None:
    def handler(**kw: Any) -> Any:
        raise sdk.TypeSafeAPIError(status, {"message": "context maximum tokens"}, httpx2.Headers())

    client = Client(handler)
    with pytest.raises(InternalError):
        engine(client).score_event("ZZAR", [thesis(i) for i in range(1, 5)], [passage()], Token())
    assert [len(c["state"]["theses"]) for c in client.calls] == ([4, 2] if status == 400 else [4])


def test_single_thesis_context_error_never_retries() -> None:
    client = Client(
        lambda **kw: (_ for _ in ()).throw(
            sdk.TypeSafeAPIError(400, {"message": "context maximum"}, httpx2.Headers())
        )
    )
    with pytest.raises(InternalError):
        engine(client).score_event("ZZAR", [thesis()], [passage()], Token())
    assert len(client.calls) == 1


def run_consumer(
    e: Any, token: Token, *, evidence: bool = False
) -> tuple[threading.Thread, list[BaseException]]:
    errors: list[BaseException] = []

    def consume() -> None:
        try:
            if evidence:
                e.locate_evidence(thesis(), "weaken", ["sentence"], token)
            else:
                e.score_event("ZZAR", [thesis()], [passage(i) for i in range(1, 10)], token)
        except BaseException as exc:
            errors.append(exc)

    consumer = threading.Thread(target=consume, daemon=True)
    consumer.start()
    return consumer, errors


@pytest.mark.parametrize("evidence", [False, True])
def test_blocked_client_cancel_returns_promptly_and_sends_no_new_requests(evidence: bool) -> None:
    started, release, token = threading.Event(), threading.Event(), Token()

    def handler(**kw: Any) -> Any:
        started.set()
        assert release.wait(3)
        return direct().SystemOneResponse(MODEL, dict.fromkeys(kw["questions"], 0.2), 11, 0)

    client, e = Client(handler), None
    e = engine(client, max_workers=1)
    consumer, errors = run_consumer(e, token, evidence=evidence)
    try:
        assert started.wait(1)
        before = time.monotonic()
        token.event.set()
        consumer.join(0.2)
        assert not consumer.is_alive() and time.monotonic() - before < 0.2
        assert isinstance(errors[0], CancelledError)
        assert len(client.calls) == 1
    finally:
        release.set()
        consumer.join(1)


def test_four_way_concurrency_and_stable_output_order() -> None:
    started = threading.Barrier(5)
    release = threading.Event()
    client: Client

    def handler(**kw: Any) -> Any:
        if len(client.calls) <= 4:
            started.wait(2)
            assert release.wait(2)
        return direct().SystemOneResponse(MODEL, dict.fromkeys(kw["questions"], 0.2), 11, 0)

    client = Client(handler)
    e = engine(client)
    result = []
    consumer = threading.Thread(
        target=lambda: result.extend(
            e.score_event("ZZAR", [thesis()], [passage(i) for i in (5, 4, 3, 2, 1)], Token())
        ),
        daemon=True,
    )
    consumer.start()
    try:
        started.wait(2)
        assert len(client.calls) == e._active == 4
    finally:
        release.set()
        consumer.join(2)
    assert not consumer.is_alive()
    assert [s.passage_id for s in result] == ["p5", "p4", "p3", "p2", "p1"]


def test_cancelled_stuck_slots_remain_bounded_across_new_batches() -> None:
    started, release = threading.Event(), threading.Event()

    def handler(**kw: Any) -> Any:
        started.set()
        assert release.wait(3)
        return direct().SystemOneResponse(MODEL, dict.fromkeys(kw["questions"], 0.2), 1, 0)

    client, token = Client(handler), Token()
    e = engine(client, max_workers=1)
    consumer, errors = run_consumer(e, token)
    try:
        assert started.wait(1)
        token.event.set()
        consumer.join(0.2)
        assert isinstance(errors[0], CancelledError) and e._active == 1
        for _ in range(3):
            second = Token()
            pending, pending_errors = run_consumer(e, second)
            second.event.set()
            pending.join(0.2)
            assert not pending.is_alive() and isinstance(pending_errors[0], CancelledError)
        assert len(client.calls) == e._active == 1
    finally:
        release.set()


def test_blocked_sdk_daemon_does_not_hold_process_exit() -> None:
    program = """
import threading
import httpx2
from sentinel.errors import CancelledError
from sentinel.semantic.base import ThesisInput, PassageInput
from sentinel.semantic.engines.jev_direct import JevDirectEngine, sdk_client_factory
class Token:
    def __init__(self): self.event = threading.Event()
    def is_cancelled(self): return self.event.is_set()
    def raise_if_cancelled(self):
        if self.is_cancelled(): raise CancelledError()
token = Token()
def transport(request):
    token.event.set()
    threading.Event().wait()
factory = sdk_client_factory(transport=httpx2.MockTransport(transport))
engine = JevDirectEngine(
    api_key="test-key-do-not-use", model_id="jev-1.14.0", client_factory=factory
)
try:
    engine.score_event(
        "ZZAR", [ThesisInput("t1", "id", 1, "statement", None, "hash")],
        [PassageInput("p1", "text", "hash")], token
    )
except CancelledError:
    print("cancelled; daemon process exits")
else:
    raise AssertionError("expected cancellation")
"""
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, timeout=3
    )
    assert result.returncode == 0 and "daemon process exits" in result.stdout


def test_blocked_client_total_timeout_is_not_read_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(direct(), "REQUEST_TIMEOUT_SEC", 0.08)
    started, release = threading.Event(), threading.Event()

    def handler(**kw: Any) -> Any:
        started.set()
        release.wait(3)
        return direct().SystemOneResponse(MODEL, dict.fromkeys(kw["questions"], 0.2), 1, 0)

    client = Client(handler)
    e = engine(client, max_workers=1)
    consumer, errors = run_consumer(e, Token())
    try:
        assert started.wait(1)
        consumer.join(0.3)
        assert not consumer.is_alive()
        assert isinstance(errors[0], EngineError) and errors[0].code == ErrorCode.TIMEOUT
        assert len(client.calls) == e._active == 1
    finally:
        release.set()


def test_any_failure_stops_new_requests_while_sibling_is_blocked() -> None:
    blocked, release = threading.Event(), threading.Event()

    def handler(**kw: Any) -> Any:
        if kw["state"]["document"] == passage().text:
            blocked.set()
            assert release.wait(3)
            return direct().SystemOneResponse(MODEL, dict.fromkeys(kw["questions"], 0.2), 1, 0)
        assert blocked.wait(1)
        raise sdk.TypeSafeAPIError(500, {}, httpx2.Headers())

    client = Client(handler)
    e = engine(client, max_workers=2)
    consumer, errors = run_consumer(e, Token())
    try:
        consumer.join(0.3)
        assert not consumer.is_alive() and isinstance(errors[0], EngineError)
        assert errors[0].code == ErrorCode.MODEL_ERROR
        assert len(client.calls) == 2
    finally:
        release.set()


@pytest.mark.parametrize("status", [429, 500, 529])
def test_real_sdk_owns_exactly_three_extra_retries(
    status: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(
            status, json={"message": "synthetic"}, headers={"retry-after-ms": "0"}
        )

    e = sdk_engine(handler)
    sdk_policy = e._client._sdk._retry
    assert sdk_policy.stop is not None
    assert e._client._sdk._config.timeout == direct().REQUEST_TIMEOUT_SEC == 60.0
    with pytest.raises(EngineError):
        e.score_event("ZZAR", [thesis()], [passage()], Token())
    assert len(calls) == 4
    assert [request.headers.get("x-typesafe-retry-count", "0") for request in calls] == [
        "0",
        "1",
        "2",
        "3",
    ]
    e._client.close()


@pytest.mark.parametrize("status", [401, 403, 404, 400, 422])
def test_real_sdk_does_not_retry_other_4xx(status: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(status, json={"message": "synthetic"})

    e = sdk_engine(handler)
    with pytest.raises((EngineError, InternalError)):
        e.score_event("ZZAR", [thesis()], [passage()], Token())
    assert len(calls) == 1
    assert e.health().state == ("degraded" if status in (401, 403, 404) else "ok")
    e._client.close()


def test_real_sdk_retry_success_does_not_count_failed_attempt_tokens_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx2.Response(500, json={}, headers={"retry-after-ms": "0"})
        return httpx2.Response(200, json=wire(json.loads(request.content)["questions"], tokens=13))

    e = sdk_engine(handler)
    result = e.score_event("ZZAR", [thesis(), thesis(2)], [passage()], Token())
    assert len(calls) == 2 and [s.input_tokens for s in result] == [7, 6]
    e._client.close()


def test_sdk_retry_wait_cancel_stops_all_later_attempts_and_remains_interruptible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    token, waiting = Token(), threading.Event()
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(429, json={}, headers={"retry-after-ms": "30000"})

    e = sdk_engine(handler, max_workers=1)
    sleep_hook = e._client._sdk._retry.sleep

    def observed_sleep(delay: float) -> None:
        waiting.set()
        sleep_hook(delay)

    e._client._sdk._retry.sleep = observed_sleep
    consumer, errors = run_consumer(e, token)
    assert waiting.wait(1)
    token.event.set()
    consumer.join(0.2)
    assert not consumer.is_alive() and isinstance(errors[0], CancelledError)
    with e._condition:
        assert e._condition.wait_for(lambda: e._active == 0, timeout=0.3)
    assert len(calls) == 1
    e._client.close()


def test_sdk_total_budget_covers_retry_wait_and_does_not_send_after_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    monkeypatch.setattr(direct(), "REQUEST_TIMEOUT_SEC", 0.08)
    calls = []
    release = threading.Event()

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        if len(calls) == 2:
            assert release.wait(3)
        return httpx2.Response(500, json={}, headers={"retry-after-ms": "60"})

    e = sdk_engine(handler, max_workers=1)
    before = time.monotonic()
    consumer, errors = run_consumer(e, Token())
    try:
        consumer.join(0.3)
        assert not consumer.is_alive() and isinstance(errors[0], EngineError)
        assert errors[0].code == ErrorCode.TIMEOUT
        assert time.monotonic() - before < 0.3
    finally:
        release.set()
        with e._condition:
            assert e._condition.wait_for(lambda: e._active == 0, timeout=0.3)
    assert len(calls) == 2
    e._client.close()


def test_stalled_real_sdk_transport_cancel_prevents_retries_after_it_unblocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    started, release, token = threading.Event(), threading.Event(), Token()
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        started.set()
        assert release.wait(3)
        return httpx2.Response(500, json={}, headers={"retry-after-ms": "0"})

    e = sdk_engine(handler, max_workers=1)
    consumer, errors = run_consumer(e, token)
    try:
        assert started.wait(1)
        token.event.set()
        consumer.join(0.2)
        assert not consumer.is_alive() and isinstance(errors[0], CancelledError)
        assert len(calls) == 1
    finally:
        release.set()
        with e._condition:
            assert e._condition.wait_for(lambda: e._active == 0, timeout=0.3)
        e._client.close()
    assert len(calls) == 1


def test_real_sdk_slow_stream_enforces_total_deadline_without_read_timeout_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    d = direct()
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    monkeypatch.setattr(d, "REQUEST_TIMEOUT_SEC", 0.08)
    release = threading.Event()
    started = threading.Event()

    class Stream(httpx2.SyncByteStream):
        def __iter__(self) -> Any:
            started.set()
            yield b'{"model":'
            assert release.wait(3)
            yield b'"jev-1.14.0"}'

    e = sdk_engine(lambda request: httpx2.Response(200, stream=Stream()), max_workers=1)
    consumer, errors = run_consumer(e, Token())
    try:
        assert started.wait(1)
        consumer.join(0.3)
        assert not consumer.is_alive() and isinstance(errors[0], EngineError)
        assert errors[0].code == ErrorCode.TIMEOUT
    finally:
        release.set()
        with e._condition:
            assert e._condition.wait_for(lambda: e._active == 0, timeout=0.3)
        e._client.close()


@pytest.mark.parametrize(
    "variant",
    [
        "missing",
        "extra",
        "future_type",
        "choice",
        "nan",
        "bool",
        "null_usage",
        "bool_usage",
        "model",
        "not_json",
    ],
)
def test_real_sdk_rejects_bad_wire_and_extra_answers(
    variant: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)

    def handler(request: httpx2.Request) -> httpx2.Response:
        payload = wire(json.loads(request.content)["questions"])
        answer = payload["answers"]["t1__relevant"]
        if variant == "missing":
            del payload["answers"]["t1__supports"]
        elif variant == "extra":
            payload["answers"]["foreign"] = {"type": "noul", "noul": 0.2}
        elif variant in ("future_type", "choice"):
            answer["type"] = "unrecognized" if variant == "future_type" else "choice"
        elif variant in ("nan", "bool"):
            answer["noul"] = float("nan") if variant == "nan" else True
        elif variant in ("null_usage", "bool_usage"):
            payload["usage"]["input_tokens"] = None if variant == "null_usage" else True
        elif variant == "model":
            payload["model"] = "jev-1.13.0"
        if variant == "not_json":
            return httpx2.Response(200, content=b"invalid")
        return httpx2.Response(200, json=payload)

    e = sdk_engine(handler)
    with pytest.raises(EngineError) as caught:
        e.score_event("ZZAR", [thesis()], [passage()], Token())
    assert caught.value.code == ErrorCode.MODEL_ERROR
    e._client.close()


def test_transport_verbose_logs_are_scoped_to_engine_thread_and_application_logs_continue(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    caplog.set_level(logging.DEBUG)
    outside, observed = threading.Event(), threading.Event()
    disable_before = logging.root.manager.disable
    level_before = logging.getLogger().level

    def other_application() -> None:
        assert outside.wait(2)
        logging.getLogger("sentinel.app").info("concurrent application log")
        logging.getLogger("typesafe_sdk").info("outside SDK call still logs")
        observed.set()

    other = threading.Thread(target=other_application)
    other.start()

    def handler(request: httpx2.Request) -> httpx2.Response:
        for name in ("typesafe_sdk", "httpx2", "httpcore2.connection", "httpcore2.http11"):
            logging.getLogger(name).debug("raw secret " + KEY)
        logging.getLogger("sentinel.semantic").info("engine application log")
        outside.set()
        assert observed.wait(2)
        return httpx2.Response(
            401, json={"message": "private body " + KEY}, headers={"x-typesafe-request-id": KEY}
        )

    e = sdk_engine(handler)
    with pytest.raises(EngineError) as caught:
        e.score_event("ZZAR", [thesis()], [passage()], Token())
    other.join(1)
    assert KEY not in caplog.text + str(caught.value.detail)
    assert "private body" not in caplog.text
    for line in (
        "concurrent application log",
        "engine application log",
        "outside SDK call still logs",
    ):
        assert line in caplog.text
    assert (
        logging.root.manager.disable == disable_before and logging.getLogger().level == level_before
    )
    e._client.close()


def test_offline_blocks_adapter_and_run_time_transition_stops_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        monkeypatch.setenv("SENTINEL_OFFLINE", "1")
        return httpx2.Response(500, json={}, headers={"retry-after-ms": "0"})

    e = sdk_engine(handler)
    for offline, expected_calls in [(True, 0), (False, 1)]:
        if not offline:
            monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
        with pytest.raises(SourceError) as caught:
            e.score_event("ZZAR", [thesis()], [passage()], Token())
        assert caught.value.code == ErrorCode.SOURCE_UNAVAILABLE
        assert caught.value.reason == "OFFLINE" and len(calls) == expected_calls
    e._client.close()


@pytest.mark.parametrize(
    "relation,has_kill",
    [("overturn", True), ("overturn", False), ("weaken", True), ("uncertain", False)],
)
def test_real_sdk_evidence_uses_shared_templates_and_sentence_order(
    relation: str,
    has_kill: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        calls.append(body)
        fixture = json.loads((FIXTURES / "success_evidence.json").read_text())
        return httpx2.Response(200, json=fixture["response"])

    e = sdk_engine(handler)
    result = e.locate_evidence(thesis(kill=has_kill), relation, ["a", "b", "c", "d"], Token())
    assert result.sentence_probabilities == [0.05, 0.91, 0.34, 0.02]
    assert result.input_tokens == 19 and not result.tokens_estimated
    assert ("kill_condition" in calls[0]["state"]) == has_kill
    expected = direct().question_set.build_evidence_questions(
        relation, 4, has_kill=has_kill, flavor="direct"
    )
    assert [calls[0]["questions"][name]["instructions"] for name in expected] == [
        q.instructions for q in expected.values()
    ]
    e._client.close()


@pytest.mark.parametrize("sentences", [[], ["sentence"] * 41, [""], [" "], ["x" * 1201]])
def test_evidence_invalid_inputs_send_nothing(sentences: list[str]) -> None:
    client = Client()
    with pytest.raises(ValueError):
        engine(client).locate_evidence(thesis(), "weaken", sentences, Token())
    assert client.calls == []


def test_retry_after_date_uses_sharedclock_not_sdk_wall_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    d = direct()
    monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-02T00:35:00Z")
    date = format_datetime(d.clock.now() + timedelta(seconds=3), usegmt=True)
    error = d.map_sdk_exception(
        sdk.TypeSafeRateLimitError(429, {}, httpx2.Headers({"retry-after": date}))
    )
    assert error.to_wire()["data"]["retryAfterSec"] == 3


def test_sdk_long_retry_after_stops_before_overspending_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(429, json={}, headers={"retry-after-ms": "120000"})

    e = sdk_engine(handler)
    before = time.monotonic()
    with pytest.raises(EngineError) as caught:
        e.score_event("ZZAR", [thesis()], [passage()], Token())
    assert caught.value.code == ErrorCode.RATE_LIMITED
    assert cast(dict[str, Any], caught.value.to_wire()["data"])["retryAfterSec"] == 120
    assert time.monotonic() - before < 0.3 and len(calls) == 1
    e._client.close()


def test_context_split_shares_original_deadline_and_counts_only_successful_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(direct(), "REQUEST_TIMEOUT_SEC", 0.08)
    calls = []
    release = threading.Event()

    def handler(**kw: Any) -> Any:
        calls.append(kw)
        if len(calls) == 1:
            raise sdk.TypeSafeAPIError(400, {"message": "context maximum tokens"}, httpx2.Headers())
        if len(calls) == 3:
            assert release.wait(3)
        return direct().SystemOneResponse(MODEL, dict.fromkeys(kw["questions"], 0.2), 11, 0)

    e = engine(Client(handler), max_workers=1)
    errors = []

    def consume() -> None:
        try:
            e.score_event("ZZAR", [thesis(i) for i in range(1, 5)], [passage()], Token())
        except EngineError as exc:
            errors.append(exc)

    consumer = threading.Thread(target=consume, daemon=True)
    consumer.start()
    try:
        consumer.join(0.3)
        assert not consumer.is_alive() and errors[0].code == ErrorCode.TIMEOUT
        assert [len(c["state"]["theses"]) for c in calls] == [4, 2, 2]
    finally:
        release.set()


def test_monotonic_latency_is_independent_of_business_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    d = direct()
    monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-02T00:35:00Z")
    started, release = threading.Event(), threading.Event()

    def handler(**kw: Any) -> Any:
        started.set()
        assert release.wait(2)
        return d.SystemOneResponse(MODEL, dict.fromkeys(kw["questions"], 0.2), 1, 0)

    e = engine(Client(handler))
    results = []
    consumer = threading.Thread(
        target=lambda: results.extend(e.score_event("ZZAR", [thesis()], [passage()], Token())),
        daemon=True,
    )
    consumer.start()
    assert started.wait(1)
    monkeypatch.setenv("SENTINEL_CLOCK", "2020-01-01T00:00:00Z")
    release.set()
    consumer.join(1)
    assert not consumer.is_alive() and len(results) == 1
    assert 0 <= results[0].latency_ms < 1000
