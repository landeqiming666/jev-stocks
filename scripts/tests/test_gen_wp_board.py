"""gen_wp_board.py 的单元测试。运行：python3 -m unittest discover -s scripts/tests -v"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gen_wp_board as gb  # noqa: E402


def item(i, deps=(), platform="shared", lane="core", title="示例", written=None):
    return {"id": i, "title": title, "phase": "mvp0", "platform": platform, "lane": lane,
            "deps": list(deps), "size": "S", "written": written}


class LevelTests(unittest.TestCase):
    def test_levels_follow_longest_dependency_chain(self) -> None:
        lv = gb.levels([item("A"), item("B", ["A"]), item("C", ["A", "B"]), item("D")])
        self.assertEqual(lv, {"A": 0, "B": 1, "C": 2, "D": 0})

    def test_cycle_raises(self) -> None:
        with self.assertRaises(ValueError):
            gb.levels([item("A", ["B"]), item("B", ["A"])])

    def test_unknown_dependency_is_ignored_for_levels(self) -> None:
        self.assertEqual(gb.levels([item("A", ["ghost"])]), {"A": 0})


class RenderTests(unittest.TestCase):
    def test_counts_split_mac_and_windows(self) -> None:
        text = gb.render([item("A"), item("W-1", platform="windows", lane="windows")])
        self.assertIn("共 2 个工作包：Mac 与共享 1 个，Windows 1 个", text)

    def test_written_items_link_to_their_file(self) -> None:
        text = gb.render([item("A", written="mvp0/A-x.md"), item("B")])
        self.assertIn("[A](mvp0/A-x.md)", text)
        self.assertIn("| B |", text)
        self.assertIn("已写完整文档 1 个", text)

    def test_front_matter_status_is_rendered(self) -> None:
        row = dict(item("A"), status="doing")
        self.assertIn("| doing |", gb.render([row]))

    def test_waves_put_windows_in_their_own_column(self) -> None:
        text = gb.render([item("A"), item("W-1", ["A"], platform="windows", lane="windows")])
        self.assertIn("| 0 | A | — |", text)
        self.assertIn("| 1 | — | W-1 |", text)

    def test_mermaid_contains_edges(self) -> None:
        text = gb.render([item("A"), item("B", ["A"])])
        self.assertIn("A --> B", text)

    def test_v1_items_are_not_in_mvp0_board(self) -> None:
        v1 = dict(item("V-1"), phase="v1")
        self.assertIn("共 1 个工作包", gb.render([item("A"), v1]))


class SpliceTests(unittest.TestCase):
    def test_replaces_only_between_markers(self) -> None:
        old = "头\n" + gb.BEGIN + "\n旧内容\n" + gb.END + "\n尾\n"
        new = gb.splice(old, gb.BEGIN + "\n新\n" + gb.END)
        self.assertTrue(new.startswith("头\n"))
        self.assertTrue(new.endswith("\n尾\n"))
        self.assertIn("新", new)
        self.assertNotIn("旧内容", new)

    def test_appends_when_markers_missing(self) -> None:
        out = gb.splice("只有头", gb.BEGIN + "\nX\n" + gb.END)
        self.assertTrue(out.startswith("只有头"))
        self.assertIn(gb.BEGIN, out)

    def test_is_idempotent(self) -> None:
        block = gb.BEGIN + "\nX\n" + gb.END
        once = gb.splice("头\n", block)
        self.assertEqual(gb.splice(once, block), once)


class LoadTests(unittest.TestCase):
    def test_file_header_wins_over_backlog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "wp" / "mvp0").mkdir(parents=True)
            (root / "docs" / "wp" / "backlog.json").write_text(json.dumps([
                {"id": "C-01", "title": "旧标题", "phase": "mvp0", "platform": "shared", "lane": "core", "size": "S", "deps": []},
                {"id": "C-02", "title": "只在 backlog", "phase": "mvp0", "platform": "shared", "lane": "core", "size": "M", "deps": ["C-01"]},
            ], ensure_ascii=False), encoding="utf-8")
            (root / "docs" / "wp" / "mvp0" / "C-01-a.md").write_text(
                "---\nid: C-01\ntitle: 新标题\nphase: mvp0\nplatform: shared\nlane: core\ndeps: []\nsize: M\nstatus: doing\nowns: [x/]\n---\n", encoding="utf-8")
            items = {i["id"]: i for i in gb.load(root)}
            self.assertEqual(items["C-01"]["title"], "新标题")
            self.assertEqual(items["C-01"]["written"], "mvp0/C-01-a.md")
            self.assertEqual(items["C-01"]["status"], "doing")
            self.assertIsNone(items["C-02"]["written"])


if __name__ == "__main__":
    unittest.main()
