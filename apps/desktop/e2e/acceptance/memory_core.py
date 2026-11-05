#!/usr/bin/env python3
"""验收专用核心入口：复用生产组合根，只把密钥存储固定为进程内存。

Playwright 的 M-3 场景会真实调用 ``secrets.set`` / ``secrets.clear``。生产入口
默认写入 macOS Keychain；验收绝不能读写用户钥匙串，因此这里显式注入
``MemorySecretStore``。除密钥存储外，参数、组合根、RPC、日志与数据库均与
``python -m sentinel`` 相同。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "core"))

from sentinel.app.args import AppArgs  # noqa: E402
from sentinel.app.container import build_container  # noqa: E402
from sentinel.app.main import run  # noqa: E402
from sentinel.secrets import MemorySecretStore  # noqa: E402


def factory(args: AppArgs):
    return build_container(args, secret_store=MemorySecretStore())


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:], container_factory=factory))
