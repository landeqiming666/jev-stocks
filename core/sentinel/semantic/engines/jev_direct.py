from __future__ import annotations

import logging
import math
import os
import re
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

import httpx2

from sentinel import clock
from sentinel.domain.classify import Probabilities, Relation, validate_probability
from sentinel.errors import (
    CancelledError,
    EngineError,
    ErrorCode,
    InternalError,
    SentinelError,
    SourceError,
    UserError,
)
from sentinel.ids import new_id
from sentinel.messages import render
from sentinel.security.redact import redact_text, register_secret
from sentinel.semantic import questions as question_set
from sentinel.semantic.base import (
    JEV_CONCURRENCY,
    CancelToken,
    EngineHealth,
    EvidenceScore,
    PairInput,
    PairScore,
    PassageInput,
    ThesisInput,
    cartesian_pairs,
    validate_count,
)
from sentinel.semantic.questions import QuestionSpec

REQUEST_TIMEOUT_SEC = 60.0
MAX_RETRIES = 3
BACKOFF_INITIAL_SEC = 1.0
BACKOFF_MAX_SEC = 20.0
MAX_EVIDENCE_SENTENCES = question_set.MAX_EVIDENCE_SENTENCES
CONTEXT_RETRY_MIN_THESES = 2
DEFAULT_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
_CANCEL_CHECK_SEC = 0.02
_local = threading.local()


@dataclass(frozen=True)
class SystemOneResponse:
    model: str
    answers: Mapping[str, float]
    input_tokens: int
    output_tokens: int


class SystemOneClient(Protocol):
    def call(
        self, *, model: str, state: dict[str, object], questions: dict[str, QuestionSpec]
    ) -> SystemOneResponse: ...


def allocate_tokens(total: int, pair_count: int) -> list[int]:
    validate_count(total)
    validate_count(pair_count, minimum=1)
    quotient, remainder = divmod(total, pair_count)
    return [quotient + int(i < remainder) for i in range(pair_count)]


def _request_id(exc: BaseException) -> str:
    value = getattr(exc, "request_id", None)
    if isinstance(value, str):
        safe = redact_text(value)
        if safe == value and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", safe):
            return safe
    return "local-" + new_id()


def _retry_after_seconds(exc: BaseException) -> int:
    headers = getattr(exc, "headers", {})
    dated = headers.get("retry-after") if isinstance(headers, Mapping) else None
    if isinstance(dated, str) and headers.get("retry-after-ms") is None:
        try:
            float(dated)
        except ValueError:
            try:
                # SDK 日期解析用墙钟，业务诊断改用统一时钟。
                seconds = (parsedate_to_datetime(dated) - clock.now()).total_seconds()
                if math.isfinite(seconds):
                    return math.ceil(max(0, seconds))
            except (TypeError, ValueError, OverflowError):
                pass
    milliseconds = getattr(exc, "retry_after_ms", None)
    if isinstance(milliseconds, (int, float)) and not isinstance(milliseconds, bool):
        try:
            if math.isfinite(milliseconds) and milliseconds >= 0:
                return math.ceil(milliseconds / 1000)
        except OverflowError:
            pass
    for name, multiplier in (("retry-after-ms", 0.001), ("retry-after", 1.0)):
        raw = headers.get(name) if isinstance(headers, Mapping) else None
        if not isinstance(raw, str):
            continue
        try:
            seconds = float(raw) * multiplier
        except ValueError:
            if name != "retry-after":
                continue
            try:
                seconds = (parsedate_to_datetime(raw) - clock.now()).total_seconds()
            except (TypeError, ValueError, OverflowError):
                continue
        if math.isfinite(seconds):
            return math.ceil(max(0, seconds))
    return 1


