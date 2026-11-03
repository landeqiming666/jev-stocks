from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import httpx2
import pytest
import typesafe_sdk as sdk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import probe_jev as p  # noqa: E402

KEY = "test-probe-secret-928173"
NOW = datetime(2026, 11, 3, tzinfo=UTC)


def success(request):
    if request.method == "GET":
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "jev-1.14.0", "description": "test", "release_date": "2026-10-14"}
                ]
            },
        )
    payload = json.loads(request.content)
    return httpx.Response(
        200,
        json={
            "model": payload["model"],
            "answers": {name: {"type": "noul", "noul": 0.51} for name in payload["questions"]},
            "usage": {"input_tokens": 123, "output_tokens": 9},
        },
    )


def run(handler=success, **options):
    options.setdefault("live", True)
    sleeps = []
    ticks = iter(NOW + timedelta(milliseconds=i * 10) for i in range(10000))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = p.run_probe(
            p.ProbeConfig("https://example.com/v1/systemone", KEY, "jev-1.14.0", **options),
            client=client,
            clock=lambda: next(ticks),
            sleep=sleeps.append,
        )
    return report, sleeps


def check(report, name):
    return next(c for c in report.checks if c["name"] == name)


def test_run_probe_not_live_never_calls_transport(tmp_path, monkeypatch):
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    calls = []

    def forbidden(request):
        calls.append(request)
        raise AssertionError("transport must not be called")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        report = p.run_probe(
            p.ProbeConfig(
                "https://example.com/v1/systemone",
                KEY,
                live=False,
                fixture_dir=tmp_path / "recordings",
            ),
            client=client,
            clock=lambda: NOW,
        )
    assert calls == []
    assert (report.status, report.reason, report.exit_code) == ("BLOCKED", "NOT_LIVE", 1)
    assert report.attempts == [] and report.fixtures_written == []
    assert all(c["detail"]["state"] == "NOT_RUN" for c in report.checks)
    assert not (tmp_path / "recordings").exists()


