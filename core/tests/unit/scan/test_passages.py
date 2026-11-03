from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast

import httpx
import httpx2
import pytest

from sentinel import clock
from sentinel.errors import SentinelError
from sentinel.http import HttpClient
from sentinel.markets.sec import (
    EventFileDraft,
    SecFilingsClient,
    SecFilingsRepository,
    SecFilingsService,
)
from sentinel.semantic.base import PairInput, SemanticEngine
from sentinel.semantic.budget import reserve_tokens
from sentinel.semantic.pipeline import BatchContext, DecisionPipeline, estimate_pair_tokens
from sentinel.storage.db import Database
from tests.unit.scan.test_orchestrator import INSTRUMENT, NOW, event, finish
from tests.unit.scan.test_orchestrator import db as db
from tests.unit.scan.test_orchestrator import stack as stack


def test_unicode_offsets_hashes_and_file_order_are_permanent(db: Database) -> None:
    from sentinel.scan.passages import persist_passages

    text = "  😀 Alpha. 𠀀公司减少研发。 e\u0301 grows.\r\n" + "X" * 1300
    row = event(text=text)
    SecFilingsRepository(db).upsert(row)
    saved = persist_passages(db, row)
    assert len(saved) == 3 and all(len(p.text) <= 1200 for p in saved)
    with db.read() as reader:
        reader.execute(
            "SELECT file_seq, start_offset, end_offset, text, passage_id FROM "
            "event_passage ORDER BY seq"
        )
        spans = reader.fetchall()
    for file_seq, start, end, value, identity in spans:
        assert text[cast(int, start) : cast(int, end)] == value
        expected = hashlib.sha256(
            f"{row.event.event_id}|{file_seq}|{start}|{end}".encode()
        ).hexdigest()[:32]
        assert identity == expected
    assert persist_passages(db, row) == saved


def test_title_only_is_a_single_deterministic_title(db: Database) -> None:
    from sentinel.scan.passages import persist_passages

    row = replace(event(text=None), title="Synthetic title 😀")
    SecFilingsRepository(db).upsert(row)
    result = persist_passages(db, row)
    assert result[0].text == row.title and result[0].content_status == "title_only"
    with db.read() as reader:
        reader.execute("SELECT file_seq, seq, start_offset, end_offset FROM event_passage")
        assert reader.fetchone() == (-1, 0, 0, len(row.title))


def test_fetch_failed_never_becomes_a_zero_passage_success(stack: Any) -> None:
    service, filings, pipeline, *_ = stack
    filings.events = [replace(event(text=None), content_status="fetch_failed")]
    result = finish(service, service.start("us"))
    assert result.run.status == "failed" and result.batches[0].status == "failed"
    assert result.batches[0].error.code == "SOURCE_UNAVAILABLE" and pipeline.calls == []


def test_immutable_passage_identity_is_not_overwritten(db: Database) -> None:
    from sentinel.scan.passages import persist_passages

    row = event(text="Original fact.")
    SecFilingsRepository(db).upsert(row)
    original = persist_passages(db, row)
    changed = replace(row, files=[replace(row.files[0], text="Modified fact.", char_count=14)])
    with pytest.raises(SentinelError, match="CONFLICT"):
        persist_passages(db, changed)
    with db.read() as reader:
        reader.execute("SELECT text FROM event_passage")
        assert reader.fetchone() == (original[0].text,)


def test_sixty_per_file_and_sixty_scored_per_event(stack: Any, db: Database) -> None:
    from tests.unit.semantic.test_pipeline import Engine

    service, filings, *_ = stack
    text = "X" * (1200 * 61)
    row = event(text=text)
    extra = replace(
        row.files[0],
        seq=2,
        file_name="ex99.htm",
        doc_type="EX-99.1",
        url=row.files[0].url.replace("main.htm", "ex99.htm"),
    )
    filings.events = [replace(row, files=[extra, row.files[0]])]
    engine = Engine()
    pipeline = DecisionPipeline(
        db, cast(SemanticEngine, engine), model_id="jev-1.14.0", daily_budget=2_000_000
    )
    service.pipeline_resolver = lambda _: pipeline
    result = finish(service, service.start("us"))
    assert result.run.stats.passages == 120 and result.run.stats.decisions == 60
    assert len(engine.pairs[0]) == 60
    with db.read() as reader:
        reader.execute("SELECT count(*) FROM event_passage WHERE file_seq=0")
        assert reader.fetchone() == (60,)


