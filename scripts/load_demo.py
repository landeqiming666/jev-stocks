#!/usr/bin/env python3
"""Load or clear the offline demo data set without starting the RPC server."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from sentinel import clock, platform
from sentinel.demo import DemoService, clear_demo
from sentinel.demo.loader import read_resources, registry_count
from sentinel.errors import SentinelError
from sentinel.storage import Database
from sentinel.storage.db import DB_FILENAME

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "resources" / "demo"


def _data_dir() -> Path:
    configured = os.environ.get("SENTINEL_DATA_DIR")
    return Path(configured).expanduser() if configured else platform.default_data_dir()


def _summary(counts: Any) -> dict[str, Any]:
    return {"loaded": True, "counts": counts.model_dump()}


def _print(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    if payload.get("cleared"):
        print(f"演示数据已清除，删除 {payload['removed']} 行。")
        return
    if payload.get("dryRun"):
        if payload.get("wouldLoad"):
            counts = payload.get("counts", {})
            print(
                "演练：将载入 "
                f"标的 {counts.get('instruments')}、持仓 {counts.get('holdings')}、"
                f"逻辑 {counts.get('theses')}、披露 {counts.get('events')}、"
                f"判定 {counts.get('decisions')}、行情 {counts.get('prices')}，不写数据库。"
            )
        else:
            print(f"演练：将清除 {payload.get('rows', 0)} 行，不写数据库。")
        return
    counts = payload.get("counts", {})
    print(
        "演示数据已载入："
        f"标的 {counts.get('instruments')}、持仓 {counts.get('holdings')}、"
        f"逻辑 {counts.get('theses')}、披露 {counts.get('events')}、"
        f"判定 {counts.get('decisions')}、行情 {counts.get('prices')}。"
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    now: Callable[[], Any] = clock.now,
) -> int:
    parser = argparse.ArgumentParser(description="载入或清除 JEV 演示数据")
    parser.add_argument("--clear", action="store_true", help="清除已登记的演示数据")
    parser.add_argument("--dry-run", action="store_true", help="只检查，不写数据库")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--data-dir", type=Path, help="覆盖 SENTINEL_DATA_DIR")
    args = parser.parse_args(argv)

    data_dir = (args.data_dir or _data_dir()).expanduser()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"无法创建数据目录：{exc}", file=sys.stderr)
        return 1

    database = Database(data_dir / DB_FILENAME)
    try:
        with platform.file_lock(data_dir / "core.lock"):
            try:
                database.open()
                database.migrate()
                if args.clear:
                    if args.dry_run:
                        with database.read() as tx:
                            removed = registry_count(tx)
                        _print(
                            {"dryRun": True, "wouldLoad": False, "rows": removed},
                            args.json,
                        )
                        return 0
                    with database.read() as tx:
                        removed = registry_count(tx)
                    clear_demo(database, now)
                    _print(
                        {"cleared": True, "removed": removed, "ok": True},
                        args.json,
                    )
                    return 0
                if args.dry_run:
                    data = read_resources(RESOURCES)
                    _print(
                        {
                            "dryRun": True,
                            "wouldLoad": True,
                            "counts": data.manifest["counts"],
                        },
                        args.json,
                    )
                    return 0
                service = DemoService(database, RESOURCES, now)
                counts = service.load()
                _print(_summary(counts), args.json)
                return 0
            finally:
                database.close()
    except platform.AlreadyRunning:
        print("另一个核心进程正在使用这份数据，请先关闭应用。", file=sys.stderr)
        return 2
    except SentinelError as exc:
        print(f"{exc.code.value}: {exc.reason or exc.detail or 'failed'}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
