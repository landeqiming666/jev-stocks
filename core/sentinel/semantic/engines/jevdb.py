from __future__ import annotations

import ipaddress
import logging
import math
import os
import re
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, cast
from urllib.parse import urlsplit

import duckdb

from sentinel.domain.classify import Probabilities, Relation
from sentinel.errors import (
    CancelledError,
    EngineError,
    ErrorCode,
    SentinelError,
    SourceError,
    UserError,
)
from sentinel.ids import new_id
from sentinel.messages import render
from sentinel.semantic import questions
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
from sentinel.semantic.budget import estimate_tokens
from sentinel.semantic.questions import QuestionSpec

DUCKDB_VERSION = "1.4.3"
BATCH_KEY = "batch"
JEVDB_THREADS, DUCKDB_THREADS = 4, 1
JEVDB_MAX_RETRIES = 3
JEVDB_RETRY_MAX_DELAY, JEVDB_RETRY_AFTER_MAX = 30, 300
JEVDB_TIMEOUT_SEC = 60
DEFAULT_RETRY_AFTER_SEC = 30
DEFAULT_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
_POLL_SEC = 0.02
_ENV_LOCK = threading.RLock()
_LOG = logging.getLogger(__name__)
_SETTINGS = (
    ("jevdb_backend", "jev"),
    ("jevdb_threads", JEVDB_THREADS),
    ("jevdb_max_retries", JEVDB_MAX_RETRIES),
    ("jevdb_retry_max_delay", JEVDB_RETRY_MAX_DELAY),
    ("jevdb_retry_after_max", JEVDB_RETRY_AFTER_MAX),
    ("jevdb_on_error", "error"),
    ("jevdb_timeout", JEVDB_TIMEOUT_SEC),
    ("threads", DUCKDB_THREADS),
    ("jevdb_dump_path", ""),
    ("jevdb_raw_dump_path", ""),
    ("jevdb_cascade_model", ""),
)


class DuckDBConnection(Protocol):
    description: Any

    def execute(self, query: str, parameters: Any = None) -> DuckDBConnection: ...
    def executemany(self, query: str, parameters: Iterable[Sequence[Any]]) -> DuckDBConnection: ...
    def fetchall(self) -> list[tuple[Any, ...]]: ...
    def fetchone(self) -> tuple[Any, ...] | None: ...
    def interrupt(self) -> None: ...
    def close(self) -> None: ...


def _endpoint_prefix(endpoint: str) -> str:
    try:
        if (
            not isinstance(endpoint, str)
            or len(endpoint) > 2048
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in endpoint)
            or "?" in endpoint
            or "#" in endpoint
        ):
            raise ValueError()
        parts = urlsplit(endpoint)
        host, port = parts.hostname, parts.port
        if (
            parts.scheme != "https"
            or not host
            or len(host) > 253
            or "@" in parts.netloc
            or parts.netloc.endswith(":")
            or parts.path != "/v1/systemone"
            or port is not None
            and not 1 <= port <= 65535
        ):
            raise ValueError()
        if ":" in host:
            if "%" in host:
                raise ValueError()
            host = f"[{ipaddress.IPv6Address(host).compressed}]"
        elif all(label.isdigit() for label in host.split(".")):
            host = str(ipaddress.IPv4Address(host))
        elif any(
            not re.fullmatch(r"(?!-)[a-zA-Z0-9-]{1,63}(?<!-)", label) for label in host.split(".")
        ):
            raise ValueError()
        return f"https://{host if port is None else f'{host}:{port}'}/v1/"
    except (TypeError, ValueError):
        raise ValueError("invalid JEV endpoint") from None


