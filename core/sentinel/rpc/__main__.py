from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from .dispatcher import Dispatcher
from .server import RpcServer


def main(argv: Sequence[str] | None = None) -> int:
    # writer 独占原 stdout；Python print 和原生库的 fd 1 都转到 stderr。
    sys.stdout.flush()
    output = os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    parser = argparse.ArgumentParser(description="Sentinel NDJSON RPC server")
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args(argv)
    # 不占用解释器标准输入的缓冲锁，父进程消失时仍能正常收尾。
    incoming = os.fdopen(os.dup(sys.stdin.fileno()), "rb", buffering=0)
    try:
        server = RpcServer(incoming, output, Dispatcher(), parent_pid=args.parent_pid)
        server.serve_forever()
    finally:
        incoming.close()
        output.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
