"""虚构标的走真实持仓 handler；临时 DuckDB 与离线环境隔离真实数据。"""
import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sentinel.portfolio import PortfolioService, register_handlers
from sentinel.rpc import CancelToken, Dispatcher
from sentinel.rpc.dispatcher import RequestContext
from sentinel.storage import Database

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / "apps/desktop/test-results/u03"
NOW = datetime(2026, 11, 2, 0, 35, tzinfo=UTC)
os.environ["SENTINEL_OFFLINE"] = "1"
os.environ["SENTINEL_CLOCK"] = "2026-11-02T00:35:00Z"
responses = []
with tempfile.TemporaryDirectory(prefix="portfolio-", dir=OUT) as folder:
    temp = Path(folder)
    os.environ["SENTINEL_DATA_DIR"] = str(temp)
    migrations = temp / "migrations"
    migrations.mkdir()
    for path in (ROOT / "core/sentinel/storage/migrations").glob("*.sql"):
        if int(path.name.split("_")[0]) <= 7:
            shutil.copyfile(path, migrations / path.name)
    db = Database(temp / "synthetic.duckdb")
    db.open()
    db.migrate(migrations)
    with db.write() as tx:
        tx.execute(
            "INSERT INTO instrument VALUES (?, ?, ?, 'NASDAQ', ?, NULL, ?, NULL, ?, 'demo', ?)",
            ["us:ZZAR", "us", "ZZAR", "Zenith Arc Robotics Inc.", "USD", True, NOW],
        )
    dispatcher = Dispatcher()
    register_handlers(dispatcher, PortfolioService(db))

    def call(method, params, code=None):
        response = dispatcher.dispatch(dispatcher.lookup(method), params, RequestContext("u03", method, CancelToken(), NOW))
        responses.append({"method": method, "response": response})
        if code:
            assert response["error"]["code"] == code, response
            return response["error"]
        assert "result" in response, response
        return response["result"]

    maximum = "99999999999999.9999"
    row = call("holdings.upsert", {"instrumentId": "us:ZZAR", "quantity": maximum, "avgCost": maximum, "note": " 🧪 "})
    assert row["quantity"] == maximum and row["avgCost"] == maximum and row["note"] == "🧪"
    call("holdings.upsert", {"instrumentId": "us:ZZAR", "quantity": "0", "avgCost": "1"}, "INVALID_ARGUMENT")
    row = call("holdings.upsert", {"instrumentId": "us:ZZAR", "quantity": "0", "avgCost": None})
    assert row["quantity"] == "0.0000"
    created = call("thesis.create", {"instrumentId": "us:ZZAR", "statement": " \u0085" + "🧪" * 500, "killCondition": "🧪" * 300})
    assert len(created["statement"]) == 500
    thesis_id = created["thesisId"]
    updated = call("thesis.update", {"thesisId": thesis_id, "statement": "new reason", "expectedVersion": 1})
    assert updated["version"] == 2
    call("thesis.update", {"thesisId": thesis_id, "statement": "my draft", "expectedVersion": 1}, "CONFLICT")
    assert len(call("thesis.versions", {"thesisId": thesis_id})["items"]) == 2
    assert call("thesis.list", {"instrumentId": "us:ZZAR", "status": "active"})["items"][0]["statement"] == "new reason"
    call("thesis.archive", {"thesisId": thesis_id})
    assert call("holdings.list", {})["items"][0]["status"] == "unguarded"
    call("holdings.archive", {"instrumentId": "us:ZZAR"})
    assert not call("holdings.list", {})["items"]
    assert len(call("thesis.versions", {"thesisId": thesis_id})["items"]) == 2
    db.close()
OUT.joinpath("portfolio-smoke.json").write_text(json.dumps(responses, ensure_ascii=False, indent=2) + "\n")
print(f"{len(responses)} real dispatcher requests passed; synthetic instruments; temporary database removed")