@pytest.mark.parametrize("over", [0, 1])
def test_real_budget_used_plus_twenty_percent_reserve(stack: Any, db: Database, over: int) -> None:
    from sentinel.scan.passages import persist_passages
    from sentinel.settings.models import SettingsPatch
    from tests.unit.semantic.test_pipeline import Engine

    service, filings, _, _, settings, _ = stack
    settings.update(SettingsPatch(daily_token_budget=10_000))
    row = event()
    SecFilingsRepository(db).upsert(row)
    passage = persist_passages(db, row)[0]
    raw = estimate_pair_tokens(
        PairInput(service._theses(INSTRUMENT.instrument_id)[0], passage.as_input()), "jev_direct"
    )
    with db.write() as tx:
        tx.execute(
            "INSERT INTO usage_daily VALUES (?, 'jevdb', 'jev-1.14.0', 0, ?, 1)",
            [NOW.date(), 10_000 - reserve_tokens(raw) + over],
        )
    engine = Engine()
    pipeline = DecisionPipeline(
        db, cast(SemanticEngine, engine), model_id="jev-1.14.0", daily_budget=10_000
    )
    service.pipeline_resolver = lambda _: pipeline
    result = finish(service, service.start("us"))
    if over:
        assert result.run.status == "failed" and result.batches[0].status == "pending"
        assert result.batches[0].error.code == "BUDGET_EXCEEDED" and not engine.pairs
    else:
        assert result.run.status == "succeeded" and result.run.stats.input_tokens == 10