@pytest.mark.parametrize("live", [False, True])
def test_run_probe_offline_never_calls_transport(live, tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    calls = []

    def forbidden(request):
        calls.append(request)
        raise AssertionError("transport must not be called")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        report = p.run_probe(
            p.ProbeConfig(
                "https://example.com/v1/systemone",
                KEY,
                live=live,
                fixture_dir=tmp_path / "recordings",
            ),
            client=client,
            clock=lambda: NOW,
        )
    assert calls == []
    assert (report.status, report.reason, report.exit_code) == ("BLOCKED", "OFFLINE", 1)
    assert report.attempts == [] and report.fixtures_written == []
    assert all(c["detail"]["state"] == "NOT_RUN" for c in report.checks)
    assert not (tmp_path / "recordings").exists()


@pytest.mark.parametrize(
    "timeout", [True, False, None, "30", [], {}, 0, -1, float("nan"), float("inf"), 10**400]
)
def test_timeout_rejects_bool_and_invalid_values(timeout):
    with pytest.raises(ValueError):
        p.validate_config(
            p.ProbeConfig("https://example.com/v1/systemone", KEY, timeout_sec=timeout)
        )


@pytest.mark.parametrize("stop_after", [1, 67])
def test_offline_enabled_during_run_stops_before_next_http_or_sdk(stop_after, monkeypatch):
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == stop_after:
            monkeypatch.setenv("SENTINEL_OFFLINE", "1")
        return success(request)

    report, _ = run(handler)
    assert len(calls) == stop_after
    assert report.status == "BLOCKED" and report.reason == "OFFLINE"
    assert report.fixtures_written == []
    assert all(not r.headers.get("user-agent", "").startswith("typesafe") for r in calls)


def test_probe_401_is_blocked_and_not_recorded(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            401, json={"error": "Invalid token"}, headers={"x-request-id": "req-1"}
        )

    report, _ = run(handler, output_dir=tmp_path)
    assert (report.status, report.reason, report.exit_code) == ("BLOCKED", "AUTH_INVALID", 2)
    assert report.request_id == "req-1" and len(calls) == 1
    assert report.fixtures_written == [] and not list(tmp_path.glob("e*.json"))


def test_probe_403_is_distinct_from_401():
    calls = []
    report, _ = run(lambda r: (calls.append(r), httpx.Response(403))[1])
    assert (report.reason, report.exit_code) == ("AUTH_FORBIDDEN", 2)
    assert len(calls) == 1


def test_probe_429_records_retry_after():
    calls = []
    report, sleeps = run(
        lambda r: (calls.append(r), httpx.Response(429, headers={"Retry-After": "2"}))[1]
    )
    assert (report.reason, report.exit_code) == ("RATE_LIMITED", 3)
    assert len(calls) == 2 and sleeps == [2]
    assert report.attempts[-1]["retryAfterSec"] == 2


def test_probe_rejects_partial_answers():
    def handler(r):
        response = success(r)
        if r.method == "POST":
            data = response.json()
            data["answers"].pop("t1__supports", None)
            return httpx.Response(200, json=data)
        return response

    report, _ = run(handler)
    assert (report.reason, report.exit_code) == ("MODEL_ERROR", 4)
    assert report.fixtures_written == []


def test_request_id_prefers_header_then_body_then_local():
    assert p.extract_request_id({"X-Request-ID": "head"}, {"request_id": "body"}) == (
        "head",
        "header:x-request-id",
    )
    assert p.extract_request_id({}, {"request_id": "body"}) == ("body", "body:request_id")
    rid, source = p.extract_request_id({}, {})
    assert rid.startswith("local-") and source == "local"
    assert p.extract_request_id({"x-typesafe-request-id": "sdk"}, {})[0] == "sdk"


def test_success_fixture_has_no_authorization_or_key(tmp_path):
    value = {
        "recorded_at": p.sharedclock.to_iso(NOW),
        "model": "jev-1.14.0",
        "request": {"Authorization": KEY, "state": {"Cookie": "session"}},
        "response": {"request_id": KEY, "nested": [{"api_key": KEY, "note": "echo " + KEY}]},
    }
    path = p.write_fixture(value, tmp_path / "synthetic.json", secret=KEY)
    text = path.read_text()
    assert json.loads(text)["response"]["nested"][0]["note"] == "echo ***REDACTED***"
    assert all(s not in text for s in (KEY, "Authorization", "Cookie", "api_key", "request_id"))


def test_classify_probe_status_maps_known_http_codes():
    assert [p.classify_probe_status(s) for s in (200, 401, 403, 429, 500)] == [
        "PASS",
        "AUTH_INVALID",
        "AUTH_FORBIDDEN",
        "RATE_LIMITED",
        "MODEL_ERROR",
    ]


def test_missing_key_produces_report_without_network(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("JEV_ENDPOINT", raising=False)
    monkeypatch.setenv("SENTINEL_CLOCK", p.sharedclock.to_iso(NOW))
    monkeypatch.setattr(
        p.httpx.Client, "send", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("network"))
    )
    assert p.main(["--live", "--output", str(tmp_path)]) == 2
    data = json.loads((tmp_path / "g0-jev.json").read_text())
    assert data["status"] == "BLOCKED" and data["fixtures_written"] == []
    assert data["started_at"] == p.sharedclock.to_iso(NOW)
    assert "AUTH_INVALID missing JEV_API_KEY" in capsys.readouterr().out


def test_live_is_explicit_and_offline_env_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", KEY)
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    assert p.main(["--live", "--output", str(tmp_path)]) == 1
    assert json.loads((tmp_path / "g0-jev.json").read_text())["reason"] == "OFFLINE"
    monkeypatch.delenv("SENTINEL_OFFLINE")
    assert p.main(["--output", str(tmp_path)]) == 1


def test_synthetic_success_cannot_pass_or_record_even_with_live(tmp_path):
    report, _ = run(live=True, output_dir=tmp_path)
    assert report.status == "BLOCKED" and report.reason == "OFFLINE_TEST"
    assert report.fixtures_written == [] and not list(tmp_path.glob("*.json"))


def test_full_suite_has_twenty_latency_five_zh_ten_evidence_and_ten_pack():
    report, _ = run()
    assert report.timeout_semantics == "per_operation"
    assert report.operation_timeout_sec == 30.0
    assert report.total_request_timeout_verified is False
    assert report.response_size_limit_bytes is None
    assert {c["name"] for c in report.checks} >= {
        "models",
        "call",
        "latency",
        "tokens",
        "pack",
        "zh",
        "evidence",
        "sdk",
    }
    assert len(check(report, "latency")["detail"]["samples"]) == 20
    assert check(report, "latency")["detail"]["p50_ms"] == 10
    assert check(report, "latency")["detail"]["p95_ms"] == 10
    assert len(check(report, "tokens")["detail"]["samples"]) == 20
    assert len(check(report, "zh")["detail"]["samples"]) == 5
    assert len(check(report, "evidence")["detail"]["samples"]) == 10
    assert len(check(report, "pack")["detail"]["samples"]) == 10
    assert check(report, "sdk")["ok"]


def test_questions_use_completed_e1_and_independent_five_nouls():
    payload = p.scoring_request(p.samples()[0], "jev-1.14.0")
    assert "completed the sale of 4.5%" in payload["state"]["document"]
    assert p.QUESTION_SET_VERSION == "qs-2026-11-02.2"
    assert len(payload["questions"]) == 9
    assert len({q["instructions"] for q in payload["questions"].values()}) == 9
    assert set(payload["questions"]) >= {"t1__" + k for k in p.QUESTION_KEYS}
    assert "t2__kill_met" not in payload["questions"]


def test_model_mismatch_never_records():

    def handler(r):
        response = success(r)
        if r.method == "POST":
            data = response.json()
            data["model"] = "jev-1.13.0"
            return httpx.Response(200, json=data)
        return response

    report, _ = run(handler)
    assert report.reason == "MODEL_ERROR" and report.fixtures_written == []
    assert report.model_returned == "jev-1.13.0"


def test_injected_secret_in_error_headers_body_and_nested_keys_is_safe(tmp_path):
    report, _ = run(
        lambda r: httpx.Response(
            401,
            json={KEY: [{"Cookie": KEY}], "error": "Authorization: Bearer " + KEY},
            headers={"x-request-id": KEY, "content-type": KEY},
        )
    )
    path = p.write_report(report, tmp_path)
    text = path.read_text()
    assert all(s not in text for s in (KEY, "Authorization", "Cookie"))
    assert len(report.attempts[0]["response_summary"]) <= 200


def test_success_response_echoes_are_discarded(tmp_path):

    def handler(r):
        response = success(r)
        data = response.json()
        data["holding"] = {"symbol": "REAL", "quantity": 90877}
        data["instructions"] = "Authorization Cookie " + KEY
        return httpx.Response(200, json=data)

    report, _ = run(handler)
    text = p.write_report(report, tmp_path).read_text()
    assert all(s not in text for s in (KEY, "Authorization", "Cookie", "90877", "REAL"))


def test_mid_run_failure_keeps_incomplete_latency_and_no_fixtures(tmp_path):
    calls = []

    def handler(r):
        if r.method == "POST":
            calls.append(r)
            if len(calls) == 8:
                return httpx.Response(500, text="upstream failed")
        return success(r)

    report, _ = run(handler, output_dir=tmp_path)
    assert report.status == "FAILED" and report.fixtures_written == []
    assert not check(report, "latency")["ok"]
    assert check(report, "latency")["detail"]["state"] == "INCOMPLETE"
    assert len(check(report, "latency")["detail"]["samples"]) < 20


def test_invalid_probabilities_and_tokens_are_rejected():

    payload = p.scoring_request(p.samples()[0], "jev-1.14.0")
    data = success(httpx.Request("POST", "https://example.com", json=payload)).json()
    for invalid in (True, "0.5", None, float("nan"), float("inf"), -0.1, 1.1):
        data["answers"]["t1__relevant"]["noul"] = invalid
        with pytest.raises(ValueError):
            p.validate_response(data, payload)
    data["answers"]["t1__relevant"]["noul"] = 0.51
    for invalid in (0, -1, True, None, 1.2):
        data["usage"]["input_tokens"] = invalid
        with pytest.raises(ValueError):
            p.validate_response(data, payload)


def test_bad_json_5xx_redirect_and_false_200_are_failed():
    for response in (
        httpx.Response(500),
        httpx.Response(529),
        httpx.Response(302),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={}),
    ):
        report, _ = run(lambda r, response=response: response)
        assert report.status == "FAILED" and report.exit_code == 4


