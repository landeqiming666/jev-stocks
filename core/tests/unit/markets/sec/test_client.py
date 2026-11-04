from dataclasses import replace

import httpx
import pytest

from sentinel import __version__
from sentinel.errors import SourceError, UserError
from sentinel.http import HttpClient
from sentinel.markets.sec import SecFilingsClient

from .conftest import BASE, INSTRUMENT, NOW, SINCE, make_ref
from .test_submissions import payload


class FakeHTTP:
    def __init__(self, response=None):
        self.response = response
        self.calls = []

    def get_json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response

    def get_text(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return "<p>Synthetic</p>"


@pytest.mark.parametrize(
    "email",
    [
        None,
        "",
        " ",
        "bad",
        "a@b",
        "a b@example.com",
        "a\r\n@example.com",
        "a@example..com",
        "用户@example.com",
        "a@例子.com",
        "a\x7f@example.com",
        "a" * 65 + "@example.com",
        True,
    ],
)
@pytest.mark.parametrize("operation", ["list", "index", "file"])
def test_missing_email_no_requests(email, operation):
    http = FakeHTTP(payload())
    client = SecFilingsClient(http, email_provider=lambda: email)
    with pytest.raises(UserError) as error:
        if operation == "list":
            client.list_filings(INSTRUMENT, SINCE, NOW, NOW)
        elif operation == "index":
            client.fetch_index(make_ref())
        else:
            client.fetch_file(BASE + "main.htm")
    assert error.value.to_wire()["data"]["missing"] == ["secEmail"]
    assert "SEC 联系邮箱" in error.value.to_wire()["message"]
    assert http.calls == []


def test_default_provider_requires_configuration():
    http = FakeHTTP(payload())
    with pytest.raises(UserError, match="CONFIG_REQUIRED"):
        SecFilingsClient(http).fetch_file(BASE + "main.htm")
    assert http.calls == []


def test_dynamic_headers_each_operation_actual_transport(monkeypatch):
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.host == "data.sec.gov":
            return httpx.Response(200, json=payload())
        return httpx.Response(200, text="<p>Synthetic</p>")

    config = {"email": "first@example.com"}
    with HttpClient(transport=httpx.MockTransport(handle)) as http:
        client = SecFilingsClient(http, email_provider=lambda: config["email"])
        assert len(client.list_filings(INSTRUMENT, SINCE, NOW, NOW)) == 6
        config["email"] = "second@example.com"
        assert client.fetch_index(make_ref()) == []
        config["email"] = "third@example.com"
        assert client.fetch_file(BASE + "main.htm")
        config["email"] = ""
        with pytest.raises(UserError):
            client.fetch_file(BASE + "main.htm")
    assert [r.headers["User-Agent"] for r in requests] == [
        f"Sentinel/{__version__} {email}@example.com" for email in ("first", "second", "third")
    ]
    assert str(requests[0].url) == "https://data.sec.gov/submissions/CIK0001234567.json"
    assert str(requests[1].url) == BASE + make_ref().accession + "-index.htm"


@pytest.mark.parametrize("response", [None, [], "not JSON", 42, {}, {"filings": []}])
def test_non_object_and_bad_submissions_response(response):
    http = FakeHTTP(response)
    with pytest.raises(SourceError) as error:
        SecFilingsClient(http, email_provider=lambda: "test@example.com").list_filings(
            INSTRUMENT, SINCE, NOW, NOW
        )
    assert error.value.reason == "SEC_SCHEMA"


@pytest.mark.parametrize(
    "changes", [{"cik": None}, {"cik": "0"}, {"cik": "../1"}, {"market": "hk"}]
)
def test_invalid_instrument_no_requests(changes):
    http = FakeHTTP(payload())
    with pytest.raises(SourceError):
        SecFilingsClient(http, email_provider=lambda: "test@example.com").list_filings(
            replace(INSTRUMENT, **changes), SINCE, NOW, NOW
        )
    assert http.calls == []


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/main.htm",
        BASE + "../main.htm",
        BASE + "%2e%2e/main.htm",
        BASE.replace("https:", "http:") + "main.htm",
        BASE + "main.htm?secret=private",
        BASE + "main.htm#fragment",
        BASE.replace("www.sec.gov", "www.sec.gov:443") + "main.htm",
        BASE.replace("www.sec.gov", "private@www.sec.gov") + "main.htm",
        BASE + "main.htm\n",
        BASE + "\x00main.htm",
    ],
)
def test_fetch_file_rejects_unsafe_before_http(url):
    http = FakeHTTP(payload())
    with pytest.raises(SourceError) as error:
        SecFilingsClient(http, email_provider=lambda: "test@example.com").fetch_file(url)
    assert error.value.reason == "SEC_UNSAFE_URL"
    assert http.calls == []


@pytest.mark.parametrize(
    "status,body,headers,code,reason,attempts",
    [
        (429, b"", {"Retry-After": "2"}, "RATE_LIMITED", None, 3),
        (403, b"", {}, "SOURCE_UNAVAILABLE", "SEC_FORBIDDEN", 1),
        (
            200,
            b"\xff",
            {"Content-Type": "text/html; charset=utf-8"},
            "SOURCE_UNAVAILABLE",
            "DECODE_FAILED",
            1,
        ),
        (200, b"not JSON", {}, "SOURCE_UNAVAILABLE", "INVALID_JSON", 1),
    ],
)
def test_real_http_errors_propagate(monkeypatch, status, body, headers, code, reason, attempts):
    monkeypatch.delenv("SENTINEL_OFFLINE", raising=False)
    requests = []
    timer = [0.0]

    def handle(request):
        requests.append(request)
        return httpx.Response(status, content=body, headers=headers)

    def sleep(seconds):
        timer[0] += seconds

    with HttpClient(
        transport=httpx.MockTransport(handle),
        monotonic=lambda: timer[0],
        sleeper=sleep,
        uniform=lambda a, b: 0,
    ) as http:
        client = SecFilingsClient(http, email_provider=lambda: "test@example.com")
        with pytest.raises(SourceError) as error:
            client.list_filings(INSTRUMENT, SINCE, NOW, NOW)
        assert error.value.code == code and error.value.reason == reason
        assert len(requests) == attempts
        if status == 403:
            with pytest.raises(SourceError) as second:
                client.fetch_file(BASE + "main.htm")
            assert second.value.reason == "CIRCUIT_OPEN" and len(requests) == 1


def test_offline_real_facade_never_reaches_transport(monkeypatch):
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    requests = []
    with (
        HttpClient(transport=httpx.MockTransport(lambda request: requests.append(request))) as http,
        pytest.raises(SourceError) as error,
    ):
        SecFilingsClient(http, email_provider=lambda: "test@example.com").fetch_file(
            BASE + "main.htm"
        )
    assert error.value.reason == "OFFLINE" and requests == []
