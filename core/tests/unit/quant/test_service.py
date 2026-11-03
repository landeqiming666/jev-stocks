import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

import jsonschema
import numpy as np
import pytest
from referencing import Registry, Resource

from sentinel.rpc.cancel import CancelToken
from sentinel.rpc.dispatcher import Dispatcher, RequestContext

from .conftest import NOW, ROOT, trading_days


def test_single_holding_and_service_audit(calendar, tmp_path):
    # fixture 延迟到测试内调用，以便实现前 11 项全部执行并失败。
    from sentinel.quant import RiskService
    from sentinel.quant.service import register_handlers
    from sentinel.storage import Database

    database = Database(tmp_path / "service.duckdb")
    database.open()
    try:
        directory = tmp_path / "service-migrations"
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
        days = trading_days(calendar)
        closes = 100 * np.cumprod([1.0] + [1.01 if i % 2 else 0.99 for i in range(65)])
        with database.write() as tx:
            for symbol, qty in (
                ("ZZAR", Decimal("0.0001")),
                ("ZZFD", Decimal(0)),
                ("ZZCL", Decimal(2)),
            ):
                tx.execute(
                    "INSERT INTO instrument VALUES (?, 'us', ?, 'NASDAQ', ?, NULL, "
                    "'USD', NULL, TRUE, 'demo', ?)",
                    [f"us:{symbol}", symbol, f"Synthetic {symbol}", NOW],
                )
                tx.execute(
                    "INSERT INTO holding VALUES (?, ?, ?, NULL, NULL, ?, ?, ?)",
                    [symbol, f"us:{symbol}", qty, NOW, NOW, NOW if symbol == "ZZCL" else None],
                )
            tx.executemany(
                "INSERT INTO price_daily VALUES ('us:ZZAR', ?, NULL, NULL, NULL, "
                "?, ?, NULL, 'demo', ?)",
                [
                    [day, float(close), float(close) * 2, NOW]
                    for day, close in zip(days, closes, strict=True)
                ],
            )
        service = RiskService(database, calendar=calendar, clock=lambda: NOW)
        dispatcher = Dispatcher()
        register_handlers(dispatcher, service)
        ctx = RequestContext("risk-1", "risk.compute", CancelToken(), NOW)
        response = dispatcher.dispatch(
            dispatcher.lookup("risk.compute"),
            {"scope": "holdings", "window": "1Y", "currency": "USD"},
            ctx,
        )
        assert "error" not in response, response
        result = response["result"]
        assert result["correlation"]["matrix"] == [[1.0]]
        assert "至少需要 2 只持仓" in result["warnings"]
        assert result["window"]["observations"] == 65
        assert result["topWeights"][0]["weight"] == 1.0
        assert result["svd"]["explained"] == [1.0]
        assert [item["symbol"] for item in result["excluded"]] == ["ZZFD"]
        with database.read() as reader:
            reader.execute("SELECT instrument_ids, params_json, result_json FROM risk_run")
            ids, params, audit = reader.fetchone()
        assert json.loads(ids) == ["us:ZZAR"]
        assert json.loads(params)["periods_per_year"] == 252
        assert json.loads(audit) == result
        assert json.dumps(result, allow_nan=False)
    finally:
        database.close()


def seed(
    db, calendar, quantities=(Decimal("0.1250"), Decimal("0.5000"), Decimal("0.2500")), count=66
):
    days = trading_days(calendar, count)
    with db.write() as tx:
        for j, (symbol, qty) in enumerate(zip(("ZZAR", "ZZCL", "ZZFD"), quantities, strict=True)):
            tx.execute(
                "INSERT INTO holding VALUES (?, ?, ?, NULL, NULL, ?, ?, NULL)",
                [symbol, f"us:{symbol}", qty, NOW, NOW],
            )
            tx.executemany(
                "INSERT INTO price_daily VALUES (?, ?, NULL, NULL, NULL, ?, ?, NULL, 'demo', ?)",
                [
                    [f"us:{symbol}", day, 100.0 + i * (j + 1), 100.0 + i * (j + 1), NOW]
                    for i, day in enumerate(days)
                ],
            )
    return days


def call(service, params):
    from sentinel.quant.service import register_handlers

    dispatcher = Dispatcher()
    register_handlers(dispatcher, service)
    return dispatcher.dispatch(
        dispatcher.lookup("risk.compute"),
        params,
        RequestContext("risk-1", "risk.compute", CancelToken(), NOW),
    )


def count_audit(db):
    with db.read() as reader:
        reader.execute("SELECT count(*) FROM risk_run")
        return reader.fetchone()[0]