def test_models_404_skips_then_all_post_paths_execute():
    report, _ = run(lambda r: httpx.Response(404) if r.method == "GET" else success(r))
    assert check(report, "models")["detail"]["state"] == "SKIP"
    assert check(report, "sdk")["ok"]


def test_retry_after_clamped_invalid_and_http_date():
    for raw, expected in (
        ("99", 5),
        ("nan", 0),
        ("-1", 0),
        ("bad", 0),
        ("Tue, 03 Nov 2026 00:00:03 GMT", 3),
    ):
        report, waits = run(lambda r, raw=raw: httpx.Response(429, headers={"Retry-After": raw}))
        assert len(waits) == 1 and abs(waits[0] - expected) < 0.1
        assert report.exit_code == 3


def test_short_sample_size_cannot_pass_latency():
    report, _ = run(sample_size=2)
    assert not check(report, "latency")["ok"]


def test_endpoint_and_key_validation_does_not_echo_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", KEY)
    for url in (
        "http://example.com",
        "https://user:pass@example.com/v1/systemone",
        "https://example.com/v1/systemone?key=" + KEY,
        "https://example.com/v1/systemone#" + KEY,
    ):
        monkeypatch.setenv("JEV_ENDPOINT", url)
        assert p.main(["--live", "--output", str(tmp_path)]) == 1
        assert KEY not in (tmp_path / "g0-jev.json").read_text()


