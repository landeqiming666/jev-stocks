#!/usr/bin/env python3
"""公开源探针；裁剪录制与离线解析分别报告，未知事实不作为通过证据。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from pathlib import Path

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from sentinel import clock
from sentinel.domain.contact import is_valid_sec_email

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "core/tests/fixtures/markets/probe"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK0000320193.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
BROWSE_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193"
    "&type=8-K&dateb=&owner=include&count=10"
)
TENCENT_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{limit},qfq"
NASDAQ_URL = (
    "https://api.nasdaq.com/api/quote/{symbol}/historical"
    "?assetclass=stocks&fromdate={fromdate}&limit={limit}"
)
EXPECTED_TICKER_ROWS = 10423
TENCENT_SYMBOLS = {"tencent_us": "usAAPL", "tencent_hk": "hk00700", "tencent_cn": "sh600519"}
NEGATIVE_URLS = {
    "yahoo": "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1mo&interval=1d",
    "stooq": "https://stooq.com/q/d/l/?s=aapl.us&i=d",
    "eastmoney": (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=105.AAPL"
        "&klt=101&fqt=1&lmt=30&end=20500101&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    ),
}
JSON_ERRORS = (ValueError, KeyError, TypeError, IndexError, AttributeError, InvalidOperation)


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    status: str
    required: bool
    http_status: int | None
    elapsed_ms: int | None
    detail: str
    values: dict[str, object]


def valid_acceptance_datetime(value: object) -> bool:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z", value
    ):
        return False
    try:
        clock.parse_iso(value)
        return True
    except ValueError:
        return False


def price(value: object) -> Decimal:
    if not isinstance(value, str):
        raise TypeError("price must be a decimal string")
    text = value.removeprefix("$")
    if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?", text):
        raise ValueError("price is missing or not a finite positive Decimal")
    result = Decimal(text.replace(",", ""))
    if not result.is_finite() or result <= 0:
        raise ValueError("price is missing or not a finite positive Decimal")
    return result


def volume(value: object) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?", value
    ):
        raise ValueError("volume must be a finite nonnegative decimal string")
    return Decimal(value.replace(",", ""))


def _bar(row: list[str]) -> dict[str, str]:
    if not isinstance(row, list):
        raise TypeError("price row must be a list")
    if len(row) != 6 and not (len(row) == 7 and isinstance(row[6], dict)):
        raise ValueError(f"Tencent row field count {len(row)}; expected 6 or 7 with metadata")
    row = row[:6]
    if any(not isinstance(v, str) for v in row):
        raise ValueError("price row must contain strings")
    date.fromisoformat(row[0])
    prices = [price(v) for v in row[1:5]]
    opened, closed, high, low = prices
    if not low <= min(opened, closed) <= max(opened, closed) <= high:
        raise ValueError("OHLC range invalid")
    volume(row[5])
    return dict(zip(("date", "open", "close", "high", "low", "volume"), row, strict=True))


def _row_stats(rows: list[list[str]]) -> dict[str, object]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("empty price rows")
    bars = [_bar(row) for row in rows]
    dates = [date.fromisoformat(b["date"]) for b in bars]
    unique = sorted(set(dates))
    duplicates = len(dates) - len(unique)
    order = "ascending" if dates == sorted(dates) else "descending"
    if dates != sorted(dates) and dates != sorted(dates, reverse=True):
        raise ValueError("price dates are not sorted")
    if duplicates:
        raise ValueError(f"duplicate trade dates: {duplicates}")
    return {
        "rows": len(rows),
        "firstDate": unique[0].isoformat(),
        "lastDate": unique[-1].isoformat(),
        "gaps": sum((b - a).days > 4 for a, b in pairwise(unique)),
        "duplicates": duplicates,
        "order": order,
        "hasAdjClose": False,
        "fractionalVolumes": sum(volume(r[5]) != volume(r[5]).to_integral_value() for r in rows),
        "sample": bars[0],
        "calendarVerified": False,
        "adjustmentVerified": False,
        "fieldCounts": sorted({len(r) for r in rows}),
        "volumeUnitVerified": False,
    }


def parse_tencent(payload: dict, symbol: str) -> dict[str, object]:
    if payload["code"] != 0:
        raise ValueError(f"Tencent code={payload['code']}; source error")
    data = payload["data"][symbol]
    key = "qfqday" if "qfqday" in data else "day"
    return {**_row_stats(data[key]), "key": key, "symbol": symbol}


def parse_nasdaq(payload: dict) -> dict[str, object]:
    rows = payload["data"]["tradesTable"]["rows"]
    mapped = [
        [
            datetime.strptime(r["date"], "%m/%d/%Y").date().isoformat(),
            str(price(r["open"])),
            str(price(r["close"])),
            str(price(r["high"])),
            str(price(r["low"])),
            str(volume(r["volume"])),
        ]
        for r in rows
    ]
    return {
        **_row_stats(mapped),
        "symbol": payload["data"].get("symbol"),
        "dollarPrefix": any(str(r["close"]).startswith("$") for r in rows),
    }


def parse_submissions(payload: dict) -> dict[str, object]:
    recent = payload["filings"]["recent"]
    required = ("accessionNumber", "acceptanceDateTime", "form", "primaryDocument")
    for key in required:
        if key not in recent:
            raise ValueError(f"missing {key}")
    if not recent["form"] or any(not isinstance(v, list) for v in recent.values()):
        raise ValueError("filings.recent must contain nonempty parallel arrays")
    if len({len(v) for v in recent.values()}) != 1:
        raise ValueError("filings.recent parallel array lengths differ")
    if not all(valid_acceptance_datetime(v) for v in recent["acceptanceDateTime"]):
        raise ValueError("acceptanceDateTime must be ISO UTC Z")
    return {
        "rows": len(recent["form"]),
        "forms": dict(Counter(recent["form"])),
        "fractionalDigits": sorted(
            {len(v.split(".")[1][:-1]) if "." in v else 0 for v in recent["acceptanceDateTime"]}
        ),
    }


def parse_tickers(payload: dict) -> dict[str, object]:
    if payload["fields"] != ["cik", "name", "ticker", "exchange"]:
        raise ValueError("ticker fields order differs")
    rows = payload["data"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("empty ticker data")
    for row in rows:
        if not isinstance(row, list) or len(row) != 4 or not isinstance(row[2], str):
            raise ValueError("ticker row must have four fields and a string ticker")
    counts = Counter(r[2] for r in rows)
    return {
        "rows": len(rows),
        "brkB": counts["BRK-B"],
        "otc": sum(r[3] == "OTC" for r in rows),
        "duplicates": sum(n - 1 for n in counts.values()),
        "spaces": sum(any(c.isspace() for c in r[2]) for r in rows),
    }


def parse_index(html: str) -> dict[str, object]:
    tables = HTMLParser(html).css("table.tableFile")
    for table in tables:
        rows = [[c.text(strip=True) for c in r.css("td")] for r in table.css("tr")]
        documents = [r for r in rows if len(r) >= 4]
        if any(r[3] == "EX-99.1" for r in documents):
            return {
                "columns": [c.text(strip=True) for c in table.css("th")],
                "documents": [r[:4] for r in documents],
                "table": table.html,
            }
    raise ValueError("8-K index table with EX-99.1 not found")


def recordings(client: httpx.Client) -> dict[str, object]:
    if not hasattr(client, "_probe_recordings"):
        client._probe_recordings = {}
    return client._probe_recordings


def _crop(name: str, payload: object) -> object:
    data = copy.deepcopy(payload)
    if name == "sec.tickers":
        rows = data["data"]
        selected = [i for i, row in enumerate(rows) if row[2] == "BRK-B"][:1]
        selected += next(([i] for i, row in enumerate(rows) if row[3] == "OTC"), [])
        selected = list(dict.fromkeys(selected + list(range(len(rows)))))[:25]
        data["data"] = [rows[i] for i in sorted(selected)]
    elif name == "sec.submissions":
        recent = data["filings"]["recent"]
        selected = []
        for form in ("8-K", "8-K/A", "10-Q"):
            selected += next(([i] for i, v in enumerate(recent["form"]) if v == form), [])
        selected = list(dict.fromkeys(selected + list(range(len(recent["form"])))))[:15]
        selected.sort()
        data = {"filings": {"recent": {k: [v[i] for i in selected] for k, v in recent.items()}}}
    elif name.startswith("tencent"):
        data["data"] = {
            s: {k: v[-30:] for k, v in item.items() if k in ("day", "qfqday")}
            for s, item in data["data"].items()
        }
    elif name == "nasdaq_us":
        table = data["data"]["tradesTable"]
        data = {
            "data": {
                "symbol": data["data"].get("symbol"),
                "totalRecords": data["data"].get("totalRecords"),
                "tradesTable": {"rows": table["rows"][:30]},
            }
        }
    elif name == "sec.index":
        data = parse_index(data)["table"]
        if len(data.encode("utf-8")) > 10000:
            raise ValueError("index table exceeds 10 KB; no truncated success fixture")
    return data


def _request(client, name, url, parser, *, headers=None, filename=None, required=True):
    if os.environ.get("SENTINEL_OFFLINE") == "1":
        return ProbeCheck(name, "fail", required, None, None, "OFFLINE; no request", {})
    previous = getattr(client, "_probe_last_request", None)
    if previous is not None:
        time.sleep(max(0, 1 - (time.monotonic() - previous)))
    client._probe_last_request = time.monotonic()
    started = time.perf_counter()
    mode = (
        "synthetic"
        if isinstance(getattr(client, "_transport", None), httpx.MockTransport)
        else "live"
    )
    provenance = {"mode": mode, "url": url, "requestedAt": clock.to_iso(clock.now())}
    try:
        response = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        elapsed = round((time.perf_counter() - started) * 1000)
        return ProbeCheck(name, "fail", required, None, elapsed, type(exc).__name__, provenance)
    elapsed = round((time.perf_counter() - started) * 1000)
    provenance.update(
        {
            "url": str(response.url),
            "fetchedAt": clock.to_iso(clock.now()),
            "httpStatus": response.status_code,
            "elapsedMs": elapsed,
            "contentType": response.headers.get("content-type", ""),
            "httpDate": response.headers.get("date"),
            "responseSha256": hashlib.sha256(response.content).hexdigest(),
        }
    )
    if not required:
        values = parser(response.text)
        return ProbeCheck(
            name,
            "warn",
            False,
            response.status_code,
            elapsed,
            "public negative-source observation",
            {**provenance, **values},
        )
    if response.status_code != 200:
        status = "warn" if response.status_code == 429 else "fail"
        detail = "SEC_FORBIDDEN; check User-Agent" if response.status_code == 403 else "HTTP error"
        return ProbeCheck(
            name,
            status,
            required,
            response.status_code,
            elapsed,
            detail,
            {**provenance, "retryAfter": response.headers.get("retry-after")},
        )
    try:
        if len(response.content) > 5_000_000:
            raise ValueError("response exceeds 5 MB")
        text = response.content.decode("utf-8", errors="strict")
        payload = text if name in ("sec.index", "sec.browse") else json.loads(text)
        values = parser(payload)
        if filename:
            clipped = _crop(name, payload)
            if isinstance(clipped, str):
                clipped = f"<!-- source: {url}; accessed: {provenance['fetchedAt']} -->\n" + clipped
            else:
                clipped["_provenance"] = provenance
            recordings(client)[filename] = clipped
    except JSON_ERRORS as exc:
        detail = f"{exc}; Content-Type={provenance['contentType']}"
        return ProbeCheck(
            name,
            "fail",
            required,
            response.status_code,
            elapsed,
            " ".join(detail.split()),
            provenance,
        )
    status = "warn" if elapsed > 3000 or values.get("fractionalVolumes", 0) else "pass"
    if name == "sec.tickers" and values["rows"] != EXPECTED_TICKER_ROWS:
        status = "warn"
    return ProbeCheck(
        name,
        status,
        required,
        200,
        elapsed,
        "parsed public response",
        {**values, "provenance": provenance},
    )


def probe_sec(contact: str, client: httpx.Client) -> list[ProbeCheck]:
    if not is_valid_sec_email(contact) or contact.rsplit("@", 1)[-1].lower() in (
        "example.com",
        "example.org",
        "example.net",
    ):
        raise ValueError("real SEC contact email required")
    headers = {
        "User-Agent": f"SentinelProbe/0.1 (contact: {contact})",
        "Accept-Encoding": "gzip, deflate",
    }
    checks = [
        _request(
            client,
            "sec.submissions",
            SUBMISSIONS_URL,
            parse_submissions,
            headers=headers,
            filename="submissions_0000320193.probe.json",
        ),
        _request(
            client,
            "sec.tickers",
            TICKERS_URL,
            parse_tickers,
            headers=headers,
            filename="company_tickers_exchange.probe.json",
        ),
        _request(client, "sec.browse", BROWSE_URL, _browse, headers=headers),
    ]
    submission = recordings(client).get("submissions_0000320193.probe.json", {})
    recent = submission.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    if "8-K" in forms:
        accession = recent["accessionNumber"][forms.index("8-K")]
        if re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
            url = (
                "https://www.sec.gov/Archives/edgar/data/320193/"
                f"{accession.replace('-', '')}/{accession}-index.htm"
            )
            checks.append(
                _request(
                    client,
                    "sec.index",
                    url,
                    _index_values,
                    headers=headers,
                    filename="filing_index_8k_ex99.probe.html",
                )
            )
            return checks
    checks.append(
        ProbeCheck(
            "sec.index", "fail", True, None, None, "no recorded valid 8-K accession for index", {}
        )
    )
    return checks


def _browse(html: str) -> dict[str, object]:
    if not HTMLParser(html).css("table.tableFile2"):
        raise ValueError("browse-edgar filing table missing")
    return {"filingTables": len(HTMLParser(html).css("table.tableFile2"))}


def _index_values(html: str) -> dict[str, object]:
    return {k: v for k, v in parse_index(html).items() if k != "table"}


def probe_tencent(client: httpx.Client) -> list[ProbeCheck]:
    checks = []
    for name, symbol in TENCENT_SYMBOLS.items():
        attempts = [
            _request(
                client,
                name,
                TENCENT_URL.format(symbol=symbol, limit=30),
                lambda p, s=symbol: parse_tencent(p, s),
                filename=f"quotes_{name}.probe.json",
            )
            for _ in range(3)
        ]
        status = (
            "fail"
            if any(c.status == "fail" for c in attempts)
            else ("warn" if any(c.status == "warn" for c in attempts) else "pass")
        )
        values = {**attempts[-1].values, "attempts": [asdict(c) for c in attempts]}
        detail = "three sequential attempts; median latency"
        if "rows" in values and values["rows"] < 30:
            status = "fail"
            detail += "; fewer than requested 30 daily rows"
        elapsed = [c.elapsed_ms for c in attempts if c.elapsed_ms is not None]
        median = round(statistics.median(elapsed)) if elapsed else None
        checks.append(
            ProbeCheck(
                name,
                status,
                True,
                attempts[-1].http_status,
                median,
                detail,
                values,
            )
        )
    return checks


def probe_nasdaq(client: httpx.Client) -> list[ProbeCheck]:
    start = (clock.utc_today() - timedelta(days=60)).isoformat()
    url = NASDAQ_URL.format(symbol="AAPL", fromdate=start, limit=30)
    return [
        _request(
            client,
            "nasdaq_us",
            url,
            parse_nasdaq,
            headers={"User-Agent": "Mozilla/5.0 SentinelProbe/0.1", "Accept": "application/json"},
            filename="quotes_nasdaq_us.probe.json",
        )
    ]


def probe_negative(client: httpx.Client) -> list[ProbeCheck]:
    checks, entries = [], []
    for name, url in NEGATIVE_URLS.items():

        def observe(text, source=name):
            available = False
            try:
                payload = json.loads(text)
                if source == "yahoo":
                    available = bool(payload.get("chart", {}).get("result"))
                elif source == "eastmoney":
                    available = bool((payload.get("data") or {}).get("klines"))
            except JSON_ERRORS:
                if source == "stooq":
                    available = (
                        text.startswith("Date,Open,High,Low,Close,Volume")
                        and len(text.splitlines()) > 1
                    )
            return {"available": available, "summary": " ".join(text.split())[:200]}

        check = _request(client, f"negative.{name}", url, observe, required=False)
        checks.append(
            ProbeCheck(
                check.name,
                "warn",
                False,
                check.http_status,
                check.elapsed_ms,
                "observation only; reconsider if available",
                check.values,
            )
        )
        entries.append(
            {
                "source": name,
                "url": url,
                "httpStatus": check.http_status,
                "elapsedMs": check.elapsed_ms,
                **check.values,
            }
        )
    recordings(client)["negative_sources.json"] = {"sources": entries}
    return checks


def probe_continuity(frames: dict[str, list[list[str]]]) -> list[ProbeCheck]:
    checks = []
    for symbol, rows in frames.items():
        try:
            values = {"symbol": symbol, **_row_stats(rows)}
            status = "fail" if values["rows"] < 250 else "warn"
            detail = "row count and >4 calendar-day gaps only; TODO-VERIFY(G1-US) calendar"
        except JSON_ERRORS as exc:
            values, status, detail = {"symbol": symbol}, "fail", str(exc)
        checks.append(ProbeCheck(f"continuity.{symbol}", status, True, None, None, detail, values))
    return checks


def fetch_continuity(client: httpx.Client, symbols: list[str], days: int) -> list[ProbeCheck]:
    checks = []
    for symbol in symbols:
        remote = "us" + symbol.replace(".", "-")
        url = TENCENT_URL.format(symbol=remote, limit=days)

        def parse(payload, s=remote, canonical=symbol):
            values = parse_tencent(payload, s)
            return {**values, "symbol": canonical}

        check = _request(client, f"continuity.{symbol}", url, parse)
        if check.status != "fail" and "rows" in check.values:
            status = "fail" if check.values["rows"] < 250 else "warn"
            check = ProbeCheck(
                check.name,
                status,
                True,
                check.http_status,
                check.elapsed_ms,
                "row count only; TODO-VERIFY(G1-US) calendar/adjustment",
                check.values,
            )
        checks.append(check)
    recordings(client)["prices_250d_summary.json"] = {
        "symbols": [c.values for c in checks],
        "requestedDays": days,
    }
    return checks


def unresolved_checks() -> list[ProbeCheck]:
    return [
        ProbeCheck(f"gate.{name}", "fail", True, None, None, f"TODO-VERIFY(G1-US) {detail}", {})
        for name, detail in (
            ("continuity", "250 trading days require verified exchange calendar and session dates"),
            ("adjustment", "qfqday/day names do not prove split/dividend adjustment"),
            ("terms", "personal-use permission not verified"),
            ("rate", "one-second pacing is not a verified source limit; no load test"),
        )
    ]


def write_fixtures(out: Path, results: list[ProbeCheck], payloads: dict[str, object]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    for filename, payload in payloads.items():
        if Path(filename).name != filename or not filename.endswith((".json", ".html")):
            raise ValueError("unsafe fixture filename")
        text = (
            payload
            if isinstance(payload, str)
            else json.dumps(payload, indent=2, ensure_ascii=True)
        )
        content = (text + "\n").encode("utf-8")
        (out / filename).write_bytes(content)
        files[filename] = hashlib.sha256(content).hexdigest()
    offline = any(c.name.startswith("offline.") for c in results)
    failed = sum(c.required and c.status == "fail" for c in results)
    passed = sum(c.required and c.status != "fail" for c in results)
    manifest = {
        "mode": "offline" if offline else "public-probe",
        "generatedAt": clock.to_iso(clock.now()),
        "gatePassed": False,
        "files": files,
        "checks": [asdict(c) for c in results],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# G1-US source probe report",
        "",
        "Gate: NOT PASSED; SEC/continuity/adjustment/terms/rate evidence required.",
        "Mode: OFFLINE parsing only; no new HTTP evidence."
        if offline
        else "Mode: public observations; historical provenance remains historical.",
        "",
        "| Check | Required | Status | HTTP | Elapsed ms | Values | Conclusion |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in results:
        values = json.dumps(c.values, ensure_ascii=True, sort_keys=True).replace("|", "\\|")
        lines.append(
            f"| {c.name} | {c.required} | {c.status} | {c.http_status} | {c.elapsed_ms} | "
            f"{values} | {c.detail.replace('|', '/')} |"
        )
    lines += [
        "",
        f"required {passed} passed, {failed} failed (warn included in passed per CLI contract)",
        "",
        "Recorded JSON has _provenance; manifest lists clipped-file hashes. "
        "No full prices are retained.",
        "Historical file timestamps are recording times, not verified HTTP access times.",
        "",
    ]
    lines += [f"- {c.detail}" for c in unresolved_checks()]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def offline_checks(source: Path) -> tuple[list[ProbeCheck], dict[str, object]]:
    results, payloads = [], {}
    parsers = {
        "company_tickers_exchange.probe.json": parse_tickers,
        "submissions_0000320193.probe.json": parse_submissions,
        "quotes_nasdaq_us.probe.json": parse_nasdaq,
        "filing_index_8k_ex99.probe.html": _index_values,
    }
    parsers.update(
        {
            f"quotes_{k}.probe.json": lambda p, s=v: parse_tencent(p, s)
            for k, v in TENCENT_SYMBOLS.items()
        }
    )
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    expected = manifest.get("files", {})
    extras = {
        "prices_250d_summary.json",
        "negative_sources.json",
        "schema_observations.json",
        "synthetic_boundaries.json",
    }
    if not isinstance(expected, dict) or set(expected) - set(parsers) - extras:
        raise ValueError("unsupported fixture manifest")
    for filename in set(parsers) | extras | set(expected):
        path = source / filename
        if Path(filename).name != filename:
            raise ValueError("unsafe manifest filename")
        if not path.exists():
            if filename in expected:
                raise ValueError(f"missing manifested fixture {filename}")
            continue
        raw = path.read_bytes()
        if filename in expected and hashlib.sha256(raw).hexdigest() != expected[filename]:
            raise ValueError(f"fixture hash mismatch {filename}")
        try:
            payload = raw.decode("utf-8") if filename.endswith(".html") else json.loads(raw)
            values = parsers[filename](payload) if filename in parsers else {"derivedOnly": True}
            results.append(
                ProbeCheck(
                    f"offline.{filename}",
                    "pass",
                    True,
                    None,
                    None,
                    "local parsing; no live/gate claim",
                    values,
                )
            )
            payloads[filename] = payload
        except JSON_ERRORS as exc:
            results.append(
                ProbeCheck(
                    f"offline.{filename}", "fail", True, None, None, " ".join(str(exc).split()), {}
                )
            )
    if not results:
        raise ValueError("no supported offline fixtures")
    return results, payloads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Public SEC/market source probe")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--contact", default=os.environ.get("SENTINEL_SEC_CONTACT", ""))
    parser.add_argument("--symbols", default="AAPL,MSFT,BRK.B,NVDA,KO")
    parser.add_argument("--days", type=int, default=250)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--offline-fixtures", type=Path)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    symbols = args.symbols.split(",")
    if (
        not 1 <= args.days <= 5000
        or not math.isfinite(args.timeout)
        or args.timeout <= 0
        or not symbols
        or len(set(symbols)) != len(symbols)
        or any(not re.fullmatch(r"[A-Z0-9]+(?:\.[A-Z0-9]+)*", s) for s in symbols)
    ):
        parser.print_usage(sys.stderr)
        return 2
    if not args.offline_fixtures and (
        not is_valid_sec_email(args.contact)
        or args.contact.rsplit("@", 1)[-1].lower() in ("example.com", "example.org", "example.net")
    ):
        parser.print_usage(sys.stderr)
        print("real SEC contact email required", file=sys.stderr)
        return 2
    try:
        if args.offline_fixtures:
            results, payloads = offline_checks(args.offline_fixtures)
        elif os.environ.get("SENTINEL_OFFLINE") == "1":
            results = [ProbeCheck("network", "fail", True, None, None, "OFFLINE; no request", {})]
            payloads = {}
        else:
            timeout = httpx.Timeout(connect=5.0, read=args.timeout, write=10.0, pool=5.0)
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                results = (
                    probe_sec(args.contact, client) + probe_tencent(client) + probe_nasdaq(client)
                )
                results += fetch_continuity(client, symbols, args.days) + probe_negative(client)
                results += unresolved_checks()
                payloads = recordings(client)
        write_fixtures(args.out, results, payloads)
    except (OSError, *JSON_ERRORS) as exc:
        print(f"probe failed: {' '.join(str(exc).split())}", file=sys.stderr)
        return 1
    failed = sum(c.required and c.status == "fail" for c in results)
    passed = sum(c.required and c.status != "fail" for c in results)
    print(f"required {passed} passed, {failed} failed")
    return int(failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