def map_sdk_exception(exc: BaseException) -> SentinelError:
    if isinstance(exc, SentinelError):
        # 同一错误族也可能由注入客户端构造；不得携带未经清理的诊断。
        family: type[SentinelError] = next(
            (
                cls
                for cls in (CancelledError, InternalError, EngineError, SourceError, UserError)
                if isinstance(exc, cls)
            ),
            SentinelError,
        )
        params: dict[str, object] = {}
        if exc.code == ErrorCode.RATE_LIMITED:
            value = exc.params.get("retryAfterSec", 1)
            params["retryAfterSec"] = value if type(value) is int and value >= 0 else 1
        if exc.code == ErrorCode.CONFIG_REQUIRED:
            params["missing"] = ["jevKey"]
        reason = redact_text(exc.reason) if exc.reason else None
        if reason and re.fullmatch(r"[A-Z_]{1,64}", reason) is None:
            reason = None
        return family(
            exc.code,
            params=params,
            reason=reason,
            detail=redact_text(exc.detail)[:200] if exc.detail else None,
        )
    status = getattr(exc, "status", None)
    status = status if type(status) is int else None
    summary = f"status={status}; request_id={_request_id(exc)}; source=SDK"
    # 原始异常文本、正文、headers 与 field_path 都可能回显密钥或用户文本。
    if status in (401, 403, 404):
        reason = {401: "INVALID_KEY", 403: "FORBIDDEN", 404: "MODEL_NOT_FOUND"}[status]
        return EngineError(ErrorCode.UNAUTHENTICATED, reason=reason, detail=summary)
    if status == 429:
        return EngineError(
            ErrorCode.RATE_LIMITED,
            params={"retryAfterSec": _retry_after_seconds(exc)},
            detail=summary,
        )
    if isinstance(exc, (TimeoutError, httpx2.TimeoutException)) or status == 408:
        return EngineError(ErrorCode.TIMEOUT, detail=summary)
    if status in (400, 413, 422):
        return InternalError(reason="INVALID_REQUEST", detail=summary)
    return EngineError(ErrorCode.MODEL_ERROR, reason="SDK_FAILURE", detail=summary)


def _context_limit(exc: BaseException) -> bool:
    # 05 §3.3 的例外只允许 400；422 验证错误不能伪装成可拆分请求。
    if getattr(exc, "status", None) != 400:
        return False
    body = getattr(exc, "body", None)
    message = (
        body.get("message", body.get("detail", body.get("error")))
        if isinstance(body, dict)
        else body
    )
    if isinstance(message, dict):
        message = message.get("message")
    if not isinstance(message, str):
        return False
    lowered = message.lower()
    return "context" in lowered and ("maximum" in lowered or "token" in lowered)


def _origin(endpoint: str) -> str:
    if not isinstance(endpoint, str) or any(c.isspace() for c in endpoint):
        raise ValueError("invalid endpoint")
    url = urlsplit(endpoint)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or url.path.rstrip("/") not in ("", "/v1/systemone")
    ):
        raise ValueError("endpoint must be HTTPS origin or /v1/systemone without credentials")
    try:
        _ = url.port
    except ValueError:
        raise ValueError("invalid endpoint port") from None
    return f"{url.scheme}://{url.netloc}"


@dataclass
class _CallContext:
    cancel: CancelToken | None
    stopped: threading.Event
    deadline: float

    def check(self) -> None:
        if self.cancel is not None:
            self.cancel.raise_if_cancelled()
        if self.stopped.is_set():
            raise CancelledError()
        if time.monotonic() >= self.deadline:
            raise EngineError(ErrorCode.TIMEOUT, reason="REQUEST_DEADLINE")


class _TransportLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not (
            getattr(_local, "context", None) is not None
            and record.name.split(".")[0] in {"typesafe_sdk", "httpx2", "httpcore2"}
        )


_log_filter = _TransportLogFilter()
_log_lock = threading.Lock()


def _protect_transport_logs() -> None:
    # 按当前调用线程过滤传输记录；不改 root level/disable 或其他线程的应用日志。
    with _log_lock:
        names = ["typesafe_sdk", "httpx2"] + [
            "httpcore2." + suffix for suffix in ("connection", "http11", "http2", "proxy", "socks")
        ]
        for name in names:
            logging.getLogger(name).addFilter(_log_filter)


