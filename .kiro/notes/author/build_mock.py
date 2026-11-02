"""生成 design/prototype/data/mock.js（纯 JSON，便于 Python 读回）。

用法：python3 build_mock.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import examples as ex  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
out = ROOT / "design" / "prototype" / "data" / "mock.js"
out.parent.mkdir(parents=True, exist_ok=True)

payload = {"examples": ex.EX, "notifications": ex.NOTIFICATIONS}
body = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False)
out.write_text(
    "/* 由 contracts/ 的 examples 生成（scripts/gen_proto_mock.py）。请勿手改。纯 JSON，供脚本读回。 */\n"
    "window.MOCK = " + body + ";\n",
    encoding="utf-8",
)
n_methods = len(ex.EX)
n_examples = sum(len(v) for v in ex.EX.values())
print("mock.js: %d 个方法, %d 个示例, %d KB" % (n_methods, n_examples, out.stat().st_size // 1024))
