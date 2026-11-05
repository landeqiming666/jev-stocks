from __future__ import annotations

import base64
import hashlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import duckdb
import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import acceptance_live as live  # noqa: E402
from sentinel import clock  # noqa: E402
from sentinel.app.args import AppArgs  # noqa: E402
from sentinel.app.container import build_container  # noqa: E402
from sentinel.app.registry import register_all  # noqa: E402
from sentinel.http import HttpClient  # noqa: E402
from sentinel.markets.instruments import InstrumentRepository, TickerRow  # noqa: E402
from sentinel.markets.sec.models import FilingRef  # noqa: E402
from sentinel.markets.sec.submissions import RECENT_FIELDS  # noqa: E402
from sentinel.rpc import Dispatcher  # noqa: E402
from sentinel.rpc.cancel import CancelToken  # noqa: E402
from sentinel.rpc.dispatcher import RequestContext  # noqa: E402
from sentinel.secrets import MemorySecretStore  # noqa: E402
from sentinel.settings.models import SettingsPatch  # noqa: E402

NOW = datetime(2026, 11, 2, 12, tzinfo=UTC)
ACCESSION = "0000320193-26-000001"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK0000320193.json"


def _http_snapshot(directory: Path) -> None:
    recent = {name: [""] for name in RECENT_FIELDS}
    recent.update(
        {
            "accessionNumber": [ACCESSION],
            "form": ["8-K"],
            "filingDate": ["2026-11-02"],
            "acceptanceDateTime": ["2026-11-02T12:00:00Z"],
            "items": ["2.02"],
            "primaryDocument": ["earnings.htm"],
            "primaryDocDescription": ["Results"],
        }
    )
    payloads = {
        SUBMISSIONS: json.dumps({"filings": {"recent": recent}}),
        ARCHIVE + ACCESSION + "-index.htm": (
            "<table><tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th></tr>"
            '<tr><td>1</td><td>Results</td><td><a href="earnings.htm">earnings.htm</a></td>'
            "<td>8-K</td></tr></table>"
        ),
        ARCHIVE
        + "earnings.htm": "<html><body><p>Apple announced quarterly results.</p></body></html>",
    }
    live.write_json(
        directory / "sec-http.json",
        {
            url: {
                "body": base64.b64encode(body.encode()).decode(),
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
                "contentType": "text/html",
                **(
                    {"originalSha256": hashlib.sha256(body.encode()).hexdigest()}
                    if url == SUBMISSIONS
                    else {}
                ),
            }
            for url, body in payloads.items()
        },
    )


def test_select_filing_binds_requested_accession_instead_of_newest() -> None:
    older = FilingRef(
        "us:" + ACCESSION,
        "us:AAPL",
        "0000320193",
        ACCESSION,
        "8-K",
        NOW,
        date(2026, 11, 2),
        "2.02",
        "earnings.htm",
        "Results",
    )
    newer = FilingRef(
        "us:0000320193-26-000002",
        "us:AAPL",
        "0000320193",
        "0000320193-26-000002",
        "8-K",
        NOW.replace(hour=13),
        date(2026, 11, 2),
        "9.01",
        "other.htm",
        "Other",
    )
    assert live.select_filing([older, newer], ACCESSION) is older
    assert live.select_filing([older, newer], None) is older
    with pytest.raises(ValueError):
        live.select_filing([newer], ACCESSION)


def test_recorded_sec_transport_rejects_modified_bytes_and_unknown_urls(tmp_path: Path) -> None:
    _http_snapshot(tmp_path)
    live.write_json(
        tmp_path / "case.json", {"httpSha256": live.digest_file(tmp_path / "sec-http.json")}
    )
    with httpx.Client(transport=live.replay_transport(tmp_path)) as client:
        assert "quarterly results" in client.get(ARCHIVE + "earnings.htm").text
        with pytest.raises(ValueError):
            client.get("https://example.com/private")
    (tmp_path / "sec-http.json").write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        live.replay_transport(tmp_path)