def test_fractional_weights_schema_and_audit_input_match(db, calendar):
    from sentinel.quant import RiskService

    days = seed(db, calendar)
    service = RiskService(db, calendar=calendar, clock=lambda: NOW)
    response = call(service, {"scope": "holdings", "window": "3Y", "currency": "USD"})
    assert "error" not in response, response
    result = response["result"]
    schema = json.loads((ROOT / "contracts/types.schema.json").read_text())
    registry = Registry().with_resource("types.schema.json", Resource.from_contents(schema))
    method = json.loads((ROOT / "contracts/methods/risk.compute.json").read_text())
    jsonschema.Draft202012Validator(
        method["result"], registry=registry, format_checker=jsonschema.FormatChecker()
    ).validate(result)
    values = [Decimal("0.1250") * 165, Decimal("0.5000") * 230, Decimal("0.2500") * 295]
    expected = [float(value / sum(values)) for value in values]
    actual = {item["symbol"]: item["weight"] for item in result["topWeights"]}
    assert [actual[s] for s in ("ZZAR", "ZZCL", "ZZFD")] == pytest.approx(expected)
    with db.read() as reader:
        reader.execute("SELECT computed_at, observations, params_json, result_json FROM risk_run")
        computed_at, observations, raw, audit = reader.fetchone()
    params = json.loads(raw)
    assert computed_at == NOW and observations == 65
    assert json.loads(audit) == result
    assert params["input"]["quantities"]["us:ZZAR"] == "0.1250"
    snapshot_json = json.dumps(
        params["input"], allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    assert hashlib.sha256(snapshot_json.encode()).hexdigest() == params["input_sha256"]
    assert params["input"]["return_dates"] == [day.isoformat() for day in days[1:]]


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"scope": "holdings", "window": "1Y"},
        {"scope": "holdings", "window": "1y", "currency": "USD"},
        {"scope": "paper", "window": "1Y", "currency": "USD"},
        {"scope": "holdings", "window": "1Y", "currency": "CNY"},
        {"scope": True, "window": "1Y", "currency": "USD"},
        {"scope": "holdings", "window": "1Y", "currency": "USD", "minObservations": 4},
        {"scope": "holdings", "window": "1Y", "currency": "USD", "min_observations": 4},
        {"scope": "holdings", "window": "1Y", "currency": "USD", "shrinkageAlpha": 0.1},
        [],
    ],
)
def test_rpc_strict_wire_arguments_do_not_write_audit(db, calendar, params):
    from sentinel.quant import RiskService

    response = call(RiskService(db, calendar=calendar, clock=lambda: NOW), params)
    assert response["error"]["code"] == "INVALID_ARGUMENT"
    assert count_audit(db) == 0


@pytest.mark.parametrize("count,quantity,observations", [(60, Decimal(1), 59), (66, Decimal(0), 0)])
def test_insufficient_rpc_has_chinese_details_and_no_audit(
    db, calendar, count, quantity, observations
):
    from sentinel.quant import RiskService

    seed(db, calendar, (quantity, quantity, quantity), count=count)
    response = call(
        RiskService(db, calendar=calendar, clock=lambda: NOW),
        {"scope": "holdings", "window": "1Y", "currency": "USD"},
    )
    error = response["error"]
    assert error["code"] == "DATA_INSUFFICIENT"
    assert error["data"]["observations"] == observations and error["data"]["required"] == 60
    if observations:
        assert "样本不足" in error["message"] and "ZZAR" in error["message"]
    else:
        assert "没有可计算的持仓" in error["message"]
    assert "detail" not in error["data"]
    assert count_audit(db) == 0


def test_future_and_unclosed_prices_do_not_affect_result(db, calendar):
    from sentinel.quant import RiskService

    days = seed(db, calendar)
    before_open = datetime.combine(days[-1], datetime.min.time(), UTC)
    service = RiskService(db, calendar=calendar, clock=lambda: before_open)
    first = service.compute("holdings", "1Y", "USD")
    assert first.as_of == days[-2]
    with db.write() as tx:
        tx.execute(
            "UPDATE price_daily SET close = 1e99, adj_close = NULL WHERE trade_date = ?", [days[-1]]
        )
        tx.execute(
            "INSERT INTO price_daily VALUES ('us:ZZAR', '2027-01-04', NULL, NULL, NULL, "
            "1e99, NULL, NULL, 'future', ?)",
            [NOW],
        )
    assert service.compute("holdings", "1Y", "USD") == first


def test_audit_insert_failure_rolls_back_and_surfaces_internal(db, calendar, monkeypatch):
    import sentinel.quant.service as risk_service

    seed(db, calendar)
    service = risk_service.RiskService(db, calendar=calendar, clock=lambda: NOW)
    monkeypatch.setattr(risk_service, "new_id", lambda: "synthetic-same-id")
    service.compute("holdings", "1Y", "USD")
    response = call(service, {"scope": "holdings", "window": "1Y", "currency": "USD"})
    assert response["error"]["code"] == "INTERNAL"
    assert count_audit(db) == 1
    with db.write() as tx:
        tx.execute("UPDATE holding SET note = 'after rollback' WHERE instrument_id = 'us:ZZAR'")


def test_011_authoritative_ddl_and_recorded_checksum(db):
    source = (ROOT / "docs/04-数据模型.md").read_text()
    ddl = source.split("### 3.11 `", 1)[1].split("```sql\n", 1)[1].split("```", 1)[0]
    migration = ROOT / "core/sentinel/storage/migrations/011_risk.sql"
    assert migration.read_text() == ddl
    with db.read() as reader:
        reader.execute("SELECT name, checksum FROM schema_version WHERE version = 11")
        assert reader.fetchone() == ("risk", hashlib.sha256(ddl.encode()).hexdigest())
