import math
from decimal import Decimal

import pytest

from sentinel.errors import InternalError
from sentinel.portfolio import PortfolioService
from sentinel.storage import Database

from .conftest import NOW, add_downstream, query

BAD_CLOSES = [
    pytest.param(-7.25, id="negative"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
]


def insert_prices(db: Database, closes: list[tuple[str, float | None]]) -> None:
    with db.write() as tx:
        tx.executemany(
            "INSERT INTO price_daily VALUES ('us:ZZAR', ?, "
            "NULL, NULL, NULL, ?, NULL, 1, 'demo', ?)",
            [[trade_date, close, NOW] for trade_date, close in closes],
        )


def assert_safe_price_error(error: InternalError) -> None:
    assert error.code == "INTERNAL"
    assert error.detail == "invalid latest holding price"
    assert error.__cause__ is None
    wire = error.to_wire("r-bad-price")
    assert wire["data"] == {
        "retryable": True,
        "requestId": "r-bad-price",
        "detail": "invalid latest holding price",
    }


@pytest.mark.parametrize("close", BAD_CLOSES)
@pytest.mark.parametrize("quantity", ["0", "2"])
def test_list_holdings_bad_latest_price_raises_safe_internal(
    service: PortfolioService, db: Database, close: float, quantity: str
) -> None:
    service.upsert_holding("us:ZZAR", Decimal(quantity), None, "original")
    add_downstream(db, ("3.5",))
    insert_prices(db, [("2026-10-29", 5.0), ("2026-10-30", close)])
    stored = query(db, "SELECT close FROM price_daily ORDER BY trade_date DESC")[0][0]
    assert isinstance(stored, float)
    assert math.isnan(stored) if math.isnan(close) else stored == close
    before = query(db, "SELECT * FROM holding")
    with pytest.raises(InternalError) as caught:
        service.list_holdings()
    assert_safe_price_error(caught.value)
    assert query(db, "SELECT * FROM holding") == before


@pytest.mark.parametrize("close", BAD_CLOSES)
@pytest.mark.parametrize("existing", ["absent", "active", "archived"])
def test_upsert_bad_latest_price_rolls_back_entire_holding(
    service: PortfolioService,
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
    close: float,
    existing: str,
) -> None:
    if existing != "absent":
        service.upsert_holding("us:ZZAR", Decimal("2"), Decimal("12"), "original")
        if existing == "archived":
            service.archive_holding("us:ZZAR")
    add_downstream(db, ("3.5",))
    insert_prices(db, [("2026-10-29", 5.0), ("2026-10-30", close)])
    before = query(db, "SELECT * FROM holding")
    monkeypatch.setenv("SENTINEL_CLOCK", "2026-11-03T00:35:00Z")
    with pytest.raises(InternalError) as caught:
        service.upsert_holding("us:ZZAR", Decimal("9"), Decimal("20"), "changed")
    assert_safe_price_error(caught.value)
    assert query(db, "SELECT * FROM holding") == before


@pytest.mark.parametrize("close", [None, 0.0])
@pytest.mark.parametrize("previous", [-5.0, 0.0, 5.0])
def test_null_zero_latest_price_and_nonpositive_previous_keep_query_semantics(
    service: PortfolioService, db: Database, close: float | None, previous: float
) -> None:
    service.upsert_holding("us:ZZAR", Decimal("2"), None, None)
    add_downstream(db, ("3.5",))
    insert_prices(db, [("2026-10-29", previous), ("2026-10-30", close)])
    for view in (
        service.list_holdings()[0],
        service.upsert_holding("us:ZZAR", Decimal("3"), None, None),
    ):
        assert view.last_close == close
        assert view.last_close_date == "2026-10-30"
        assert view.market_value == (None if close is None else Decimal("0.0000"))
        assert view.day_change_pct == (None if close is None or previous <= 0 else -1.0)


@pytest.mark.parametrize("close", BAD_CLOSES)
def test_bad_older_price_does_not_reject_valid_selected_latest(
    service: PortfolioService, db: Database, close: float
) -> None:
    service.upsert_holding("us:ZZAR", Decimal("2"), None, None)
    add_downstream(db, ("3.5",))
    insert_prices(db, [("2026-10-28", close), ("2026-10-29", 5.0), ("2026-10-30", 10.0)])
    latest = service.list_holdings()[0]
    assert latest.last_close == 10.0 and latest.day_change_pct == 1.0
    assert latest.market_value == Decimal("20.0000")
