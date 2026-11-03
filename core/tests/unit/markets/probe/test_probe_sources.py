import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[5] / "scripts/probe_sources.py"
ROW = ["2026-10-30", "346.72", "344.63", "349.19", "334.35", "67841555"]
CONTACT = "unit@probe.test"  # 仅供 MockTransport；不得用于公开请求。


@pytest.fixture
def probe(monkeypatch):
    spec = importlib.util.spec_from_file_location("probe_sources", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    return module


def client_for(payload, status=200, headers=None):
    return httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status, json=payload, headers=headers)
        )
    )


def submissions():
    return {
        "filings": {
            "recent": {
                "accessionNumber": ["0000000000-26-000001"],
                "acceptanceDateTime": ["2026-10-30T20:30:28.000Z"],
                "form": ["8-K"],
                "primaryDocument": ["synthetic.htm"],
            }
        }
    }


def test_sec_acceptance_datetime_regex(probe):
    assert probe.valid_acceptance_datetime("2026-07-30T20:30:28.000Z")
    assert not probe.valid_acceptance_datetime("2026-07-30 20:30:28")


def test_tencent_maps_close_before_high(probe):
    bar = probe.parse_tencent({"code": 0, "data": {"usZZAR": {"day": [ROW]}}}, "usZZAR")
    assert bar["sample"] == {
        "date": "2026-10-30",
        "open": "346.72",
        "close": "344.63",
        "high": "349.19",
        "low": "334.35",
        "volume": "67841555",
    }


def test_tencent_prefers_qfqday_key(probe):
    result = probe.parse_tencent(
        {"code": 0, "data": {"usZZAR": {"qfqday": [ROW], "day": []}}}, "usZZAR"
    )
    assert result["key"] == "qfqday"
    assert result["hasAdjClose"] is False


def test_nasdaq_strips_dollar_prefix(probe):
    assert probe.price("$344.63") == Decimal("344.63")
    assert probe.price("$345.10") == Decimal("345.10")


def test_missing_submissions_field_fails(probe):
    payload = submissions()
    del payload["filings"]["recent"]["acceptanceDateTime"]
    checks = probe.probe_sec(CONTACT, client_for(payload))
    assert checks[0].status == "fail"
    assert "acceptanceDateTime" in checks[0].detail
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, content=b"\xff", headers={"Content-Type": "application/json"}
            )
        )
    )
    check = probe.probe_sec(CONTACT, client)[0]
    assert check.status == "fail" and "Content-Type" in check.detail


def test_rate_limit_is_warn_not_fail(probe):
    checks = probe.probe_sec(CONTACT, client_for({}, 429, {"Retry-After": "2"}))
    assert checks[0].status == "warn"
    assert checks[0].values["retryAfter"] == "2"


def test_empty_ticker_rows_is_fail(probe):
    payload = {"fields": ["cik", "name", "ticker", "exchange"], "data": []}
    checks = probe.probe_sec(CONTACT, client_for(payload))
    assert next(c for c in checks if c.name == "sec.tickers").status == "fail"


def test_offline_fixture_mode_does_not_use_network(probe, tmp_path, monkeypatch):
    fixture = tmp_path / "synthetic input"
    fixture.mkdir()
    (fixture / "quotes_tencent_us.probe.json").write_text(
        json.dumps(
            {
                "code": 0,
                "data": {"usAAPL": {"day": [ROW]}},
                "_provenance": {"mode": "synthetic"},
            }
        )
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("network is forbidden")

    monkeypatch.setattr(probe.httpx, "Client", forbidden)
    out = tmp_path / "output"
    assert probe.main(["--offline-fixtures", str(fixture), "--out", str(out)]) == 0
    assert "OFFLINE" in (out / "REPORT.md").read_text()


def test_missing_contact_exits_2(probe, monkeypatch, tmp_path):
    monkeypatch.delenv("SENTINEL_SEC_CONTACT", raising=False)
    monkeypatch.setattr(probe.httpx, "Client", lambda *a, **k: pytest.fail("client opened"))
    assert probe.main(["--contact", "", "--out", str(tmp_path / "output")]) == 2
    assert not (tmp_path / "output").exists()


def test_continuity_counts_four_day_gap(probe):
    rows = [["2026-01-02", *ROW[1:]], ["2026-01-07", *ROW[1:]]]
    result = probe.probe_continuity({"ZZAR": rows})[0]
    assert result.values["gaps"] == 1
    assert result.status == "fail"


@pytest.mark.parametrize("value", ["2026-07-30T20:30:28Z", "2026-07-30T20:30:28.1Z"])
def test_acceptance_precision_is_observed_not_assumed(probe, value):
    assert probe.valid_acceptance_datetime(value)


@pytest.mark.parametrize("value", [None, "2026-02-30T00:00:00Z", "2026-01-01T00:00:00+00:00"])
def test_bad_acceptance_datetime(probe, value):
    assert not probe.valid_acceptance_datetime(value)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0", "", "N/A", None, 5, "$1,2"])
def test_price_rejects_nonfinite_missing_and_invalid(probe, value):
    with pytest.raises((ValueError, TypeError)):
        probe.price(value)


@pytest.mark.parametrize("value", ["$1,234.500", "1234.500"])
def test_price_decimal_precision(probe, value):
    assert probe.price(value) == Decimal("1234.500")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "", None, "1,23"])
