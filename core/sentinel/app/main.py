"""进程入口装配：解析参数、构造组合根、注册处理器、启动 RPC server。"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Sequence
from typing import BinaryIO

from sentinel import __version__, logging_setup
from sentinel.errors import InternalError
from sentinel.logging_setup import get_logger, log_event
from sentinel.rpc import Dispatcher, RpcServer

from .args import AppArgs, UsageError, parse_args
from .container import AppContainer, build_container
from .lifecycle import shutdown, startup
from .registry import EXPECTED_BUSINESS_METHOD_COUNT, register_all

EXPECTED_TOTAL_METHOD_COUNT = 40
SHUTDOWN_GRACE_SECONDS = 3
_LOG = get_logger(__name__)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_MIGRATION = 3
EXIT_FAILURE = 1


def _ready(server: RpcServer, container: AppContainer) -> None:
    server.notify(
        "app.ready",
        {"version": __version__, "migrationsApplied": container.migrations_applied},
    )
    change = container.engine.take_change()
    if change is not None:
        server.notify(
            "engine.changed",
            {"from": change.from_engine, "to": change.to_engine, "reason": change.reason},
        )


def serve(
    container: AppContainer,
    *,
    parent_pid: int | None,
    stdin: BinaryIO,
    stdout: BinaryIO,
) -> int:
    dispatcher = Dispatcher()
    register_all(dispatcher, container)
    server = RpcServer(stdin, stdout, dispatcher, parent_pid=parent_pid)
    if len(dispatcher.methods()) != EXPECTED_TOTAL_METHOD_COUNT:
        raise InternalError(
            detail=f"method count {len(dispatcher.methods())} != {EXPECTED_TOTAL_METHOD_COUNT}"
        )
    server.set_start_hook(lambda: _ready(server, container))
    container.attach_notifier(server.notify)
    startup(container)
    try:
        server.start()
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown(container, server)
    return EXIT_OK


def run(
    argv: Sequence[str] | None = None,
    *,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
    container_factory: Callable[[AppArgs], AppContainer] = build_container,
) -> int:
    try:
        args = parse_args(argv)
    except UsageError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    except SystemExit as exc:  # --help 已打印帮助
        return int(exc.code or EXIT_OK)
    try:
        logging_setup.configure(args.data_dir / "logs", args.log_level)
    except Exception:
        print("无法写入日志目录。", file=sys.stderr)
        return EXIT_FAILURE
    try:
        container = container_factory(args)
    except Exception as exc:
        if getattr(exc, "code", "") == "MIGRATION_FAILED":
            print("数据库升级失败，已尝试恢复备份。", file=sys.stderr)
            return EXIT_MIGRATION
        log_event(_LOG, logging.ERROR, event="app.start_failed", error_code="INTERNAL")
        print("应用启动失败，请查看日志。", file=sys.stderr)
        return EXIT_FAILURE
    incoming = stdin if stdin is not None else sys.stdin.buffer
    outgoing = stdout if stdout is not None else sys.stdout.buffer
    try:
        return serve(container, parent_pid=args.parent_pid, stdin=incoming, stdout=outgoing)
    except InternalError:
        print("应用组件不完整，请重新安装。", file=sys.stderr)
        container.close()
        return EXIT_FAILURE


__all__ = [
    "EXIT_FAILURE",
    "EXIT_MIGRATION",
    "EXIT_OK",
    "EXIT_USAGE",
    "EXPECTED_BUSINESS_METHOD_COUNT",
    "EXPECTED_TOTAL_METHOD_COUNT",
    "run",
    "serve",
]