def test_sdk_actual_exception_types_and_retry_policy():

    assert sdk.__version__ == "0.7.5"
    config = p.ProbeConfig("https://example.com/v1/systemone", KEY, "jev-1.14.0")
    payload = p.scoring_request(p.samples()[0], config.model)
    for status, cls, expected in (
        (401, sdk.TypeSafeAuthenticationError, 1),
        (403, sdk.TypeSafePermissionDeniedError, 1),
        (429, sdk.TypeSafeRateLimitError, 2),
        (500, sdk.TypeSafeInternalServerError, 1),
    ):
        calls = []

        def handler(r, calls=calls, status=status):
            calls.append(r)
            return httpx2.Response(
                status, json={"error": "synthetic"}, headers={"x-typesafe-request-id": "sdk-id"}
            )

        with sdk.TypeSafeClient(
            api_key=KEY,
            base_url="https://example.com",
            transport=httpx2.MockTransport(handler),
            compression=False,
            retry=sdk.RetryPolicy(
                max_retries=1, http_statuses={429}, respect_retry_after=False, backoff_initial=0
            ),
        ) as client:
            with pytest.raises(cls) as captured:
                client.system_one(
                    model=config.model, state=payload["state"], questions=p.sdk_questions(payload)
                )
            assert captured.value.status == status and captured.value.request_id == "sdk-id"
        assert len(calls) == expected


def test_sdk_probe_errors_use_same_safe_report_and_two_attempts():
    for status, count in ((401, 1), (403, 1), (429, 2), (500, 1)):
        calls = []

        def handler(r, calls=calls, status=status):
            if r.headers.get("user-agent", "").startswith("typesafe"):
                calls.append(r)
                return httpx.Response(status, json={"error": KEY})
            return success(r)

        report, _ = run(handler)
        assert len(calls) == count and not check(report, "sdk")["ok"]
        assert report.fixtures_written == []


def test_evidence_offsets_are_codepoints_and_ties_choose_first():
    sample = p.samples()[0]
    payload, spans = p.evidence_request(sample, "jev-1.14.0")
    assert len(spans) == 4 and set(payload["questions"]) == {"s1", "s2", "s3", "s4"}
    result = p.select_evidence(spans, [0.2, 0.8, 0.8, 0.1])
    assert result["sentence"] == 2
    assert sample.document[result["start"] : result["end"]] == spans[1].text
    assert p.select_evidence(spans, [0.1] * 4)["kind"] == "passage"


def test_secure_report_permissions_and_unsafe_manual_report_rejected(tmp_path):

    report, _ = run()
    path = p.write_report(report, tmp_path / "含 空格 目录")
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    report.reason = "Authorization"
    with pytest.raises(ValueError):
        p.write_report(report, tmp_path)


def test_semantic_observations_require_completed_sale_and_resist_injection():
    records = {}
    for sample in p.samples():
        payload = p.scoring_request(sample, "jev-1.14.0")
        records[sample.name] = {
            "response": success(httpx.Request("POST", "https://example.com", json=payload)).json()
        }
    assert not all(p.semantic_observations(records).values())
    for name, key, probability in (
        ("e1_overturn", "kill_met", p.YES + 0.01),
        ("e4_adversarial", "relevant", p.NO - 0.01),
        ("e6_plan", "kill_met", p.NO - 0.01),
        ("e7_withdrawn", "kill_met", p.NO - 0.01),
    ):
        records[name]["response"]["answers"]["t1__" + key]["noul"] = probability
    assert all(p.semantic_observations(records).values())
    records["e6_plan"]["response"]["answers"]["t1__kill_met"]["noul"] = p.YES
    assert not p.semantic_observations(records)["planned_sale_not_completed"]


