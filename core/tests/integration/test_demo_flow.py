"""真实核心上的演示数据闭环：载入、清单、处理、清除。"""

from __future__ import annotations

from tests.integration.harness import CoreHarness


def test_demo_load_returns_exact_counts(core: CoreHarness) -> None:
    result = core.result("demo.load")
    assert result["loaded"] is True
    assert result["counts"] == {
        "instruments": 6,
        "holdings": 5,
        "theses": 6,
        "events": 6,
        "decisions": 12,
        "prices": 1560,
    }


def test_demo_inbox_exact_counts(core: CoreHarness) -> None:
    core.result("demo.load")
    inbox = core.result("inbox.list")
    assert [item["relation"] for item in inbox["items"]] == ["overturn", "weaken"]
    assert [item["headline"] for item in inbox["items"]] == [0.93, 0.78]
    assert [item["relation"] for item in inbox["uncertain"]] == ["uncertain"]
    assert inbox["uncertain"][0]["headline"] == 0.71
    assert inbox["summary"]["pendingCount"] == 3
    assert inbox["summary"]["uncertainCount"] == 1
    assert inbox["setup"] == {"holdings": 5, "activeTheses": 6, "scannableInstruments": 5}


def test_decision_detail_has_evidence(core: CoreHarness) -> None:
    core.result("demo.load")
    inbox = core.result("inbox.list")
    detail = core.result("decision.get", {"decisionId": inbox["items"][0]["decisionId"]})
    assert detail["relation"] == "overturn"
    assert detail["evidence"]["kind"] in ("sentence", "passage", "title")
    assert "4.5%" in detail["evidence"]["text"]
    assert detail["thesisIsLatest"] is True
    assert detail["actions"] == []


def test_decision_act_and_reopen(core: CoreHarness) -> None:
    core.result("demo.load")
    inbox = core.result("inbox.list")
    decision_id = inbox["items"][0]["decisionId"]
    acted = core.result("decision.act", {"decisionId": decision_id, "action": "still_valid"})
    assert acted["decisionId"] == decision_id
    after = core.result("inbox.list")
    assert len(after["items"]) == 1
    assert after["summary"]["pendingCount"] == 2
    assert after["summary"]["processedCount"] == 1

    core.result("decision.reopen", {"decisionId": decision_id})
    restored = core.result("inbox.list")
    assert len(restored["items"]) == 2
    assert restored["summary"]["pendingCount"] == 3


def test_demo_load_twice_conflicts(core: CoreHarness) -> None:
    core.result("demo.load")
    second = core.request("demo.load")
    assert second["error"]["code"] == "CONFLICT"
    inbox = core.result("inbox.list")
    assert len(inbox["items"]) == 2


def test_demo_clear_removes_only_demo_rows(core: CoreHarness) -> None:
    core.result("demo.load")
    core.result("demo.clear")
    inbox = core.result("inbox.list")
    assert inbox["items"] == [] and inbox["uncertain"] == []
    assert inbox["setup"]["holdings"] == 0
    core.result("demo.clear")


def test_unconfigured_scan_fails_without_losing_inbox(core: CoreHarness) -> None:
    core.result("demo.load")
    response = core.request("scan.start", {"market": "us"})
    assert response["error"]["code"] == "CONFIG_REQUIRED"
    assert response["error"]["data"]["missing"] == ["jevKey", "secEmail"]
    inbox = core.result("inbox.list")
    assert len(inbox["items"]) == 2
    assert len(inbox["uncertain"]) == 1


def test_scan_requires_email_even_without_key(core: CoreHarness) -> None:
    core.result("demo.load")
    core.result("settings.update", {"secContactEmail": "analyst@example.invalid"})
    response = core.request("scan.start", {"market": "us"})
    assert response["error"]["code"] == "CONFIG_REQUIRED"
    assert response["error"]["data"]["missing"] == ["jevKey"]
    assert len(core.result("inbox.list")["items"]) == 2
