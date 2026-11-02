"""check_contrast.py 的单元测试。运行：python3 -m unittest discover -s scripts/tests -v"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_contrast as cc  # noqa: E402


class LuminanceTests(unittest.TestCase):
    def test_black_on_white_is_21(self) -> None:
        self.assertAlmostEqual(cc.contrast("#000000", "#FFFFFF"), 21.0, places=2)

    def test_same_color_is_1(self) -> None:
        self.assertAlmostEqual(cc.contrast("#336699", "#336699"), 1.0, places=3)

    def test_symmetric(self) -> None:
        self.assertAlmostEqual(cc.contrast("#123456", "#FEDCBA"), cc.contrast("#FEDCBA", "#123456"), places=6)

    def test_known_value_777777_on_white(self) -> None:
        # WCAG 常见参考值：#777777 在白底上约 4.48:1
        self.assertAlmostEqual(cc.contrast("#777777", "#FFFFFF"), 4.48, places=2)

    def test_short_hex_is_expanded(self) -> None:
        self.assertAlmostEqual(cc.contrast("#000", "#FFF"), 21.0, places=2)


class ParseTests(unittest.TestCase):
    def test_parses_custom_properties(self) -> None:
        css = ":root{ --paper:#FAF8F3; --ink: #1A1C20 ; --x: 12px; }"
        tokens = cc.parse_tokens(css)
        self.assertEqual(tokens["--paper"], "#FAF8F3")
        self.assertEqual(tokens["--ink"], "#1A1C20")
        self.assertNotIn("--x", tokens)

    def test_later_definition_wins_inside_same_block_only_for_root(self) -> None:
        css = ":root{--a:#111111;} [data-x]{--a:#222222;}"
        self.assertEqual(cc.parse_tokens(css)["--a"], "#111111")


class CheckTests(unittest.TestCase):
    def write_tokens(self, text: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "tokens.css"
        path.write_text(text, encoding="utf-8")
        return path

    def test_failing_pair_is_reported_with_ratio(self) -> None:
        path = self.write_tokens(":root{--paper:#FFFFFF; --muted:#999999;}")
        results = cc.check(path, pairs=[("--muted", "--paper", 4.5, "辅助文字")])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertLess(results[0].ratio, 4.5)

    def test_passing_pair(self) -> None:
        path = self.write_tokens(":root{--paper:#FFFFFF; --ink:#111111;}")
        results = cc.check(path, pairs=[("--ink", "--paper", 4.5, "正文")])
        self.assertTrue(results[0].ok)

    def test_missing_token_is_reported_not_raised(self) -> None:
        path = self.write_tokens(":root{--paper:#FFFFFF;}")
        results = cc.check(path, pairs=[("--nope", "--paper", 4.5, "x")])
        self.assertFalse(results[0].ok)
        self.assertIn("--nope", results[0].detail)

    def test_main_returns_1_when_any_fails(self) -> None:
        path = self.write_tokens(":root{--paper:#FFFFFF; --muted:#999999;}")
        self.assertEqual(cc.main(["--tokens", str(path), "--only-demo-pair"]), 1)

    def test_main_skips_when_tokens_file_missing(self) -> None:
        self.assertEqual(cc.main(["--tokens", "/no/such/tokens.css"]), 0)


if __name__ == "__main__":
    unittest.main()
