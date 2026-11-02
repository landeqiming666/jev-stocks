"""check_proto.py 的单元测试（只测检查逻辑本身，不依赖 node）。
运行：python3 -m unittest discover -s scripts/tests -v"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_proto as cp  # noqa: E402


class CssRuleTests(unittest.TestCase):
    def test_hex_color_outside_tokens_is_reported(self) -> None:
        found = cp.check_css_text("a { color: #ff0000; }", "css/components.css")
        self.assertTrue(any("十六进制颜色" in f for f in found))

    def test_hex_color_inside_tokens_is_allowed(self) -> None:
        self.assertEqual(cp.check_css_text(":root { --a: #ff0000; }", "css/tokens.css"), [])

    def test_hex_like_selectors_are_not_colors(self) -> None:
        self.assertEqual(cp.check_css_text("a[href^='#abc'] { color: var(--ink); }", "css/base.css"), [])

    def test_outline_none_is_reported(self) -> None:
        found = cp.check_css_text("button { outline: none; }", "css/base.css")
        self.assertTrue(any("outline" in f for f in found))
        found = cp.check_css_text("button { outline:none }", "css/base.css")
        self.assertTrue(any("outline" in f for f in found))

    def test_outline_with_width_is_allowed(self) -> None:
        self.assertEqual(cp.check_css_text(":focus-visible { outline: 2px solid var(--focus-ring); }", "css/base.css"), [])

    def test_shimmer_or_infinite_animation_is_reported(self) -> None:
        found = cp.check_css_text(".x { animation: spin 1s infinite; }", "css/components.css")
        self.assertTrue(any("循环动画" in f for f in found))

    def test_class_prefix_rule(self) -> None:
        found = cp.check_css_text(".foo { color: var(--ink); }", "css/components.css")
        self.assertTrue(any(".foo" in f for f in found))
        self.assertEqual(cp.check_css_text(".c-a, .l-b, .p-c, .u-d, .is-e, .has-f { color: var(--ink); }", "css/components.css"), [])

    def test_proto_prefix_only_in_proto_css(self) -> None:
        self.assertEqual(cp.check_css_text(".proto-bar { color: var(--ink); }", "css/proto.css"), [])
        found = cp.check_css_text(".proto-bar { color: var(--ink); }", "css/components.css")
        self.assertTrue(any("proto-" in f for f in found))

    def test_undefined_variable_is_reported(self) -> None:
        found = cp.check_css_text("a { color: var(--nope); }", "css/components.css", defined={"--ink"})
        self.assertTrue(any("--nope" in f for f in found))

    def test_variable_with_fallback_is_allowed(self) -> None:
        self.assertEqual(cp.check_css_text("a { color: var(--nope, red); }", "css/components.css", defined={"--ink"}), [])

    def test_variables_defined_in_the_same_sheet_count(self) -> None:
        css = ".c-a { --k: 10%; width: var(--k); }"
        self.assertEqual(cp.check_css_text(css, "css/components.css", defined=set()), [])


class HtmlRuleTests(unittest.TestCase):
    def check(self, html: str) -> list:
        return cp.check_html(html, "t")

    def test_balanced_html_passes(self) -> None:
        self.assertEqual(self.check('<div class="c-a"><p>x</p><br><input aria-label="n"></div>'), [])

    def test_unclosed_tag_is_reported(self) -> None:
        self.assertTrue(any("未闭合" in f or "不匹配" in f for f in self.check("<div><p>x</div>")))

    def test_duplicate_id_is_reported(self) -> None:
        found = self.check('<div id="a"></div><div id="a"></div>')
        self.assertTrue(any("重复的 id" in f for f in found))

    def test_button_without_name_is_reported(self) -> None:
        self.assertTrue(any("按钮" in f for f in self.check('<button class="c-button"></button>')))
        self.assertTrue(any("按钮" in f for f in self.check('<button class="c-button"><svg aria-hidden="true"></svg></button>')))

    def test_button_with_text_or_label_passes(self) -> None:
        self.assertEqual(self.check('<button>确定</button>'), [])
        self.assertEqual(self.check('<button aria-label="关闭"><svg aria-hidden="true"></svg></button>'), [])

    def test_link_without_name_is_reported(self) -> None:
        self.assertTrue(any("链接" in f for f in self.check('<a href="#/x"><svg aria-hidden="true"></svg></a>')))
        self.assertEqual(self.check('<a href="#/x" aria-label="今日"><svg aria-hidden="true"></svg></a>'), [])

    def test_input_without_label_is_reported(self) -> None:
        self.assertTrue(any("表单控件" in f for f in self.check('<input type="text">')))
        self.assertEqual(self.check('<label for="a">名</label><input id="a">'), [])
        self.assertEqual(self.check('<input aria-label="搜索">'), [])
        self.assertEqual(self.check('<input type="radio" name="x">'), [])

    def test_inline_style_must_only_set_custom_properties(self) -> None:
        self.assertTrue(any("内联样式" in f for f in self.check('<div style="color: red"></div>')))
        self.assertEqual(self.check('<div style="--w: 40%"></div>'), [])

    def test_aria_controls_target_must_exist(self) -> None:
        self.assertTrue(any("aria-controls" in f for f in self.check('<button aria-controls="nope">x</button>')))
        self.assertEqual(self.check('<button aria-controls="a">x</button><div id="a"></div>'), [])

    def test_aria_labelledby_target_must_exist(self) -> None:
        self.assertTrue(any("aria-labelledby" in f for f in self.check('<section aria-labelledby="nope"></section>')))

    def test_forbidden_words_are_reported(self) -> None:
        for word in ("建议买入", "建议卖出", "必涨", "抄底", "牛股", "置信度", "AI 精准预测"):
            self.assertTrue(any(word in f for f in self.check("<p>%s</p>" % word)), word)

    def test_svg_icon_must_be_hidden_from_screen_readers(self) -> None:
        self.assertTrue(any("svg" in f for f in self.check('<button>x<svg class="c-icon"></svg></button>')))
        self.assertEqual(self.check('<button>x<svg class="c-icon" aria-hidden="true"></svg></button>'), [])

    def test_img_role_svg_needs_label(self) -> None:
        self.assertTrue(any("role=\"img\"" in f for f in self.check('<svg role="img"></svg>')))
        self.assertEqual(self.check('<svg role="img" aria-label="图"></svg>'), [])

    def test_unknown_class_prefix_is_reported(self) -> None:
        self.assertTrue(any("类名" in f for f in self.check('<div class="foo"></div>')))
        self.assertEqual(self.check('<div class="c-a is-b u-mono"></div>'), [])

    def test_unused_css_class_is_reported(self) -> None:
        found = cp.check_classes_defined({"c-a", "c-missing"}, {"c-a"})
        self.assertEqual(found, ["HTML 使用了 CSS 里没有定义的类: c-missing"])

    def test_registered_hook_classes_are_allowed_without_css(self) -> None:
        self.assertEqual(cp.check_classes_defined({"p-today", "c-drawer"}, set()), [])

    def test_state_classes_are_allowed_without_css_rule(self) -> None:
        self.assertEqual(cp.check_classes_defined({"is-whatever"}, set()), [])


class ExampleRefTests(unittest.TestCase):
    def test_missing_example_is_reported(self) -> None:
        refs = cp.find_example_refs("res('inbox.list', 'pending'); err('thesis.create', 'empty'); ex('a.b','c')")
        self.assertEqual(sorted(refs), [("a.b", "c"), ("inbox.list", "pending"), ("thesis.create", "empty")])
        missing = cp.missing_examples(refs, {"inbox.list/pending"})
        self.assertEqual(sorted(missing), ["a.b/c", "thesis.create/empty"])


class ContrastIntegrationTests(unittest.TestCase):
    def test_real_tokens_file_passes_contrast(self) -> None:
        tokens = Path(__file__).resolve().parents[2] / "design" / "prototype" / "css" / "tokens.css"
        if not tokens.is_file():
            self.skipTest("没有 tokens.css")
        import check_contrast
        results = check_contrast.check(tokens)
        bad = [r for r in results if not r.ok]
        self.assertEqual(bad, [], "对比度不达标: %r" % [(b.fg, b.bg, b.ratio) for b in bad])


if __name__ == "__main__":
    unittest.main()