@pytest.mark.parametrize("retry_mode", ["manual", "new_run"])
def test_real_d03_and_s05_mock_transports_restore_failed_file_preserving_references(
    stack: Any, db: Database, retry_mode: str
) -> None:
    from sentinel.markets.sec.submissions import RECENT_FIELDS
    from sentinel.scan.passages import persist_passages
    from sentinel.semantic.engines.jev_direct import JevDirectEngine, sdk_client_factory

    service, _, _, _, settings, _ = stack
    row = event(text="Synthetic main disclosure.")
    ref = row.event
    source_calls: list[str] = []
    model_calls: list[dict[str, Any]] = []
    failed = True
    elapsed = [0.0]
    recent: dict[str, list[object]] = {name: [""] for name in RECENT_FIELDS}
    recent.update(
        accessionNumber=[ref.accession],
        filingDate=[str(ref.filing_date)],
        acceptanceDateTime=[clock.to_iso(ref.published_at)],
        form=["8-K"],
        primaryDocument=["main.htm"],
        primaryDocDescription=["Synthetic"],
        items=[""],
    )
    index = (
        "<table><tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th></tr><tr><td>2</td><td>Press</td><td><a"
        ' href="ex99.htm">ex99.htm</a></td><td>EX-99.1</td></tr></table>'
    )

    def sec_response(request: httpx.Request) -> httpx.Response:
        source_calls.append(str(request.url))
        assert "synthetic@example.invalid" in request.headers["user-agent"]
        if request.url.path.endswith(".json"):
            return httpx.Response(200, json={"filings": {"recent": recent}})
        if request.url.path.endswith("-index.htm"):
            return httpx.Response(200, text=index)
        if request.url.path.endswith("main.htm"):
            pytest.fail("successful referenced main must not be downloaded")
        assert request.url.path.endswith("ex99.htm")
        return httpx.Response(403 if failed else 200, text="<p>😀 First fact. 𠀀公司减少研发。</p>")

    def model_response(request: httpx2.Request) -> httpx2.Response:
        payload = json.loads(request.content)
        model_calls.append(payload)
        return httpx2.Response(
            200,
            json={
                "model": "jev-1.14.0",
                "answers": {
                    name: {
                        "type": "noul",
                        "noul": (
                            0.1
                            if payload["state"].get("document") == row.files[0].text
                            else 0.95
                            if name.endswith(("relevant", "contradicts")) or name == "s2"
                            else 0.05
                        ),
                    }
                    for name in payload["questions"]
                },
                "usage": {"input_tokens": 11, "output_tokens": 0},
            },
        )

    engine = JevDirectEngine(
        api_key="synthetic-p02-key",
        model_id="jev-1.14.0",
        client_factory=sdk_client_factory(transport=httpx2.MockTransport(model_response)),
    )
    pipeline = DecisionPipeline(
        db, cast(SemanticEngine, engine), model_id="jev-1.14.0", daily_budget=2_000_000
    )
    service.pipeline_resolver = lambda _: pipeline
    repo = SecFilingsRepository(db)
    repo.upsert(row)
    main = persist_passages(db, row)
    pipeline.process_batch(
        BatchContext(
            "synthetic-seed-run",
            "synthetic-seed-batch",
            ref.event_id,
            ref.instrument_id,
            INSTRUMENT.name,
        ),
        service._theses(ref.instrument_id),
        main,
        service_token(),
    )
    with db.read() as reader:
        reader.execute("SELECT decision_id,passage_id FROM decision")
        references = reader.fetchall()
    seed_calls = len(model_calls)
    exhibit = EventFileDraft(
        2,
        "ex99.htm",
        "EX-99.1",
        row.files[0].url.replace("main.htm", "ex99.htm"),
        "failed",
        None,
        None,
    )
    repo.upsert(replace(row, files=[row.files[0], exhibit], content_status="fetch_failed"))
    with HttpClient(
        transport=httpx.MockTransport(sec_response), monotonic=lambda: time.monotonic() + elapsed[0]
    ) as http:
        service.filings = SecFilingsService(
            SecFilingsClient(http, email_provider=lambda: settings.get().sec_contact_email),
            repo,
            clock.now,
        )
        first = finish(service, service.start("us"))
        assert first.run.status == "failed" and first.batches[0].status == "failed"
        assert first.run.stats.requests == 0 and len(model_calls) == seed_calls
        failed = False
        elapsed[0] = 601.0  # 显式推进 HTTP 熔断冷却时钟，不跳过真实熔断策略。
        if retry_mode == "manual":
            batch = service.retry_batch(first.batches[0].batch_id)
            view = service.status(first.run.run_id)
            assert view.status == "failed"
        else:
            view_detail = finish(service, service.start("us"))
            batch, view = view_detail.batches[0], view_detail.run
            assert view.status == "succeeded"
        assert batch.status == "succeeded"
        assert view.stats.requests == 2 and view.stats.input_tokens == 22
        assert view.stats.decisions == 1 and view.stats.cached_decisions == 1
        with db.read() as reader:
            reader.execute("SELECT decision_id,passage_id FROM decision")
            assert set(references).issubset(set(reader.fetchall()))
            reader.execute(
                "SELECT text,evidence_start,evidence_end FROM decision JOIN "
                "event_passage USING(passage_id) WHERE evidence_kind='sentence'"
            )
            slices = [
                cast(str, text)[cast(int, start) : cast(int, end)]
                for text, start, end in reader.fetchall()
            ]
            assert "𠀀公司减少研发。" in slices
        before = len(model_calls)
        cached = finish(service, service.start("us", NOW - timedelta(days=7))).run
        assert cached.stats.requests == cached.stats.input_tokens == 0
        assert len(model_calls) == before
    assert not any(url.endswith("main.htm") for url in source_calls)


def service_token() -> Any:
    from sentinel.rpc.cancel import CancelToken

    return CancelToken()
