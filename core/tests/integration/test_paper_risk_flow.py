"""真实核心上的模拟交易、风险与推进。"""

from __future__ import annotations

from tests.integration.harness import CoreHarness


def _account(core: CoreHarness) -> dict[str, object]:
    accounts = core.result("paper.accounts")["items"]
    assert len(accounts) == 1
    return accounts[0]


def test_demo_paper_account_is_ready(core: CoreHarness) -> None:
    core.result("demo.load")
    account = _account(core)
    assert account["name"] == "演示账户"
    assert account["initialCash"] == "100000.0000"
    assert account["clockDate"] == "2026-10-29"


def test_paper_advance_moves_clock_exactly_one_day(core: CoreHarness) -> None:
    core.result("demo.load")
    account = _account(core)
    advanced = core.result("paper.advance", {"accountId": account["accountId"]})
    assert advanced["clockDate"] == "2026-10-30"
    assert advanced["tradingDay"] is True
    assert "equity" in advanced["portfolio"]
    assert advanced["portfolio"]["account"]["clockDate"] == "2026-10-30"
    assert isinstance(advanced["filled"], list) and isinstance(advanced["rejected"], list)


def test_risk_has_60_observations_and_unit_diagonal(core: CoreHarness) -> None:
    core.result("demo.load")
    risk = core.result("risk.compute", {"scope": "holdings", "window": "6M", "currency": "USD"})
    assert risk["window"]["observations"] >= 60
    matrix = risk["correlation"]["matrix"]
    assert len(matrix) == len(risk["correlation"]["instrumentIds"])
    assert all(matrix[index][index] == 1.0 for index in range(len(matrix)))
    assert risk["asOf"] == "2026-10-30"


def test_paper_order_validation_is_rejected_with_reason(core: CoreHarness) -> None:
    core.result("demo.load")
    account = _account(core)
    response = core.request(
        "paper.order.place",
        {
            "accountId": account["accountId"],
            "instrumentId": "us:ZZAR",
            "side": "buy",
            "quantity": 0,
            "orderType": "market_open",
            "idempotencyKey": "11111111-1111-4111-8111-111111111111",
        },
    )
    assert response["error"]["code"] == "INVALID_ARGUMENT"


def test_paper_reset_requires_matching_confirmation(core: CoreHarness) -> None:
    core.result("demo.load")
    account = _account(core)
    wrong = core.request("paper.reset", {"accountId": account["accountId"], "confirmText": "wrong"})
    assert wrong["error"]["code"] == "INVALID_ARGUMENT"
    after = core.result("paper.accounts")["items"]
    assert len(after) == 1