def test_volume_rejects_bad_values(probe, value):
    with pytest.raises(ValueError):
        probe.volume(value)


def test_fractional_volume_is_reported_without_truncation(probe):
    row = [*ROW[:5], "12.5"]
    result = probe.parse_tencent({"code": 0, "data": {"usZZAR": {"day": [row]}}}, "usZZAR")
    assert result["fractionalVolumes"] == 1
    assert result["sample"]["volume"] == "12.5"
    assert not result["volumeUnitVerified"]


def test_real_hk_metadata_shape_retained(probe):
    row = [*ROW, {"cqr": "2026-10-30", "HGcontent": ""}]
    payload = {"code": 0, "data": {"hk00700": {"day": [row]}}}
    result = probe.parse_tencent(payload, "hk00700")
    assert result["fieldCounts"] == [7]
    assert probe._crop("tencent_hk", payload)["data"]["hk00700"]["day"][0] == row


@pytest.mark.parametrize(
    "row",
    [
        ROW[:5],
        [*ROW, "unknown"],
        [*ROW, {}, "unknown"],
        [ROW[0], "400", *ROW[2:]],
        [ROW[0], "NaN", *ROW[2:]],
    ],
)
def test_bad_quote_row_shape_or_ohlc(probe, row):
    with pytest.raises((ValueError, TypeError)):
        probe.parse_tencent({"code": 0, "data": {"usZZAR": {"day": [row]}}}, "usZZAR")


@pytest.mark.parametrize(
    "dates", [["2026-10-30", "2026-10-30"], ["2026-10-28", "2026-10-30", "2026-10-29"]]
)
def test_duplicate_and_unsorted_dates_rejected(probe, dates):
    result = probe.probe_continuity({"ZZAR": [[d, *ROW[1:]] for d in dates]})[0]
    assert result.status == "fail"


def test_continuity_row_count_does_not_verify_calendar(probe):
    from datetime import date, timedelta

    rows = [[(date(2025, 1, 1) + timedelta(days=i)).isoformat(), *ROW[1:]] for i in range(250)]
    result = probe.probe_continuity({"ZZAR": rows})[0]
    assert result.status == "warn" and result.values["rows"] == 250
    assert result.values["calendarVerified"] is False
    assert result.values["hasAdjClose"] is False


def test_submissions_parallel_arrays_and_crop(probe):
    payload = submissions()
    recent = payload["filings"]["recent"]
    for key, values in recent.items():
        recent[key] = values * 40
    recent["form"][30] = "8-K/A"
    recent["form"][35] = "10-Q"
    clipped = probe._crop("sec.submissions", payload)
    assert len(clipped["filings"]["recent"]["form"]) == 15
    assert {"8-K", "8-K/A", "10-Q"} <= set(clipped["filings"]["recent"]["form"])
    recent["form"].append("8-K")
    with pytest.raises(ValueError, match="lengths"):
        probe.parse_submissions(payload)


def test_ticker_crop_only_selects_existing_rows(probe):
    payload = {
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [[i + 1, "Synthetic fixture", f"ZZ{i}", "Nasdaq"] for i in range(30)],
    }
    payload["data"] += [
        [31, "Synthetic class fixture", "BRK-B", "NYSE"],
        [32, "Synthetic OTC fixture", "ZZOT", "OTC"],
    ]
    clipped = probe._crop("sec.tickers", payload)
    assert len(clipped["data"]) == 25
    assert all(r in payload["data"] for r in clipped["data"])
    assert probe.parse_tickers(clipped)["duplicates"] == 0
    assert probe.parse_tickers(clipped)["spaces"] == 0


@pytest.mark.parametrize("status", [403, 500, 503])
def test_sec_http_failure_records_status_without_success_fixture(probe, status):
    client = client_for({}, status)
    check = probe.probe_sec(CONTACT, client)[0]
    assert check.http_status == status and check.status == "fail"
    assert not probe.recordings(client)


