"""M-8: recorded public SEC input, production RPC services, and real native inference."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import sys
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import duckdb  # noqa: E402
import httpx  # noqa: E402
from sentinel import clock  # noqa: E402
from sentinel.app.args import AppArgs  # noqa: E402
from sentinel.app.container import AppContainer, build_container  # noqa: E402
from sentinel.app.main import run  # noqa: E402
from sentinel.domain.contact import is_valid_sec_email  # noqa: E402
from sentinel.http import HttpClient  # noqa: E402
from sentinel.markets.instruments import InstrumentRepository, SecTickerSource  # noqa: E402
from sentinel.markets.instruments.normalize import normalize_symbol  # noqa: E402
from sentinel.markets.sec import SecFilingsClient  # noqa: E402
from sentinel.markets.sec.models import FilingRef  # noqa: E402
from sentinel.markets.sec.urls import validate_archive_url  # noqa: E402
from sentinel.scan.pending import InboxService  # noqa: E402
from sentinel.secrets import MemorySecretStore  # noqa: E402
from sentinel.security.redact import register_secret  # noqa: E402
from sentinel.semantic.questions import QUESTION_SET_VERSION  # noqa: E402
from sentinel.settings.models import SettingsPatch  # noqa: E402
from sentinel.storage import Database  # noqa: E402

MODEL_ID = "jev-1.14.0"
STATS_FIELDS = {"requests", "pairs", "records", "cache_hits", "input_tokens", "errors", "retries"}


def digest_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


class RecordedSecClient(HttpClient):
    def __init__(self) -> None:
        super().__init__()
        self.responses: dict[str, dict[str, object]] = {}

    def get(self, url: str, **kwargs: Any) -> Any:
        response = super().get(url, **kwargs)
        self.responses[url] = {
            "body": base64.b64encode(response.content).decode("ascii"),
            "sha256": hashlib.sha256(response.content).hexdigest(),
            "contentType": response.headers.get("content-type", "text/html; charset=utf-8"),
        }
        return response


def select_filing(refs: Sequence[FilingRef], accession: str | None) -> FilingRef:
    selected = [
        ref
        for ref in refs
        if (
            ref.accession == accession
            if accession
            else ref.form_type.startswith("8-K") and "2.02" in (ref.items or "").split(",")
        )
    ]
    if not selected:
        raise ValueError("no matching public SEC filing")
    return max(selected, key=lambda ref: (ref.published_at, ref.accession))


def prepare_case(
    directory: Path, *, symbol: str, statement: str, accession: str | None, token_budget: int
) -> dict[str, object]:
    if os.environ.get("SENTINEL_OFFLINE") == "1":
        raise ValueError("offline")
    email = os.environ.get("SENTINEL_SEC_CONTACT", "")
    if not is_valid_sec_email(email) or normalize_symbol(symbol) != symbol:
        raise ValueError("invalid SEC configuration")
    if not statement.strip() or len(statement.strip()) > 500:
        raise ValueError("invalid thesis")
    SettingsPatch(daily_token_budget=token_budget)
    if accession is not None and re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession) is None:
        raise ValueError("invalid accession")
    database = directory / "data" / "sentinel.duckdb"
    if database.exists():
        raise ValueError("live acceptance requires a fresh database")
    register_secret(email)
    database.parent.mkdir(parents=True, exist_ok=True)
    db = Database(database)
    db.open()
    try:
        db.migrate()
        with RecordedSecClient() as http:
            rows = [
                row
                for row in SecTickerSource(http, email_provider=lambda: email).fetch()
                if row.ticker == symbol
            ]
            if not rows:
                raise ValueError("symbol not present in SEC ticker response")
            repo = InstrumentRepository(db, resource_dir=ROOT / "resources")
            repo.replace_from_sec(rows, fetched_at=datetime.now(UTC), require_nonempty=True)
            instrument = repo.get("us:" + symbol)
            if instrument is None:
                raise ValueError("SEC instrument unavailable")
            client = SecFilingsClient(http, email_provider=lambda: email)
            now = datetime.now(UTC)
            refs = client.list_filings(instrument, now - timedelta(days=366), now, now)
            ref = select_filing(refs, accession)
            rows_index = client.fetch_index(ref)
            from sentinel.markets.sec.index import select_files

            selected, _ = select_files(
                rows_index,
                cik=ref.cik,
                accession=ref.accession,
                primary_document=ref.primary_document,
            )
            for item in selected:
                client.fetch_file(item.url)
            submissions_url = f"https://data.sec.gov/submissions/CIK{ref.cik}.json"
            original = http.responses[submissions_url]
            original_bytes = base64.b64decode(str(original["body"]))
            original_sha256 = hashlib.sha256(original_bytes).hexdigest()
            (directory / "sec-submissions-original.json").write_bytes(original_bytes)
            payload = json.loads(original_bytes)
            recent = payload["filings"]["recent"]
            index = recent["accessionNumber"].index(ref.accession)
            payload["filings"] = {
                "recent": {name: [values[index]] for name, values in recent.items()}
            }
            filtered = json.dumps(payload, ensure_ascii=False).encode()
            http.responses[submissions_url] = {
                **original,
                "originalSha256": original_sha256,
                "body": base64.b64encode(filtered).decode(),
                "sha256": hashlib.sha256(filtered).hexdigest(),
                "selection": "one original filing row; all original field values retained",
            }
            responses_path = directory / "sec-http.json"
            write_json(responses_path, http.responses)
            case: dict[str, object] = {
                "schemaVersion": "1",
                "source": "sec-live-snapshot",
                "httpMode": "recorded SEC HTTP, selected filing only",
                "capturedAt": clock.to_iso(now),
                "symbol": symbol,
                "instrumentId": instrument.instrument_id,
                "eventId": ref.event_id,
                "accession": ref.accession,
                "statement": statement.strip(),
                "tokenBudget": token_budget,
                "clock": clock.to_iso(ref.published_at + timedelta(seconds=1)),
                "from": clock.to_iso(ref.published_at - timedelta(seconds=1)),
                "httpSha256": digest_file(responses_path),
                "submissionsUrl": submissions_url,
                "submissionsSha256": original_sha256,
                "modelId": MODEL_ID,
                "questionSetVersion": QUESTION_SET_VERSION,
                "nativeCriteriaEquivalence": "NOT_RUN (F18-S04-CR-01)",
            }
            write_json(directory / "case.json", case)
            return case
    finally:
        db.close()


def replay_transport(directory: Path) -> httpx.MockTransport:
    case = json.loads((directory / "case.json").read_text())
    path = directory / "sec-http.json"
    if digest_file(path) != case["httpSha256"]:
        raise ValueError("SEC snapshot checksum mismatch")
    responses = json.loads(path.read_text())

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method != "GET" or str(request.url) not in responses:
            raise ValueError("request absent from recorded SEC snapshot")
        row = responses[str(request.url)]
        content = base64.b64decode(row["body"], validate=True)
        if hashlib.sha256(content).hexdigest() != row["sha256"]:
            raise ValueError("SEC response checksum mismatch")
        if request.url.host not in {"www.sec.gov", "data.sec.gov"}:
            raise ValueError("non-SEC snapshot URL")
        return httpx.Response(200, content=content, headers={"content-type": row["contentType"]})

    return httpx.MockTransport(respond)


class AuditedConnection:
    def __init__(self, directory: Path, *args: Any, **kwargs: Any) -> None:
        self.connection = duckdb.connect(*args, **kwargs)
        self.directory = directory
        self.query: str | None = None
        self.query_path: Path | None = None

    @property
    def description(self) -> Any:
        return self.connection.description

    def execute(self, query: str, parameters: Any = None) -> AuditedConnection:
        self.query = query if "jev_probability(" in query else None
        self.query_path = None
        if self.query is not None:
            self.directory.mkdir(parents=True, exist_ok=True)
            sequence = len(list(self.directory.glob("query-*.sql"))) + 1
            self.query_path = self.directory / f"query-{sequence:04d}.sql"
            self.query_path.write_text(query, encoding="utf-8")
            write_json(self.query_path.with_suffix(".error.json"), {"status": "pending"})
        try:
            self.connection.execute(query, parameters)
        except Exception as error:
            if self.query_path is not None:
                write_json(
                    self.query_path.with_suffix(".error.json"),
                    {"status": "failed", "errorType": type(error).__name__},
                )
            raise
        return self

    def executemany(self, query: str, parameters: Iterable[Sequence[Any]]) -> AuditedConnection:
        self.query = None
        self.query_path = None
        self.connection.executemany(query, parameters)
        return self

    def fetchall(self) -> list[tuple[Any, ...]]:
        rows = self.connection.fetchall()
        if self.query is not None:
            self.query = None
            result = self.connection.execute("SELECT * FROM jevdb_stats()")
            stats_row = result.fetchone()
            stats = {
                column[0]: value
                for column, value in zip(result.description or [], stats_row or (), strict=True)
                if column[0] in STATS_FIELDS
                and type(value) in (int, float)
                and math.isfinite(value)
            }
            assert self.query_path is not None
            write_json(self.query_path.with_suffix(".stats.json"), stats)
            self.query_path.with_suffix(".error.json").unlink()
        return rows

    def fetchone(self) -> Any:
        return self.connection.fetchone()

    def interrupt(self) -> None:
        self.connection.interrupt()

    def close(self) -> None:
        self.connection.close()


def serve_case(directory: Path) -> int:
    key, email = os.environ.get("JEV_API_KEY", ""), os.environ.get("SENTINEL_SEC_CONTACT", "")
    if os.environ.get("SENTINEL_OFFLINE") == "1" or not key or not is_valid_sec_email(email):
        raise ValueError("live configuration required")
    case = json.loads((directory / "case.json").read_text())
    os.environ["SENTINEL_CLOCK"] = case["clock"]
    extension = Path(os.environ.get("SENTINEL_JEVDB_PATH", "")).expanduser().resolve()
    if not extension.is_file():
        raise ValueError("native extension required")
    write_json(
        directory / "runtime.json",
        {
            "extensionSha256": digest_file(extension),
            "duckdbVersion": duckdb.__version__,
            "engine": "jevdb",
            "modelId": MODEL_ID,
            "questionSetVersion": QUESTION_SET_VERSION,
        },
    )
    register_secret(email)
    register_secret(key)

    def factory(args: AppArgs) -> AppContainer:
        store = MemorySecretStore()
        http = HttpClient(transport=replay_transport(directory))
        container = build_container(
            args,
            secret_store=store,
            http_client=http,
            jevdb_connection_factory=lambda *args, **kwargs: AuditedConnection(
                directory / "audit", *args, **kwargs
            ),
        )
        try:
            container.secrets.set_jev_key(key)
            container.settings.update(
                SettingsPatch(
                    engine="jevdb",
                    sec_contact_email=email,
                    daily_token_budget=case["tokenBudget"],
                )
            )
            return container
        except Exception:
            container.close()
            raise

    output = os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0)
    sys.stdout.flush()
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    try:
        return run(
            ["--data-dir", str(directory / "data"), "--resource-dir", str(ROOT / "resources")],
            stdout=output,
            container_factory=factory,
        )
    finally:
        output.close()


def validate_evidence(directory: Path, extension: Path) -> dict[str, object]:
    required = (
        "case.json",
        "result.json",
        "runtime.json",
        "sec-http.json",
        "sec-submissions-original.json",
    )
    missing = [name for name in required if not (directory / name).is_file()]
    if missing:
        raise ValueError(f"missing evidence files: {', '.join(missing)}")
    case = json.loads((directory / "case.json").read_text())
    result = json.loads((directory / "result.json").read_text())
    runtime = json.loads((directory / "runtime.json").read_text())
    if runtime != {
        "extensionSha256": digest_file(extension),
        "duckdbVersion": "1.4.3",
        "engine": "jevdb",
        "modelId": MODEL_ID,
        "questionSetVersion": QUESTION_SET_VERSION,
    }:
        raise ValueError("native runtime changed or unverified")
    responses = json.loads((directory / "sec-http.json").read_text())
    submissions_url = case.get("submissionsUrl")
    submissions_sha256 = case.get("submissionsSha256")
    if (
        case["source"] != "sec-live-snapshot"
        or digest_file(directory / "sec-http.json") != case["httpSha256"]
        or not isinstance(submissions_url, str)
        or not isinstance(submissions_sha256, str)
    ):
        raise ValueError("missing public SEC snapshot")
    original = directory / "sec-submissions-original.json"
    if digest_file(original) != submissions_sha256:
        raise ValueError("original SEC submissions checksum changed")
    recorded = responses.get(submissions_url)
    if not isinstance(recorded, dict) or recorded.get("originalSha256") != submissions_sha256:
        raise ValueError("recorded SEC submissions hash mismatch")
    filtered = json.loads(base64.b64decode(str(recorded["body"]), validate=True))
    if filtered["filings"]["recent"]["accessionNumber"] != [case["accession"]]:
        raise ValueError("SEC snapshot contains unrelated filings")
    if (
        result["bootstrap"]["engine"]["requested"] != "jevdb"
        or result["bootstrap"]["engine"]["active"] != "jevdb"
    ):
        raise ValueError("engine fallback")
    scan = result["scan"]
    detail = result["detail"]
    if scan["status"] != "succeeded" or scan["engine"] != "jevdb" or scan["stats"]["filings"] != 1:
        raise ValueError("scan incomplete")
    if not scan["stats"]["requests"] or not scan["stats"]["decisions"]:
        raise ValueError("no real inference")
    if (
        detail["engine"],
        detail["modelId"],
        detail["questionSetVersion"],
        detail["event"]["eventId"],
    ) != ("jevdb", MODEL_ID, QUESTION_SET_VERSION, case["eventId"]):
        raise ValueError("invalid decision provenance")
    validate_archive_url(detail["event"]["url"])
    selected = [
        item["decisionId"] for item in result["inbox"]["items"] + result["inbox"]["uncertain"]
    ]
    if detail["decisionId"] not in selected or not detail["evidence"]["text"]:
        raise ValueError("decision absent from product inbox")
    screenshot = directory / "evidence-drawer.png"
    if not screenshot.is_file() or not screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("missing evidence drawer screenshot")
    queries = sorted((directory / "audit").glob("query-*.sql"))
    if list((directory / "audit").glob("query-*.error.json")):
        raise ValueError("native query failed or did not complete")
    if not queries:
        raise ValueError("missing executed native SQL")
    requested = 0
    for query in queries:
        stats = json.loads(query.with_suffix(".stats.json").read_text())
        requests = stats.get("requests")
        if type(requests) not in (int, float) or not math.isfinite(requests) or requests < 1:
            raise ValueError("native stats have no remote requests")
        if "jev_probability(" not in query.read_text() or stats.get("errors", 0) != 0:
            raise ValueError("native query failed")
        requested = max(requested, int(requests))
    db = Database(directory / "data" / "sentinel.duckdb", read_only=True)
    db.open()
    try:
        with db.read() as reader:
            reader.execute(
                "SELECT d.engine,d.model_id,d.question_set_version,e.source,d.evidence_kind "
                "FROM decision d JOIN event_doc e ON e.event_id=d.event_id "
                "WHERE d.decision_id=? AND d.event_id=?",
                [detail["decisionId"], case["eventId"]],
            )
            if reader.fetchone() != (
                "jevdb",
                MODEL_ID,
                QUESTION_SET_VERSION,
                "sec_edgar",
                detail["evidence"]["kind"],
            ):
                raise ValueError("persisted decision differs from UI")

        def unused_status(*_args: object) -> Any:
            raise ValueError("status should not be queried when verifying one decision")

        persisted = (
            InboxService(db, status_provider=unused_status)
            .get_decision(detail["decisionId"])
            .model_dump(mode="json", by_alias=True)
        )
        if persisted != detail:
            raise ValueError("persisted decision/evidence differs from captured RPC response")
    finally:
        db.close()
    return {
        "engine": "jevdb",
        "modelId": MODEL_ID,
        "questionSetVersion": QUESTION_SET_VERSION,
        "duckdbVersion": duckdb.__version__,
        "extensionPath": str(extension),
        "extensionSha256": digest_file(extension),
        "queries": len(queries),
        "nativeRequests": requested,
        "eventId": case["eventId"],
        "httpMode": case["httpMode"],
        "secSubmissionsSha256": submissions_sha256,
        "nativeCriteriaEquivalence": "NOT_RUN (F18-S04-CR-01)",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", type=Path)
    mode.add_argument("--serve", type=Path)
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument(
        "--statement", default="Apple has not announced its quarterly financial results."
    )
    parser.add_argument("--accession")
    parser.add_argument("--token-budget", type=int, default=50_000)
    parser.add_argument("--confirm-live-model-cost", action="store_true")
    args = parser.parse_args()
    try:
        if args.prepare:
            prepare_case(
                args.prepare.resolve(),
                symbol=args.symbol,
                statement=args.statement,
                accession=args.accession,
                token_budget=args.token_budget,
            )
            print("SEC case prepared; no model requests executed")
            return 0
        if not args.confirm_live_model_cost:
            raise ValueError("model cost confirmation required")
        return serve_case(args.serve.resolve())
    except Exception as error:
        print(f"M-8 failed: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