class _DeadlineStream(httpx2.SyncByteStream):
    def __init__(self, stream: httpx2.SyncByteStream, context: _CallContext) -> None:
        self.stream, self.context = stream, context

    def __iter__(self) -> Iterator[bytes]:
        try:
            self.context.check()
            for chunk in self.stream:
                self.context.check()
                yield chunk
            self.context.check()
        finally:
            self.stream.close()

    def close(self) -> None:
        self.stream.close()


class _GuardedTransport(httpx2.BaseTransport):
    def __init__(self, transport: httpx2.BaseTransport) -> None:
        self.transport = transport

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        context: _CallContext = _local.context
        context.check()
        if os.environ.get("SENTINEL_OFFLINE") == "1":
            raise SourceError(ErrorCode.SOURCE_UNAVAILABLE, reason="OFFLINE")
        remaining = max(0.001, context.deadline - time.monotonic())
        request.extensions["timeout"] = dict.fromkeys(
            ("connect", "read", "write", "pool"), remaining
        )
        # 服务端 cookie 不成为后续请求的新凭据，重定向由 httpx2.Client 禁用。
        request.headers.pop("cookie", None)
        response = self.transport.handle_request(request)
        try:
            context.check()
        except SentinelError:
            response.close()
            raise
        assert isinstance(response.stream, httpx2.SyncByteStream)
        response.stream = _DeadlineStream(response.stream, context)
        return response

    def close(self) -> None:
        self.transport.close()


def _sdk_sleep(delay: float) -> None:
    context: _CallContext = _local.context
    end = time.monotonic() + delay
    while True:
        context.check()
        remaining = min(end, context.deadline) - time.monotonic()
        if remaining <= 0:
            return
        context.stopped.wait(min(_CANCEL_CHECK_SEC, remaining))


class _SdkClient:
    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        # 密钥仅交给 SDK 自有配置，不在适配器另存原文；导入与构造不发网络。
        import typesafe_sdk as sdk

        register_secret(api_key)
        guarded = _GuardedTransport(
            transport if transport is not None else httpx2.HTTPTransport(retries=0)
        )
        self._sdk: Any = sdk.TypeSafeClient(
            api_key=api_key,
            base_url=_origin(endpoint),
            retry=sdk.RetryPolicy(
                max_retries=MAX_RETRIES,
                timeout=REQUEST_TIMEOUT_SEC,
                backoff_initial=BACKOFF_INITIAL_SEC,
                backoff_max=BACKOFF_MAX_SEC,
                respect_retry_after=True,
            ),
            timeout=REQUEST_TIMEOUT_SEC,
            compression=False,
            http_client=httpx2.Client(
                transport=guarded,
                timeout=REQUEST_TIMEOUT_SEC,
                trust_env=False,
                follow_redirects=False,
            ),
        )
        # 锁定 0.7.5 的 Tenacity sleep seam；重试的判定、计数与执行仍全由 SDK 负责。
        self._sdk._retry.sleep = _sdk_sleep

    def call(
        self, *, model: str, state: dict[str, object], questions: dict[str, QuestionSpec]
    ) -> SystemOneResponse:
        import typesafe_sdk as sdk

        previous = getattr(_local, "context", None)
        if previous is None:
            _local.context = _CallContext(
                None, threading.Event(), time.monotonic() + REQUEST_TIMEOUT_SEC
            )
        _protect_transport_logs()
        try:
            _local.context.check()
            result = self._sdk.system_one(
                model=model,
                state=state,
                questions={
                    name: sdk.Noul(
                        instructions=q.instructions,
                        criteria=sdk.NoulCriteria(true=q.true_text, false=q.false_text),
                    )
                    for name, q in questions.items()
                },
            )
            _local.context.check()
            # SDK 会忽略未来的答案类型，故同时检查原 wire 的键集合和 Noul 类型。
            raw = result.raw_http_response.json()
            if (
                not isinstance(raw, dict)
                or not isinstance(raw.get("answers"), dict)
                or set(raw["answers"]) != set(questions)
                or any(
                    not isinstance(v, dict) or v.get("type") != "noul"
                    for v in raw["answers"].values()
                )
            ):
                raise EngineError(ErrorCode.MODEL_ERROR, detail="INCOMPLETE_RESPONSE")
            response = SystemOneResponse(
                result.model,
                {name: answer.noul for name, answer in result.answers.items()},
                result.usage.input_tokens,
                result.usage.output_tokens,
            )
            _validate_response(response, model, questions)
            return response
        finally:
            _local.context = previous

    def close(self) -> None:
        self._sdk.close()


