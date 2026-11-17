"""`python -m sentinel`：独占 stdout 作为 NDJSON 通道，其余输出转到 stderr。"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence

from .app.main import run


def main(argv: Sequence[str] | None = None) -> int:
    sys.stdout.flush()
    output = os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    incoming = os.fdopen(os.dup(sys.stdin.fileno()), "rb", buffering=0)
    try:
        return run(argv, stdin=incoming, stdout=output)
    finally:
        incoming.close()
        output.close()


if __name__ == "__main__":
    raise SystemExit(main())