def test_sdk_constructor_model_and_call_override_use_actual_wire():
    calls = []

    def handler(request):
        assert str(request.url) == "https://example.com/v1/systemone"
        assert request.headers["authorization"] == "Bearer " + KEY
        calls.append(json.loads(request.content))
        response = success(request)
        return httpx2.Response(200, json=response.json())

    payload = p.scoring_request(p.samples()[0], "jev-1.14.0")
    with sdk.TypeSafeClient(
        api_key=KEY,
        model="jev-1.13.0",
        base_url="https://example.com",
        transport=httpx2.MockTransport(handler),
        compression=False,
        retry=sdk.RetryPolicy(max_retries=0),
    ) as client:
        inherited = client.system_one(state=payload["state"], questions=p.sdk_questions(payload))
        override = client.system_one(
            model="jev-1.14.0", state=payload["state"], questions=p.sdk_questions(payload)
        )
    assert inherited.model == "jev-1.13.0" and override.model == "jev-1.14.0"
    assert [r["model"] for r in calls] == ["jev-1.13.0", "jev-1.14.0"]
    assert isinstance(override.answers["t1__relevant"], sdk.NoulAnswer)
    assert override.usage.input_tokens == 123


def test_sdk_invalid_json_and_model_mismatch_fail_safely():
    for invalid in ("bad-json", "different-model", "partial"):

        def handler(request, invalid=invalid):
            response = success(request)
            if request.headers.get("user-agent", "").startswith("typesafe"):
                if invalid == "bad-json":
                    return httpx.Response(200, text="invalid " + KEY)
                body = response.json()
                if invalid == "different-model":
                    body["model"] = "jev-1.13.0"
                else:
                    body["answers"].pop("t1__supports")
                return httpx.Response(200, json=body)
            return response

        report, _ = run(handler)
        assert report.reason == "MODEL_ERROR" and not check(report, "sdk")["ok"]
        assert report.fixtures_written == []


def test_logs_suppress_sdk_response_echo_and_restore_logging(caplog):
    import logging

    previous = logging.root.manager.disable

    def handler(request):
        logging.getLogger("typesafe_sdk").critical("echo %s", KEY)
        return success(request)

    report, _ = run(handler)
    assert report.status == "BLOCKED"
    assert KEY not in caplog.text and logging.root.manager.disable == previous


def test_transport_failure_does_not_serialize_exception_secret(tmp_path):
    def handler(request):
        raise httpx.ReadTimeout("Authorization " + KEY, request=request)

    report, _ = run(handler)
    assert report.reason == "MODEL_ERROR" and report.fixtures_written == []
    assert KEY not in p.write_report(report, tmp_path).read_text()


def test_cassette_publication_is_atomic_and_preserves_manifest_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "__file__", str(tmp_path / "scripts" / "probe_jev.py"))
    records = {}
    for sample in p.samples()[:4]:
        payload = p.scoring_request(sample, "jev-1.14.0")
        records[sample.name] = {
            "request": payload,
            "response": success(httpx.Request("POST", "https://example.com", json=payload)).json(),
        }
    config = p.ProbeConfig("https://example.com/v1/systemone", KEY, "jev-1.14.0")
    target = tmp_path / "synthetic-serializer-test"
    files = p.publish_fixtures(records, target, config=config, clock=lambda: NOW)
    assert len(files) == 4 and len(list(target.glob("*.json"))) == 5
    manifest = json.loads((target / "manifest.json").read_text())
    assert len(manifest["fixtures"][0]["request_hash"]) == 64
    before = (target / "manifest.json").read_bytes()
    with pytest.raises(ValueError):
        p.publish_fixtures(records, target, config=config, clock=lambda: NOW)
    assert (target / "manifest.json").read_bytes() == before
    records["e3_support_zh"]["response"]["bad"] = float("nan")
    failed_target = tmp_path / "failed-serializer-test"
    with pytest.raises(ValueError):
        p.publish_fixtures(records, failed_target, config=config, clock=lambda: NOW)
    assert not failed_target.exists() and not list(tmp_path.glob(".g0-jev-*"))


def test_offline_mock_mount_cannot_pass_or_publish(tmp_path):
    with httpx.Client(mounts={"https://": httpx.MockTransport(success)}) as client:
        report = p.run_probe(
            p.ProbeConfig(
                "https://example.com/v1/systemone",
                KEY,
                "jev-1.14.0",
                live=True,
                fixture_dir=tmp_path / "recordings",
            ),
            client=client,
            clock=lambda: NOW,
            sleep=lambda seconds: None,
        )
    assert report.status == "BLOCKED" and report.fixtures_written == []
    assert not (tmp_path / "recordings").exists()


def test_server_cookie_is_not_forwarded_to_next_request():
    def handler(request):
        assert "cookie" not in request.headers
        response = success(request)
        response.headers["set-cookie"] = "server_session=" + KEY
        return response

    report, _ = run(handler)
    assert report.status == "BLOCKED" and check(report, "sdk")["ok"]