def sdk_client_factory(
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    transport: httpx2.BaseTransport | None = None,
) -> Callable[[str], SystemOneClient]:
    origin = _origin(endpoint)
    return lambda key: _SdkClient(key, endpoint=origin, transport=transport)


def _validate_response(
    response: SystemOneResponse,
    model: str,
    questions: Mapping[str, QuestionSpec],
) -> None:
    if response.model != model:
        raise EngineError(ErrorCode.MODEL_ERROR, detail="MODEL_MISMATCH")
    try:
        if set(response.answers) != set(questions):
            raise ValueError("answer keys differ")
        for value in response.answers.values():
            validate_probability(value)
        validate_count(response.input_tokens)
        validate_count(response.output_tokens)
    except (TypeError, ValueError):
        raise EngineError(ErrorCode.MODEL_ERROR, detail="INCOMPLETE_RESPONSE") from None


@dataclass(frozen=True)
class _Request:
    state: dict[str, object]
    questions: dict[str, QuestionSpec]
    pairs: tuple[tuple[int, PairInput], ...] = ()


def _score_request(company: str, pairs: Sequence[tuple[int, PairInput]]) -> _Request:
    theses = [pair.thesis for _, pair in pairs]
    states = {}
    for thesis in theses:
        value = {"thesis": thesis.statement}
        if thesis.kill_condition is not None:
            value["kill_condition"] = thesis.kill_condition
        states[thesis.ref] = value
    return _Request(
        {"company": company, "document": pairs[0][1].passage.text, "theses": states},
        question_set.build_score_questions(theses, flavor="direct"),
        tuple(pairs),
    )


def _requests(company: str, pairs: Sequence[PairInput]) -> list[_Request]:
    validate_count(len(pairs), minimum=1)
    if not isinstance(company, str) or not company.strip():
        raise ValueError("company must be nonempty")
    identities: dict[str, ThesisInput] = {}
    refs: dict[str, str] = {}
    passages: dict[str, PassageInput] = {}
    seen = set()
    grouped: dict[str, list[tuple[int, PairInput]]] = {}
    for index, pair in enumerate(pairs):
        t, p = pair.thesis, pair.passage
        t.__post_init__()
        p.__post_init__()
        if t.thesis_id in identities and identities[t.thesis_id] != t:
            raise ValueError("inconsistent thesis version/ref/hash/content")
        if t.ref in refs and refs[t.ref] != t.thesis_id:
            raise ValueError("thesis ref collision")
        if p.passage_id in passages and passages[p.passage_id] != p:
            raise ValueError("inconsistent passage hash/content")
        key = (t.thesis_id, t.version, p.passage_id)
        if key in seen:
            raise ValueError("duplicate pair")
        seen.add(key)
        identities[t.thesis_id], refs[t.ref], passages[p.passage_id] = t, t.thesis_id, p
        grouped.setdefault(p.passage_id, []).append((index, pair))
    validate_count(len(identities), maximum=question_set.MAX_THESES)
    requests: list[_Request] = []
    for passage_id in sorted(grouped):
        group = sorted(grouped[passage_id], key=lambda item: item[1].thesis.ref)
        chunks = [group] if question_set.PACK_THESES else [[item] for item in group]
        requests.extend(_score_request(company, chunk) for chunk in chunks)
    return requests


@dataclass
class _Invocation:
    request: _Request
    context: _CallContext
    started: float
    responses: list[tuple[_Request, SystemOneResponse]] = field(default_factory=list)
    latency_ms: int = 0
    error: SentinelError | None = None
    done: bool = False


