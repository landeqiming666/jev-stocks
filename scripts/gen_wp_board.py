#!/usr/bin/env python3
"""由 docs/wp/ 下各工作包文件的头部生成看板 docs/wp/README.md 的「波次」「依赖图」「完整看板」三节。
仅用标准库，兼容 Python 3.9。

数据来源是工作包文件头部（id/title/phase/platform/lane/deps/size）；还没有写文件的工作包，
从 docs/wp/backlog.json 读取同样的字段（见该文件）。已写文件的工作包以文件头部为准。

用法：
    python3 scripts/gen_wp_board.py            重写 docs/wp/README.md 中标记之间的内容
    python3 scripts/gen_wp_board.py --check    只检查是否过期（过期则返回 1）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_docs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WP = ROOT / "docs" / "wp"
BEGIN = "<!-- BOARD:BEGIN（由 scripts/gen_wp_board.py 生成，请勿手改）-->"
END = "<!-- BOARD:END -->"
LANE = {"core": "核心", "data": "数据", "semantic": "语义", "ui": "界面", "integration": "联调", "windows": "Windows"}
PLAT = {"shared": "共享", "macos": "macOS", "windows": "Windows"}


def load(root: Path = ROOT) -> List[dict]:
    items: Dict[str, dict] = {}
    backlog = root / "docs" / "wp" / "backlog.json"
    if backlog.is_file():
        for row in json.loads(backlog.read_text(encoding="utf-8")):
            items[row["id"]] = dict(row, written=None)
    for phase in ("mvp0", "v1"):
        folder = root / "docs" / "wp" / phase
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            if path.name == "README.md":
                continue
            meta = check_docs.parse_front_matter(path.read_text(encoding="utf-8"))
            if not meta:
                continue
            items[str(meta["id"])] = {
                "id": str(meta["id"]), "title": str(meta["title"]), "phase": str(meta["phase"]),
                "platform": str(meta["platform"]), "lane": str(meta["lane"]),
                "deps": list(meta["deps"]) if isinstance(meta["deps"], list) else [],
                "size": str(meta["size"]), "written": "%s/%s" % (phase, path.name),
            }
    return sorted(items.values(), key=lambda r: r["id"])


def levels(items: List[dict]) -> Dict[str, int]:
    by = {i["id"]: i for i in items}
    memo: Dict[str, int] = {}

    def lv(i: str, trail: tuple = ()) -> int:
        if i in trail:
            raise ValueError("依赖成环: " + " -> ".join(trail + (i,)))
        if i not in memo:
            deps = [d for d in by[i]["deps"] if d in by]
            memo[i] = 0 if not deps else 1 + max(lv(d, trail + (i,)) for d in deps)
        return memo[i]

    for i in by:
        lv(i)
    return memo


def render(items: List[dict]) -> str:
    lvl = levels(items)
    by = {i["id"]: i for i in items}
    mvp = [i for i in items if i["phase"] == "mvp0"]
    n_mac = sum(1 for i in mvp if i["platform"] != "windows")
    n_win = len(mvp) - n_mac
    n_written = sum(1 for i in mvp if i["written"])

    waves: Dict[int, List[str]] = {}
    for i in mvp:
        waves.setdefault(lvl[i["id"]], []).append(i["id"])
    wave_rows = []
    for k in sorted(waves):
        mac = sorted(x for x in waves[k] if by[x]["platform"] != "windows")
        win = sorted(x for x in waves[k] if by[x]["platform"] == "windows")
        wave_rows.append("| %d | %s | %s |" % (k, "、".join(mac) or "—", "、".join(win) or "—"))

    def nid(x: str) -> str:
        return x.replace("-", "_")

    mm = ["graph LR"]
    for lane in ("core", "data", "semantic", "ui", "integration", "windows"):
        members = [i for i in mvp if i["lane"] == lane]
        if not members:
            continue
        mm.append('  subgraph %s["%s车道"]' % (lane, LANE[lane]))
        mm += ['    %s["%s"]' % (nid(i["id"]), i["id"]) for i in members]
        mm.append("  end")
    for i in mvp:
        for d in i["deps"]:
            mm.append("  %s --> %s" % (nid(d), nid(i["id"])))

    rows = []
    for i in sorted(mvp, key=lambda r: (lvl[r["id"]], r["id"])):
        cell = "[%s](%s)" % (i["id"], i["written"]) if i["written"] else i["id"]
        rows.append("| %s | %s | %s | %s | %s | %d | %s | %s | 待派发 |" % (
            cell, i["title"], LANE[i["lane"]], PLAT[i["platform"]], i["size"], lvl[i["id"]],
            ", ".join(i["deps"]) or "—", "已写" if i["written"] else "待写"))

    return "\n".join([
        BEGIN, "",
        (
            "MVP-0 共 %d 个工作包：Mac 与共享 %d 个，Windows %d 个。%s"
            % (
                len(mvp), n_mac, n_win,
                ("全部 %d 个均已写完整文档，可派发。" % len(mvp))
                if n_written == len(mvp)
                else ("已写完整文档 %d 个，其余 %d 个按同一模板待写。" % (n_written, len(mvp) - n_written)),
            )
        ), "",
        "### 波次", "",
        "同一波次内的工作包彼此没有依赖，可以同时做。波次编号 = 依赖链的最长层数。", "",
        "| 波次 | Mac 与共享 | Windows |", "|---|---|---|", *wave_rows, "",
        "### 依赖图", "", "```mermaid", *mm, "```", "",
        "### 完整看板", "",
        "规模：S < 300 行，M 300–800 行（代码加测试）。“状态”取值：待派发 / doing / review / done。", "",
        "| ID | 标题 | 车道 | 平台 | 规模 | 波次 | 依赖 | 文档 | 状态 |", "|---|---|---|---|---|---|---|---|---|", *rows, "",
        END,
    ])


def splice(readme: str, block: str) -> str:
    if BEGIN in readme and END in readme:
        a, b = readme.index(BEGIN), readme.index(END) + len(END)
        return readme[:a] + block + readme[b:]
    return readme.rstrip("\n") + "\n\n" + block + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    readme_path = WP / "README.md"
    if not readme_path.is_file():
        print("[说明] 没有 docs/wp/README.md，跳过")
        return 0
    items = load()
    new = splice(readme_path.read_text(encoding="utf-8"), render(items))
    if "--check" in argv:
        if new != readme_path.read_text(encoding="utf-8"):
            print("[错误] docs/wp/README.md 的看板已过期，请运行 python3 scripts/gen_wp_board.py")
            return 1
        print("看板是最新的")
        return 0
    readme_path.write_text(new, encoding="utf-8")
    print("已更新看板：%d 个工作包" % len(items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