def test_sec_ua_and_index_from_actual_mock_accession(probe):
    urls, headers = [], []

    def respond(request):
        urls.append(str(request.url))
        headers.append(request.headers)
        if str(request.url) == probe.SUBMISSIONS_URL:
            return httpx.Response(200, json=submissions())
        if str(request.url) == probe.TICKERS_URL:
            return httpx.Response(
                200,
                json={
                    "fields": ["cik", "name", "ticker", "exchange"],
                    "data": [[1, "Synthetic", "ZZAR", "Nasdaq"]],
                },
            )
        if str(request.url) == probe.BROWSE_URL:
            return httpx.Response(200, text='<table class="tableFile2"></table>')
        return httpx.Response(
            200,
            text='<table class="tableFile"><tr><th>Seq</th>'
            "<th>Description</th><th>Document</th><th>Type</th></tr>"
            "<tr><td>2</td><td>Synthetic exhibit</td><td>zz.htm</td>"
            "<td>EX-99.1</td></tr></table>",
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    checks = probe.probe_sec(CONTACT, client)
    assert checks[-1].status == "pass"
    assert urls[-1].endswith("/000000000026000001/0000000000-26-000001-index.htm")
    assert all(h["User-Agent"] == f"SentinelProbe/0.1 (contact: {CONTACT})" for h in headers)
    assert all(h["Accept-Encoding"] == "gzip, deflate" for h in headers)
    assert "EX-99.1" in probe.recordings(client)["filing_index_8k_ex99.probe.html"]


@pytest.mark.parametrize(
    "contact", ["", "name@example.com", "a b@probe.test", "a\n@probe.test", "中文@probe.test"]
)
def test_invalid_contact_never_opens_client(probe, contact, monkeypatch, tmp_path):
    monkeypatch.setattr(probe.httpx, "Client", lambda *a, **k: pytest.fail("client opened"))
    assert probe.main(["--contact", contact, "--out", str(tmp_path)]) == 2


@pytest.mark.parametrize(
    "args",
    [
        ["--days", "0"],
        ["--timeout", "NaN"],
        ["--timeout", "0"],
        ["--symbols", "AAPL,AAPL"],
        ["--symbols", "AAPL/evil"],
        ["--unknown"],
    ],
)
def test_invalid_arguments_exit_2(probe, args):
    assert probe.main(args) == 2


def test_env_offline_blocks_cli_and_public_functions(probe, monkeypatch, tmp_path):
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    monkeypatch.setattr(probe.httpx, "Client", lambda *a, **k: pytest.fail("client opened"))
    assert probe.main(["--contact", CONTACT, "--out", str(tmp_path)]) == 1

    class Forbidden:
        def get(self, *a, **k):
            pytest.fail("get called")

    assert all(c.status == "fail" for c in probe.probe_sec(CONTACT, Forbidden()))
    assert all(c.status == "fail" for c in probe.probe_tencent(Forbidden()))


def test_timeout_is_failed_check(probe):
    def timed_out(request):
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    client = httpx.Client(transport=httpx.MockTransport(timed_out))
    check = probe.probe_nasdaq(client)[0]
    assert check.status == "fail" and check.http_status is None
    assert check.detail == "ReadTimeout"


def test_negative_source_now_available_is_warn(probe):
    client = client_for({"data": {"klines": ["synthetic boundary"]}})
    check = probe.probe_negative(client)[-1]
    assert check.status == "warn" and check.required is False
    assert check.values["available"] is True
    assert len(check.values["summary"]) <= 200


def test_fixture_manifest_detects_corruption_and_preserves_origin(probe, tmp_path):
    payload = {"code": 0, "data": {"usAAPL": {"day": [ROW]}}, "_provenance": {"mode": "synthetic"}}
    probe.write_fixtures(tmp_path, [], {"quotes_tencent_us.probe.json": payload})
    checks, copied = probe.offline_checks(tmp_path)
    assert checks[0].status == "pass"
    assert copied["quotes_tencent_us.probe.json"]["_provenance"]["mode"] == "synthetic"
    path = tmp_path / "quotes_tencent_us.probe.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="hash mismatch"):
        probe.offline_checks(tmp_path)


def test_write_fixtures_rejects_path_escape(probe, tmp_path):
    with pytest.raises(ValueError, match="unsafe"):
        probe.write_fixtures(tmp_path, [], {"../escape.json": {}})


def test_recorded_fixture_replay_stays_offline(probe, tmp_path, monkeypatch):
    monkeypatch.setattr(probe.httpx, "Client", lambda *a, **k: pytest.fail("network used"))
    source = SCRIPT.parent.parent / "core/tests/fixtures/markets/probe"
    assert probe.main(["--offline-fixtures", str(source), "--out", str(tmp_path)]) == 0
    assert json.loads((tmp_path / "manifest.json").read_text())["gatePassed"] is False


def test_synthetic_boundaries_are_separate_from_recorded_tickers(probe):
    source = SCRIPT.parent.parent / "core/tests/fixtures/markets/probe"
    synthetic = json.loads((source / "synthetic_boundaries.json").read_text())
    real = json.loads((source / "company_tickers_exchange.probe.json").read_text())
    assert synthetic["_provenance"]["mode"] == "synthetic"
    assert real["_provenance"]["mode"] == "historical"
    assert probe.parse_tickers(synthetic["tickers"])["duplicates"] == 1
    assert probe.parse_tickers(synthetic["tickers"])["spaces"] == 1
    assert probe.parse_tickers(real)["duplicates"] == 0
    assert probe.parse_tickers(real)["spaces"] == 0


def test_unknown_manifest_file_is_rejected(probe, tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"files": {"unexpected.json": "x"}}))
    with pytest.raises(ValueError, match="unsupported"):
        probe.offline_checks(tmp_path)