class JevDirectEngine:
    name: Literal["jev_direct"] = "jev_direct"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str,
        client_factory: Callable[[str], SystemOneClient] | None = None,
        max_workers: int = JEV_CONCURRENCY,
        endpoint: str = DEFAULT_ENDPOINT,
    ) -> None:
        validate_count(max_workers, minimum=1, maximum=JEV_CONCURRENCY)
        if (
            not isinstance(model_id, str)
            or re.fullmatch(r"jev-[0-9]+\.[0-9]+\.[0-9]+", model_id) is None
        ):
            raise ValueError("model_id must be a fixed Jev version")
        origin = _origin(endpoint)
        self.model_id, self.max_workers = model_id, max_workers
        self._condition = threading.Condition()
        self._active = 0
        self._degraded = False
        self._client: SystemOneClient | None = None
        key = api_key.strip() if isinstance(api_key, str) else ""
        if key and key.isascii() and key.isprintable() and not any(c.isspace() for c in key):
            register_secret(key)
            self._client = (client_factory or sdk_client_factory(endpoint=origin))(key)

    def health(self) -> EngineHealth:
        with self._condition:
            if self._client is None:
                return EngineHealth(
                    "unconfigured", render("error.CONFIG_REQUIRED", {"missing": ["jevKey"]})
                )
            if self._degraded:
                return EngineHealth("degraded", render("error.UNAUTHENTICATED"))
            return EngineHealth("ok", "")

    def _invoke(self, invocation: _Invocation) -> None:
        _local.context = invocation.context
        try:
            invocation.context.check()
            assert self._client is not None
            request = invocation.request
            try:
                response = self._client.call(
                    model=self.model_id, state=request.state, questions=request.questions
                )
            except Exception as exc:
                if not _context_limit(exc) or len(request.pairs) < CONTEXT_RETRY_MIN_THESES:
                    raise
                midpoint = len(request.pairs) // 2
                # 仅拆分一次，不丢弃任何 pair；子请求共享原请求截止。
                for half in (request.pairs[:midpoint], request.pairs[midpoint:]):
                    invocation.context.check()
                    child = _score_request(str(request.state["company"]), half)
                    result = self._client.call(
                        model=self.model_id, state=child.state, questions=child.questions
                    )
                    _validate_response(result, self.model_id, child.questions)
                    invocation.responses.append((child, result))
            else:
                _validate_response(response, self.model_id, request.questions)
                invocation.responses.append((request, response))
            invocation.context.check()
            invocation.latency_ms = max(0, int((time.monotonic() - invocation.started) * 1000))
        except BaseException as exc:
            # daemon 中的失败必须唤醒消费者；原异常及 traceback 不跨线程保存。
            error = map_sdk_exception(exc)
            with self._condition:
                invocation.error = error
                invocation.context.stopped.set()
                if error.code == ErrorCode.UNAUTHENTICATED:
                    self._degraded = True
        finally:
            _local.context = None
            with self._condition:
                invocation.done = True
                self._active -= 1
                self._condition.notify_all()

    def _run(self, requests: Sequence[_Request], cancel: CancelToken) -> list[_Invocation]:
        cancel.raise_if_cancelled()
        if self._client is None:
            raise UserError(ErrorCode.CONFIG_REQUIRED, params={"missing": ["jevKey"]})
        stopped = threading.Event()
        invocations: list[_Invocation] = []
        next_request = 0
        capacity_deadline = time.monotonic() + REQUEST_TIMEOUT_SEC
        try:
            with self._condition:
                while True:
                    cancel.raise_if_cancelled()
                    errors = [item.error for item in invocations if item.error is not None]
                    if errors:
                        # 因失败停止的兄弟请求可能先退出；保留触发失败而非衍生取消。
                        raise next(
                            (e for e in errors if e.code != ErrorCode.CANCELLED), errors[0]
                        ) from None
                    for item in invocations:
                        if not item.done and time.monotonic() >= item.context.deadline:
                            raise EngineError(ErrorCode.TIMEOUT, reason="REQUEST_DEADLINE")
                    if next_request == len(requests) and all(item.done for item in invocations):
                        self._degraded = False
                        return invocations
                    if (
                        next_request < len(requests)
                        and self._active < self.max_workers
                        and not stopped.is_set()
                    ):
                        started = time.monotonic()
                        context = _CallContext(cancel, stopped, started + REQUEST_TIMEOUT_SEC)
                        invocation = _Invocation(requests[next_request], context, started)
                        self._active += 1
                        try:
                            threading.Thread(
                                target=self._invoke,
                                args=(invocation,),
                                daemon=True,
                                name="jev-direct-call",
                            ).start()
                        except Exception:
                            self._active -= 1
                            raise InternalError(reason="WORKER_START_FAILED") from None
                        invocations.append(invocation)
                        next_request += 1
                        capacity_deadline = started + REQUEST_TIMEOUT_SEC
                        continue
                    if next_request < len(requests) and time.monotonic() >= capacity_deadline:
                        raise EngineError(ErrorCode.TIMEOUT, reason="CAPACITY_DEADLINE")
                    # CancelToken 只有结构协议，无可等待的事件；Condition 阻塞等待并有界复查。
                    self._condition.wait(_CANCEL_CHECK_SEC)
        finally:
            stopped.set()
            with self._condition:
                self._condition.notify_all()

    def score_pairs(
        self,
        company: str,
        pairs: Sequence[PairInput],
        cancel: CancelToken,
    ) -> list[PairScore]:
        cancel.raise_if_cancelled()
        invocations = self._run(_requests(company, pairs), cancel)
        scores: dict[int, PairScore] = {}
        for invocation in invocations:
            for request, response in invocation.responses:
                allocations = allocate_tokens(response.input_tokens, len(request.pairs))
                for (index, pair), tokens in zip(request.pairs, allocations, strict=True):
                    ref = pair.thesis.ref
                    p = response.answers
                    probabilities = Probabilities(
                        p[f"{ref}__relevant"],
                        p[f"{ref}__against"],
                        p[f"{ref}__contradicts"],
                        p[f"{ref}__kill_met"] if pair.thesis.kill_condition is not None else None,
                        p[f"{ref}__supports"],
                    )
                    scores[index] = PairScore(
                        pair.thesis.thesis_id,
                        pair.thesis.version,
                        pair.passage.passage_id,
                        probabilities,
                        self.model_id,
                        tokens,
                        False,
                        invocation.latency_ms,
                    )
        cancel.raise_if_cancelled()
        if len(scores) != len(pairs):
            raise EngineError(ErrorCode.MODEL_ERROR, detail="INCOMPLETE_RESPONSE")
        return [scores[i] for i in range(len(pairs))]

    def score_event(
        self,
        company: str,
        theses: Sequence[ThesisInput],
        passages: Sequence[PassageInput],
        cancel: CancelToken,
    ) -> list[PairScore]:
        return self.score_pairs(company, cartesian_pairs(theses, passages), cancel)

    def locate_evidence(
        self,
        thesis: ThesisInput,
        relation: Relation,
        sentences: Sequence[str],
        cancel: CancelToken,
    ) -> EvidenceScore:
        cancel.raise_if_cancelled()
        thesis.__post_init__()
        questions = question_set.build_evidence_questions(
            relation,
            len(sentences),
            has_kill=thesis.kill_condition is not None,
            flavor="direct",
        )
        if any(
            not isinstance(s, str) or not s.strip() or len(s) > question_set.MAX_PASSAGE_CHARS
            for s in sentences
        ):
            raise ValueError("invalid evidence sentence")
        state: dict[str, object] = {
            "thesis": thesis.statement,
            "sentences": {f"s{i}": s for i, s in enumerate(sentences, 1)},
        }
        if thesis.kill_condition is not None:
            state["kill_condition"] = thesis.kill_condition
        invocation = self._run([_Request(state, questions)], cancel)[0]
        response = invocation.responses[0][1]
        cancel.raise_if_cancelled()
        return EvidenceScore(
            [response.answers[f"s{i}"] for i in range(1, len(sentences) + 1)],
            self.model_id,
            response.input_tokens,
            False,
        )