def _suffix(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[a-z0-9_]{1,20}", value) is None:
        raise ValueError("invalid table suffix")


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _specs(question_set: dict[str, QuestionSpec]) -> dict[str, QuestionSpec]:
    specs: dict[str, QuestionSpec] = {}
    for name, spec in question_set.items():
        questions.validate_question_name(name)
        if not isinstance(spec, QuestionSpec) or any(
            marker in spec.instructions for marker in ("theses.", "sentences.", "{", "}")
        ):
            raise ValueError("invalid JEVDB question")
        key = name.split("__")[-1]
        if key in specs and specs[key] != spec:
            raise ValueError("inconsistent JEVDB templates")
        specs[key] = spec
    return specs


def build_score_sql(question_set: dict[str, QuestionSpec], table_suffix: str) -> str:
    _suffix(table_suffix)
    specs = _specs(question_set)
    if set(specs) - set(questions.QUESTION_KEYS) or any(
        key not in specs for key in ("relevant", "against", "contradicts", "supports")
    ):
        raise ValueError("incomplete score questions")
    fields = []
    for key in questions.QUESTION_KEYS:
        if key not in specs:
            expression = "CAST(NULL AS DOUBLE)"
        else:
            left = "{'thesis': th.thesis}"
            if key == "kill_met":
                left = "{'thesis': th.thesis, 'kill_condition': th.kill_condition}"
            expression = (
                f"jev_probability({_literal(specs[key].instructions)}, "
                f"{left}, {{'document': th.document}})"
            )
        fields.append(f"{expression} AS p_{key}")
    # 物化实体对将普通连接固定在概率投影之前，避免缓存缺失对变成完整笛卡尔积。
    return (
        "WITH selected AS MATERIALIZED (\n"
        " SELECT th.ref, ps.pid, th.thesis, th.kill_condition, ps.document\n"
        f" FROM th_{table_suffix} th JOIN wanted_{table_suffix} w ON th.ref = w.ref\n"
        f" JOIN ps_{table_suffix} ps ON ps.pid = w.pid\n"
        " WHERE jev_keys_overlap(th.keys, ps.keys)\n"
        ")\nSELECT th.ref, th.pid, " + ",\n".join(fields) + "\nFROM selected th"
    )


def build_evidence_sql(question_set: dict[str, QuestionSpec], table_suffix: str) -> str:
    _suffix(table_suffix)
    specs = _specs(question_set)
    if not specs or any(re.fullmatch(r"s[1-9][0-9]*", key) is None for key in specs):
        raise ValueError("invalid evidence questions")
    template = next(iter(specs.values()))
    if any(spec != template for spec in specs.values()):
        raise ValueError("inconsistent evidence questions")
    left = "{'thesis': ev.thesis}"
    if "`kill_condition`" in template.instructions:
        left = "{'thesis': ev.thesis, 'kill_condition': ev.kill_condition}"
    return (
        f"SELECT ev.sid, jev_probability({_literal(template.instructions)}, "
        f"{left}, {{'document': ev.sentence}}) AS p_evidence FROM ev_{table_suffix} ev"
    )


def map_jevdb_error(message: str) -> EngineError:
    # 上游可在异常 body 中带回 key/原文；仅发布分类和可验证的等待秒数。
    for status, reason in (("401", "INVALID_KEY"), ("403", "FORBIDDEN")):
        if re.search(rf"\b{status}\b", message):
            return EngineError(ErrorCode.UNAUTHENTICATED, reason=reason)
    if re.search(r"\b429\b", message):
        match = re.search(r"retry[-_ ]after(?:sec)?\s*[:=]\s*(\d+)\b", message, re.I)
        seconds = min(int(match[1]), JEVDB_RETRY_AFTER_MAX) if match else DEFAULT_RETRY_AFTER_SEC
        return EngineError(ErrorCode.RATE_LIMITED, params={"retryAfterSec": seconds})
    if "timeout" in message.lower() or "timed out" in message.lower():
        return EngineError(ErrorCode.TIMEOUT)
    return EngineError(ErrorCode.MODEL_ERROR)


@dataclass
class _Job[T]:
    done: threading.Event = field(default_factory=threading.Event)
    stop: threading.Event = field(default_factory=threading.Event)
    value: T | None = None
    error: SentinelError | None = None
    interrupted: bool = False


class JevdbEngine:
    name: Literal["jevdb"] = "jevdb"

    def __init__(
        self,
        *,
        extension_path: Path,
        model_id: str,
        secret_provider: Callable[[], str],
        connection_factory: Callable[..., DuckDBConnection] | None = None,
        endpoint: str | None = None,
    ) -> None:
        if not isinstance(model_id, str) or not re.fullmatch(
            r"jev-[0-9]+\.[0-9]+\.[0-9]+", model_id
        ):
            raise ValueError("model_id must be a fixed Jev version")
        self.extension_path, self.model_id = extension_path, model_id
        self.secret_provider = secret_provider
        self._endpoint = _endpoint_prefix(DEFAULT_ENDPOINT if endpoint is None else endpoint)
        self._factory = connection_factory or cast(Callable[..., DuckDBConnection], duckdb.connect)
        self._lock = threading.RLock()
        self._connection: DuckDBConnection | None = None
        self._job: _Job[Any] | None = None
        self._closed = self._closing = self._degraded = False

    def _key(self) -> str:
        try:
            key = self.secret_provider()
        except Exception:
            raise UserError(ErrorCode.CONFIG_REQUIRED, params={"missing": ["jevKey"]}) from None
        return (
            key
            if (
                isinstance(key, str)
                and key
                and key.isascii()
                and key.isprintable()
                and not any(c.isspace() for c in key)
            )
            else ""
        )

    @staticmethod
    def _check(cancel: CancelToken | None, stop: threading.Event, deadline: float) -> None:
        if cancel is not None:
            cancel.raise_if_cancelled()
        if stop.is_set():
            raise CancelledError()
        if time.monotonic() >= deadline:
            raise EngineError(ErrorCode.TIMEOUT)

    def _acquire(self, cancel: CancelToken | None, deadline: float) -> None:
        while True:
            if cancel is not None:
                cancel.raise_if_cancelled()
            if time.monotonic() >= deadline:
                raise EngineError(ErrorCode.TIMEOUT, reason="CAPACITY_DEADLINE")
            if self._lock.acquire(timeout=_POLL_SEC):
                return

    def _interrupt(self, job: _Job[Any]) -> None:
        job.stop.set()
        if job.interrupted or job.done.is_set():
            return
        job.interrupted = True
        if self._connection is not None:
            with suppress(Exception):
                self._connection.interrupt()

    def _run[T](
        self, work: Callable[[threading.Event, float], T], cancel: CancelToken | None = None
    ) -> T:
        deadline = time.monotonic() + JEVDB_TIMEOUT_SEC
        self._acquire(cancel, deadline)
        try:
            if self._closed or self._closing:
                raise EngineError(ErrorCode.ENGINE_UNAVAILABLE, reason="CLOSED")
            while self._job is not None and not self._job.done.is_set():
                self._check(cancel, threading.Event(), deadline)
                self._job.done.wait(_POLL_SEC)
            self._check(cancel, threading.Event(), deadline)
            job: _Job[T] = _Job()
            self._job = job

            def invoke() -> None:
                try:
                    job.value = work(job.stop, deadline)
                except SentinelError as error:
                    # 原始异常链和 traceback 局部变量可能留有 key，不交给实例保存。
                    error.__traceback__ = error.__context__ = error.__cause__ = None
                    job.error = error
                except Exception:
                    job.error = EngineError(ErrorCode.MODEL_ERROR)
                finally:
                    if self._closing:
                        self._dispose()
                    job.done.set()

            try:
                threading.Thread(target=invoke, name="jevdb-call", daemon=True).start()
            except Exception:
                job.done.set()
                raise EngineError(
                    ErrorCode.ENGINE_UNAVAILABLE, reason="WORKER_START_FAILED"
                ) from None
            try:
                while not job.done.wait(_POLL_SEC):
                    self._check(cancel, job.stop, deadline)
                self._check(cancel, job.stop, deadline)
            except SentinelError:
                self._interrupt(job)
                raise
            if job.error is not None:
                self._degraded = True
                raise job.error from None
            self._degraded = False
            return cast(T, job.value)
        finally:
            self._lock.release()

    def _dispose(self) -> None:
        con, self._connection = self._connection, None
        if con is not None:
            try:
                con.execute("DROP SECRET IF EXISTS jev")
            except Exception:
                pass
            finally:
                try:
                    con.close()
                except Exception:
                    _LOG.debug("jevdb connection cleanup failed")

    def _load(self, stop: threading.Event, deadline: float) -> None:
        if self._connection is not None:
            return
        path = self.extension_path
        if (
            duckdb.__version__ != DUCKDB_VERSION
            or not isinstance(path, Path)
            or not path.is_absolute()
            or not path.is_file()
            or path.suffix != ".duckdb_extension"
            or any(c in str(path) for c in ("'", '"', "\r", "\n", "\0"))
        ):
            raise EngineError(ErrorCode.ENGINE_UNAVAILABLE, reason="EXTENSION_PATH_OR_ABI")
        self._check(None, stop, deadline)
        try:
            self._connection = self._factory(
                ":memory:", config={"allow_unsigned_extensions": "true"}
            )
            self._check(None, stop, deadline)
            self._connection.execute(f"LOAD '{path}'")
            self._connection.execute("SET jevdb_model = ?", [self.model_id])
            self._connection.execute("SET jevdb_endpoint = ?", [self._endpoint])
            for name, value in _SETTINGS:
                self._check(None, stop, deadline)
                self._connection.execute(f"SET {name} = ?", [value])
        except SentinelError:
            self._dispose()
            raise
        except Exception:
            self._dispose()
            raise EngineError(ErrorCode.ENGINE_UNAVAILABLE, reason="EXTENSION_LOAD") from None

    def load(self) -> None:
        self._run(self._load)

    def health(self) -> EngineHealth:
        deadline = time.monotonic() + JEVDB_TIMEOUT_SEC
        self._acquire(None, deadline)
        try:
            if (
                self._closed
                or self._closing
                or (self._job is not None and not self._job.done.is_set())
            ):
                return EngineHealth("degraded", render("error.ENGINE_UNAVAILABLE"))
            try:
                key = self._key()
            except UserError:
                key = ""
            if not key:
                return EngineHealth(
                    "unconfigured", render("error.CONFIG_REQUIRED", {"missing": ["jevKey"]})
                )
            if self._degraded:
                return EngineHealth("degraded", render("error.ENGINE_UNAVAILABLE"))
            return EngineHealth("ok", "")
        finally:
            self._lock.release()

    def close(self) -> None:
        deadline = time.monotonic() + JEVDB_TIMEOUT_SEC
        self._acquire(None, deadline)
        try:
            if self._closed:
                return
            self._closing = True
            job = self._job
            if job is not None and not job.done.is_set():
                self._interrupt(job)
                while not job.done.wait(_POLL_SEC):
                    if time.monotonic() >= deadline:
                        return
            if self._connection is not None:
                disposal: _Job[None] = _Job()
                self._job = disposal

                def dispose() -> None:
                    try:
                        self._dispose()
                    finally:
                        disposal.done.set()

                try:
                    threading.Thread(target=dispose, name="jevdb-close", daemon=True).start()
                except Exception:
                    disposal.done.set()
                    raise EngineError(
                        ErrorCode.ENGINE_UNAVAILABLE, reason="CLEANUP_WORKER_START_FAILED"
                    ) from None
                self._closed = True
                while not disposal.done.wait(_POLL_SEC):
                    if time.monotonic() >= deadline:
                        return
            self._closed = True
        finally:
            self._lock.release()

    def _secret(
        self, con: DuckDBConnection, cancel: CancelToken, stop: threading.Event, deadline: float
    ) -> None:
        self._check(cancel, stop, deadline)
        key = self._key()
        if not key:
            raise UserError(ErrorCode.CONFIG_REQUIRED, params={"missing": ["jevKey"]})
        if os.environ.get("SENTINEL_OFFLINE") == "1":
            raise SourceError(ErrorCode.SOURCE_UNAVAILABLE, reason="OFFLINE")
        while not _ENV_LOCK.acquire(timeout=_POLL_SEC):
            self._check(cancel, stop, deadline)
        try:
            self._check(cancel, stop, deadline)
            previous = os.environ.get("JEV_API_KEY")
            try:
                os.environ["JEV_API_KEY"] = key
                con.execute("CREATE SECRET jev (TYPE jev, PROVIDER env)")
            finally:
                if previous is None:
                    os.environ.pop("JEV_API_KEY", None)
                else:
                    os.environ["JEV_API_KEY"] = previous
        finally:
            _ENV_LOCK.release()

    def _stats(self, con: DuckDBConnection) -> None:
        try:
            result = con.execute("SELECT * FROM jevdb_stats()")
            row = result.fetchone()
            if row is None:
                return
            stats = {
                column[0]: value
                for column, value in zip(result.description, row, strict=True)
                if isinstance(column[0], str)
                and re.fullmatch(r"[a-z_]+", column[0])
                and (value is None or type(value) in (int, float) and math.isfinite(value))
            }
            _LOG.debug("jevdb_stats %s", stats)
        except Exception:
            _LOG.debug("jevdb stats unavailable")

    def _cleanup(self, con: DuckDBConnection, tables: Sequence[str]) -> None:
        failed = False
        for sql in [
            *(f"DROP TABLE IF EXISTS {table}" for table in tables),
            "DROP SECRET IF EXISTS jev",
        ]:
            try:
                con.execute(sql)
            except Exception:
                failed = True
        if failed:
            self._dispose()
            raise EngineError(ErrorCode.MODEL_ERROR, reason="CLEANUP_FAILED")

    def score_pairs(
        self, company: str, pairs: Sequence[PairInput], cancel: CancelToken
    ) -> list[PairScore]:
        cancel.raise_if_cancelled()
        if not isinstance(company, str) or not company.strip():
            raise ValueError("company must be nonempty")
        requested = tuple(pairs)
        if not requested:
            return []
        theses: dict[str, ThesisInput] = {}
        passages: dict[str, PassageInput] = {}
        for pair in requested:
            pair.thesis.__post_init__()
            pair.passage.__post_init__()
            th, ps = pair.thesis, pair.passage
            if (
                th.ref in theses
                and theses[th.ref] != th
                or (ps.passage_id in passages and passages[ps.passage_id] != ps)
            ):
                raise ValueError("conflicting input identity")
            theses[th.ref], passages[ps.passage_id] = th, ps
        question_set = questions.build_score_questions(list(theses.values()), flavor="jevdb")
        wanted = list(dict.fromkeys((p.thesis.ref, p.passage.passage_id) for p in requested))

        def work(stop: threading.Event, deadline: float) -> list[PairScore]:
            self._check(cancel, stop, deadline)
            self._load(stop, deadline)
            con = self._connection
            assert con is not None
            suffix = new_id().lower()[-20:]
            tables = [f"{prefix}_{suffix}" for prefix in ("th", "ps", "wanted")]
            try:
                self._secret(con, cancel, stop, deadline)
                con.execute(
                    f"CREATE TEMP TABLE {tables[0]} "
                    "(ref VARCHAR, thesis VARCHAR, kill_condition VARCHAR, keys VARCHAR[])"
                )
                con.execute(
                    f"CREATE TEMP TABLE {tables[1]} (pid VARCHAR, document VARCHAR, keys VARCHAR[])"
                )
                con.execute(f"CREATE TEMP TABLE {tables[2]} (ref VARCHAR, pid VARCHAR)")
                con.executemany(
                    f"INSERT INTO {tables[0]} VALUES (?, ?, ?, ?)",
                    [(t.ref, t.statement, t.kill_condition, [BATCH_KEY]) for t in theses.values()],
                )
                con.executemany(
                    f"INSERT INTO {tables[1]} VALUES (?, ?, ?)",
                    [(p.passage_id, p.text, [BATCH_KEY]) for p in passages.values()],
                )
                con.executemany(f"INSERT INTO {tables[2]} VALUES (?, ?)", wanted)
                self._check(cancel, stop, deadline)
                if os.environ.get("SENTINEL_OFFLINE") == "1":
                    raise SourceError(ErrorCode.SOURCE_UNAVAILABLE, reason="OFFLINE")
                started = time.monotonic()
                rows = con.execute(build_score_sql(question_set, suffix)).fetchall()
                latency = max(0, int((time.monotonic() - started) * 1000))
                self._check(cancel, stop, deadline)
                self._stats(con)
                values: dict[tuple[str, str], Probabilities] = {}
                for row in rows:
                    if len(row) != 7 or not isinstance(row[0], str) or not isinstance(row[1], str):
                        raise ValueError("invalid score row")
                    identity = row[0], row[1]
                    if identity not in wanted or identity in values:
                        raise ValueError("unexpected or duplicate score")
                    if (row[5] is None) != (theses[row[0]].kill_condition is None):
                        raise ValueError("invalid kill probability")
                    values[identity] = Probabilities(*row[2:])
                if set(values) != set(wanted):
                    raise ValueError("incomplete scores")
                result = []
                for pair in requested:
                    t, p = pair.thesis, pair.passage
                    chars = len(t.statement) + len(t.kill_condition or "") + len(p.text)
                    chars += sum(
                        len(q.instructions)
                        for name, q in question_set.items()
                        if name.startswith(t.ref + "__")
                    )
                    result.append(
                        PairScore(
                            t.thesis_id,
                            t.version,
                            p.passage_id,
                            values[t.ref, p.passage_id],
                            self.model_id,
                            estimate_tokens(chars),
                            True,
                            latency,
                        )
                    )
                return result
            except SentinelError:
                raise
            except Exception as error:
                raise map_jevdb_error(str(error)) from None
            finally:
                self._cleanup(con, tables)

        return self._run(work, cancel)

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
        thesis.__post_init__()
        sentence_list = tuple(sentences)
        question_set = questions.build_evidence_questions(
            relation, len(sentence_list), has_kill=thesis.kill_condition is not None, flavor="jevdb"
        )
        if any(
            not isinstance(s, str) or not s.strip() or len(s) > questions.MAX_PASSAGE_CHARS
            for s in sentence_list
        ):
            raise ValueError("invalid evidence sentence")

        def work(stop: threading.Event, deadline: float) -> EvidenceScore:
            self._check(cancel, stop, deadline)
            self._load(stop, deadline)
            con = self._connection
            assert con is not None
            suffix = new_id().lower()[-20:]
            table = f"ev_{suffix}"
            try:
                self._secret(con, cancel, stop, deadline)
                con.execute(
                    f"CREATE TEMP TABLE {table} "
                    "(sid VARCHAR, sentence VARCHAR, thesis VARCHAR, kill_condition VARCHAR)"
                )
                con.executemany(
                    f"INSERT INTO {table} VALUES (?, ?, ?, ?)",
                    [
                        (f"s{i}", s, thesis.statement, thesis.kill_condition)
                        for i, s in enumerate(sentence_list, 1)
                    ],
                )
                self._check(cancel, stop, deadline)
                if os.environ.get("SENTINEL_OFFLINE") == "1":
                    raise SourceError(ErrorCode.SOURCE_UNAVAILABLE, reason="OFFLINE")
                rows = con.execute(build_evidence_sql(question_set, suffix)).fetchall()
                self._check(cancel, stop, deadline)
                self._stats(con)
                probabilities: dict[str, float] = {}
                for row in rows:
                    if (
                        len(row) != 2
                        or not isinstance(row[0], str)
                        or row[0] not in question_set
                        or row[0] in probabilities
                    ):
                        raise ValueError("unexpected evidence row")
                    probabilities[row[0]] = row[1]
                if set(probabilities) != set(question_set):
                    raise ValueError("incomplete evidence")
                chars = sum(
                    len(s) + len(thesis.statement) + len(q.instructions)
                    for s, q in zip(sentence_list, question_set.values(), strict=True)
                )
                if relation == "overturn" and thesis.kill_condition is not None:
                    chars += len(thesis.kill_condition) * len(sentence_list)
                return EvidenceScore(
                    [probabilities[f"s{i}"] for i in range(1, len(sentence_list) + 1)],
                    self.model_id,
                    estimate_tokens(chars),
                    True,
                )
            except SentinelError:
                raise
            except Exception as error:
                raise map_jevdb_error(str(error)) from None
            finally:
                self._cleanup(con, [table])

        return self._run(work, cancel)
