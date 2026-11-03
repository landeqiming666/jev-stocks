import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime

import pytest

from .conftest import ROOT


def test_calendar_holiday_is_not_trading_day():
    from sentinel.markets.prices.calendar import is_trading_day, market_state

    assert not is_trading_day(date(2026, 11, 26))
    assert market_state(datetime(2026, 11, 26, 16, tzinfo=UTC)).status == "holiday"


def test_calendar_early_close_and_dst():
    from sentinel.markets.prices.calendar import session_close

    for day, hour in ((date(2026, 11, 27), 18), (date(2026, 3, 9), 20), (date(2026, 11, 2), 21)):
        assert session_close(day) == datetime.combine(day, datetime.min.time(), UTC).replace(
            hour=hour
        )


def test_calendar_out_of_range_uses_weekday(caplog):
    from sentinel.markets.prices.calendar import is_trading_day

    assert is_trading_day(date(2030, 1, 1))
    assert "calendar.out_of_range" in caplog.text


@pytest.mark.parametrize(
    "day,status,opening",
    [
        ("2026-11-02T08:59:59Z", "closed", "2026-11-02T14:30:00Z"),
        ("2026-11-02T09:00:00Z", "pre", "2026-11-02T14:30:00Z"),
        ("2026-11-02T14:29:59Z", "pre", "2026-11-02T14:30:00Z"),
        ("2026-11-02T14:30:00Z", "open", "2026-11-03T14:30:00Z"),
        ("2026-11-02T20:59:59Z", "open", "2026-11-03T14:30:00Z"),
        ("2026-11-02T21:00:00Z", "after", "2026-11-03T14:30:00Z"),
        ("2026-11-03T00:59:59Z", "after", "2026-11-03T14:30:00Z"),
        ("2026-11-03T01:00:00Z", "closed", "2026-11-03T14:30:00Z"),
        ("2026-11-27T17:59:59Z", "open", "2026-11-30T14:30:00Z"),
        ("2026-11-27T18:00:00Z", "after", "2026-11-30T14:30:00Z"),
        ("2026-11-26T18:00:00Z", "holiday", "2026-11-27T14:30:00Z"),
        ("2026-11-28T18:00:00Z", "holiday", "2026-11-30T14:30:00Z"),
        ("2026-03-08T18:00:00Z", "holiday", "2026-03-09T13:30:00Z"),
        ("2026-11-01T18:00:00Z", "holiday", "2026-11-02T14:30:00Z"),
    ],
)
def test_states_boundaries_and_future_next_open(day, status, opening):
    from sentinel.markets.prices.calendar import market_state

    now = datetime.fromisoformat(day)
    state = market_state(now)
    assert state.status == status
    assert state.next_open_at == datetime.fromisoformat(opening)
    assert state.next_open_at > now


def test_carter_closure_strict_next_previous_and_dst():
    from sentinel.markets.prices.calendar import (
        is_trading_day,
        next_trading_day,
        prev_trading_day,
        session_close,
    )

    assert not is_trading_day(date(2025, 1, 9))
    assert next_trading_day(date(2025, 1, 8)) == date(2025, 1, 10)
    assert prev_trading_day(date(2025, 1, 10)) == date(2025, 1, 8)
    assert next_trading_day(date(2026, 11, 25)) == date(2026, 11, 27)
    assert prev_trading_day(date(2026, 11, 30)) == date(2026, 11, 27)
    assert session_close(date(2026, 3, 6)).hour == 21
    assert session_close(date(2026, 3, 9)).hour == 20
    assert session_close(date(2026, 10, 30)).hour == 20
    assert session_close(date(2026, 11, 2)).hour == 21
    with pytest.raises(ValueError):
        session_close(date(2025, 1, 9))


@pytest.mark.parametrize(
    "key,value",
    [
        ("market", "hk"),
        ("timezone", "UTC"),
        ("years", [True]),
        ("years", []),
        ("years", [2026, 2025]),
        ("years", [2025, 2025]),
        ("regular_open", "9:30"),
        ("regular_close", "25:00"),
        ("pre_open", "17:00"),
        ("holidays", {}),
        ("early_closes", [{"date": "2026-11-27", "close": "16:00"}]),
    ],
)
def test_calendar_rejects_invalid_configuration(tmp_path, key, value):
    from sentinel.markets.prices.calendar import TradingCalendar

    data = json.loads((ROOT / "resources/calendars/us.json").read_text())
    data[key] = value
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        TradingCalendar(path)


def test_calendar_duplicate_and_outside_year_dates_rejected(tmp_path):
    from sentinel.markets.prices.calendar import TradingCalendar

    for extra in [{"date": "2026-11-26"}, {"date": "2030-01-01"}, {"date": "2026-11-28"}]:
        data = json.loads((ROOT / "resources/calendars/us.json").read_text())
        data["holidays"].append(extra)
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError):
            TradingCalendar(path)


def test_outside_year_warns_once_under_concurrent_calls(caplog):
    from sentinel.markets.prices.calendar import TradingCalendar

    calendar = TradingCalendar(ROOT / "resources/calendars/us.json")
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(calendar.is_trading_day, [date(2030, 1, 1)] * 12))
    assert caplog.text.count("calendar.out_of_range") == 1
    assert not calendar.is_trading_day(date(2030, 1, 5))


def test_naive_clock_rejected():
    from sentinel.markets.prices.calendar import market_state

    with pytest.raises(ValueError):
        market_state(datetime(2026, 11, 2, 12))


def test_every_calendar_entry_has_source():
    data = json.loads((ROOT / "resources/calendars/us.json").read_text())
    sources = (ROOT / "resources/calendars/SOURCES.md").read_text()
    assert data["years"] == [2025, 2026, 2027]
    assert len(data["holidays"]) == 31
    assert len(data["early_closes"]) == 6
    for row in data["holidays"] + data["early_closes"]:
        assert f"| {row['date']} |" in sources
    assert "direct HTTP 403" in sources