def test_prepare_offline_does_not_create_database(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    with pytest.raises(ValueError, match="offline"):
        live.prepare_case(
            tmp_path, symbol="AAPL", statement="test", accession=None, token_budget=50000
        )
    assert not (tmp_path / "data").exists()


def test_prepare_records_sec_response_shape_and_preserves_selected_row(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    monkeypatch.setenv("SENTINEL_SEC_CONTACT", "unit-analyst@example.com")
    _http_snapshot(tmp_path)
    raw = json.loads((tmp_path / "sec-http.json").read_text())
    responses = {url: base64.b64decode(row["body"]) for url, row in raw.items()}
    responses["https://www.sec.gov/files/company_tickers_exchange.json"] = json.dumps(
        {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [[320193, "Apple Inc.", "AAPL", "Nasdaq"]],
        }
    ).encode()
    requested = []

    def respond(request):
        requested.append(str(request.url))
        assert request.method == "GET"
        assert "unit-analyst@example.com" in request.headers["user-agent"]
        return httpx.Response(
            200, content=responses[str(request.url)], headers={"content-type": "text/html"}
        )

    class OfflineRecorder(live.RecordedSecClient):
        def __init__(self):
            HttpClient.__init__(self, transport=httpx.MockTransport(respond))
            self.responses = {}

    monkeypatch.setattr(live, "RecordedSecClient", OfflineRecorder)
    directory = tmp_path / "prepared"
    case = live.prepare_case(
        directory,
        symbol="AAPL",
        statement="Apple quarterly results",
        accession=ACCESSION,
        token_budget=50000,
    )
    assert case["eventId"] == "us:" + ACCESSION
    assert case["clock"] == "2026-11-02T12:00:01Z"
    assert len(requested) == 4
    assert (directory / "sec-submissions-original.json").read_bytes() == responses[SUBMISSIONS]
    assert case["submissionsSha256"] == hashlib.sha256(responses[SUBMISSIONS]).hexdigest()
    recorded = json.loads((directory / "sec-http.json").read_text())
    assert recorded[SUBMISSIONS]["originalSha256"] == case["submissionsSha256"]
    filtered = json.loads(base64.b64decode(recorded[SUBMISSIONS]["body"]))
    original = json.loads(responses[SUBMISSIONS])
    assert filtered["filings"]["recent"] == original["filings"]["recent"]
    assert "unit-analyst@example.com" not in (directory / "sec-http.json").read_text()
    assert not (directory / "audit").exists()
    with pytest.raises(ValueError, match="fresh"):
        live.prepare_case(
            directory, symbol="AAPL", statement="same", accession=None, token_budget=50000
        )


class SyntheticNativeConnection:
    def __init__(self, *args, **kwargs) -> None:
        self.db = duckdb.connect(":memory:")
        self.requests = 0
        self.description = None
        self.rows = []
        self.db.execute("CREATE MACRO jev_keys_overlap(a,b) AS list_has_any(a,b)")
        self.db.execute(
            "CREATE MACRO jev_probability(q,a,b) AS CASE WHEN contains(q,'more likely') "
            "THEN 0.1::DOUBLE ELSE 0.95::DOUBLE END"
        )

    def execute(self, sql, parameters=None):
        if sql.startswith(("LOAD", "SET", "CREATE SECRET", "DROP SECRET")):
            self.rows, self.description = [], []
        elif sql == "SELECT * FROM jevdb_stats()":
            self.rows = [(self.requests, 0, "private-value-must-not-be-exported")]
            self.description = [("requests",), ("errors",), ("body",)]
        else:
            self.requests += int("jev_probability(" in sql)
            result = self.db.execute(sql, parameters)
            self.rows, self.description = result.fetchall(), result.description
        return self

    def executemany(self, sql, parameters):
        self.db.executemany(sql, list(parameters))
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def interrupt(self):
        self.db.interrupt()

    def close(self):
        self.db.close()


def test_failed_native_execute_saves_failure_type_without_provider_body(
    tmp_path: Path, monkeypatch
) -> None:
    class BrokenNative(SyntheticNativeConnection):
        def execute(self, sql, parameters=None):
            raise TimeoutError("private-provider-body")

    monkeypatch.setattr(live, "duckdb", SimpleNamespace(connect=BrokenNative))
    connection = live.AuditedConnection(tmp_path)
    try:
        with pytest.raises(TimeoutError):
            connection.execute("SELECT jev_probability('test', {}, {})")
        error = json.loads((tmp_path / "query-0001.error.json").read_text())
        assert error == {"status": "failed", "errorType": "TimeoutError"}
        assert "private-provider-body" not in (tmp_path / "query-0001.error.json").read_text()
        assert not (tmp_path / "query-0001.stats.json").exists()
    finally:
        connection.close()


def test_production_rpc_scan_with_synthetic_native_records_queries_and_validates_proof(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-02T12:00:01Z")
    extension = tmp_path / "synthetic.duckdb_extension"
    extension.write_bytes(b"explicit synthetic native fixture; not a real model result")
    monkeypatch.setenv("SENTINEL_JEVDB_PATH", str(extension))
    monkeypatch.setattr(
        live, "duckdb", SimpleNamespace(connect=SyntheticNativeConnection, __version__="1.4.3")
    )
    _http_snapshot(tmp_path)
    submissions = (tmp_path / "sec-http.json").read_text()
    original = base64.b64decode(json.loads(submissions)[SUBMISSIONS]["body"])
    (tmp_path / "sec-submissions-original.json").write_bytes(original)
    case = {
        "source": "sec-live-snapshot",
        "httpSha256": live.digest_file(tmp_path / "sec-http.json"),
        "eventId": "us:" + ACCESSION,
        "accession": ACCESSION,
        "submissionsUrl": SUBMISSIONS,
        "submissionsSha256": hashlib.sha256(original).hexdigest(),
        "httpMode": "explicit synthetic unit fixture",
    }
    live.write_json(tmp_path / "case.json", case)
    live.write_json(
        tmp_path / "runtime.json",
        {
            "extensionSha256": live.digest_file(extension),
            "duckdbVersion": "1.4.3",
            "engine": "jevdb",
            "modelId": "jev-1.14.0",
            "questionSetVersion": "qs-2026-11-02.2",
        },
    )
    audit = tmp_path / "audit"
    store = MemorySecretStore()
    http = HttpClient(transport=live.replay_transport(tmp_path))
    container = build_container(
        AppArgs(tmp_path / "data", live.ROOT / "resources"),
        secret_store=store,
        http_client=http,
        jevdb_connection_factory=lambda *args, **kwargs: live.AuditedConnection(
            audit, *args, **kwargs
        ),
    )
    try:
        InstrumentRepository(container.db).replace_from_sec(
            [TickerRow("320193", "Apple Inc.", "AAPL", "Nasdaq")],
            fetched_at=NOW,
        )
        container.secrets.set_jev_key("test-key-do-not-use")
        container.settings.update(
            SettingsPatch(engine="jevdb", sec_contact_email="test@example.com")
        )
        dispatcher = Dispatcher()
        register_all(dispatcher, container)
        sequence = 0

        def call(method, params=None):
            nonlocal sequence
            sequence += 1
            ctx = RequestContext(str(sequence), method, CancelToken(), clock.now())
            response = dispatcher.dispatch(dispatcher.lookup(method), params or {}, ctx)
            assert "error" not in response, response
            return response["result"]

        bootstrap = call("app.bootstrap")
        assert bootstrap["engine"]["active"] == "jevdb"
        call("holdings.upsert", {"instrumentId": "us:AAPL", "quantity": "0.0000"})
        call(
            "thesis.create",
            {"instrumentId": "us:AAPL", "statement": "Apple has not announced quarterly results."},
        )
        started = call("scan.start", {"market": "us", "from": "2026-11-02T11:59:59Z"})
        assert container.scan.wait_idle(5)
        scan = call("scan.status", {"runId": started["runId"]})
        assert scan["status"] == "succeeded"
        inbox = call("inbox.list")
        assert len(inbox["items"]) == 1
        detail = call("decision.get", {"decisionId": inbox["items"][0]["decisionId"]})
        live.write_json(
            tmp_path / "result.json",
            {"bootstrap": bootstrap, "scan": scan, "inbox": inbox, "detail": detail},
        )
        (tmp_path / "evidence-drawer.png").write_bytes(
            b"\x89PNG\r\n\x1a\nexplicit synthetic screenshot fixture"
        )
    finally:
        container.close()
    proof = live.validate_evidence(tmp_path, extension)
    assert proof["queries"] == 2
    assert proof["nativeRequests"] == 2
    report_path = tmp_path / "result.json"
    saved_result = report_path.read_text()
    altered_result = json.loads(saved_result)
    altered_result["detail"]["evidence"]["text"] = "not the persisted source evidence"
    live.write_json(report_path, altered_result)
    with pytest.raises(ValueError, match="persisted"):
        live.validate_evidence(tmp_path, extension)
    report_path.write_text(saved_result)
    assert not any("private-value" in path.read_text() for path in audit.glob("*.json"))
    extension.write_bytes(b"changed since core inference")
    with pytest.raises(ValueError, match="runtime"):
        live.validate_evidence(tmp_path, extension)
    extension.write_bytes(b"explicit synthetic native fixture; not a real model result")
    stats_path = next(audit.glob("*.stats.json"))
    original = stats_path.read_text()
    stats_path.write_text('{"requests":0,"errors":0}')
    with pytest.raises(ValueError, match="no remote requests"):
        live.validate_evidence(tmp_path, extension)
    stats_path.write_text(original)
    (audit / "query-0003.sql").write_text("SELECT jev_probability('evidence', {}, {})")
    live.write_json(
        audit / "query-0003.error.json", {"status": "failed", "errorType": "TimeoutError"}
    )
    with pytest.raises(ValueError, match="failed"):
        live.validate_evidence(tmp_path, extension)
    (audit / "query-0003.sql").unlink()
    (audit / "query-0003.error.json").unlink()
    (tmp_path / "evidence-drawer.png").unlink()
    with pytest.raises(ValueError, match="screenshot"):
        live.validate_evidence(tmp_path, extension)
    (tmp_path / "evidence-drawer.png").write_bytes(
        b"\x89PNG\r\n\x1a\nexplicit synthetic screenshot fixture"
    )
    original_path = tmp_path / "sec-submissions-original.json"
    saved_original = original_path.read_bytes()
    original_path.write_bytes(saved_original + b" ")
    with pytest.raises(ValueError, match="original SEC submissions"):
        live.validate_evidence(tmp_path, extension)
    original_path.write_bytes(saved_original)
    case_path = tmp_path / "case.json"
    saved_case = case_path.read_text()
    case_path.unlink()
    with pytest.raises(ValueError, match="missing evidence"):
        live.validate_evidence(tmp_path, extension)
    case_path.write_text(saved_case)
    assert live.validate_evidence(tmp_path, extension)["secSubmissionsSha256"] == hashlib.sha256(
        saved_original
    ).hexdigest()
