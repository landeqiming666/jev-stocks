from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pytest

from sentinel.markets.prices.calendar import CALENDAR_PATH, TradingCalendar
from sentinel.storage import Database

ROOT = Path(__file__).resolve().parents[4]
NOW = datetime(2026, 11, 2, 23, tzinfo=UTC)
DOCUMENT_RETURNS = np.array(
    [[0.01, 0.035, 0.02], [-0.01, 0.005, -0.02], [0.01, -0.005, -0.02], [-0.01, -0.035, 0.02]],
    dtype=np.float64,
)


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENTINEL_OFFLINE", "1")
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SENTINEL_CLOCK", NOW.isoformat())


@pytest.fixture
def calendar() -> TradingCalendar:
    return TradingCalendar(CALENDAR_PATH)


def trading_days(calendar: TradingCalendar, count: int = 66) -> list[date]:
    days = [date(2026, 7, 1)]
    while len(days) < count:
        days.append(calendar.next_trading_day(days[-1]))
    return days


def risk_input(returns: np.ndarray = DOCUMENT_RETURNS, weights=None, **kwargs):
    from sentinel.quant import RiskInput

    count = returns.shape[1]
    symbols = ["ZZAR", "ZZCL", "ZZFD"][:count]
    return RiskInput(
        symbols=symbols,
        instrument_ids=[f"us:{symbol}" for symbol in symbols],
        returns=returns.copy(),
        weights=np.array(weights if weights is not None else [0.5, 0.3, 0.2][:count]),
        endpoint_closes=np.full(count, 100.0),
        window_observations=len(returns),
        periods_per_year=252,
        price_basis="adj_close",
        as_of=date(2026, 10, 30),
        from_date=date(2026, 7, 2),
        window_label=kwargs.pop("window_label", "1Y"),
        min_observations=kwargs.pop("min_observations", 4),
        **kwargs,
    )


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(tmp_path / "risk.duckdb")
    database.open()
    directory = tmp_path / "migrations"
    directory.mkdir()
    for name in (
        "001_core.sql",
        "002_instrument.sql",
        "003_portfolio.sql",
        "005_prices.sql",
        "011_risk.sql",
    ):
        source = ROOT / "core/sentinel/storage/migrations" / name
        (directory / name).write_bytes(source.read_bytes())
    database.migrate(directory)
    assert database.migrate(directory).applied == ()
    with database.write() as tx:
        for symbol in ("ZZAR", "ZZCL", "ZZFD", "ZZMD"):
            tx.execute(
                "INSERT INTO instrument VALUES (?, 'us', ?, 'NASDAQ', ?, NULL, 'USD', "
                "NULL, TRUE, 'demo', ?)",
                [f"us:{symbol}", symbol, f"Synthetic {symbol}", NOW],
            )
    try:
        yield database
    finally:
        database.close()
