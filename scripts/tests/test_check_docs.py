"""check_docs.py 的单元测试。

运行：python3 -m unittest discover -s scripts/tests -v
只用标准库，兼容 Python 3.9。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_docs  # noqa: E402

GOOD_DOC = "# 标题\n\n> 版本：v2.0 · 2026-11-02 · 状态：已定稿\n\n正文\n"
LEGACY_DOC = "# 标题\n\n> 版本：v1.0 · 2026-11-02 · 状态：待重写\n\n旧稿\n"


def wp_text(
    wp_id: str,
    deps: str = "[]",
    phase: str = "mvp0",
    platform: str = "shared",
    lane: str = "core",
    size: str = "S",
    owns: Optional[str] = None,
    appends: Optional[str] = None,
    stubs: Optional[str] = None,
    title: str = "示例",
) -> str:
    if owns is None:
        owns = "[core/%s/]" % wp_id.lower()
    lines = [
        "---",
        "id: %s" % wp_id,
        "title: %s" % title,
        "phase: %s" % phase,
        "platform: %s" % platform,
        "lane: %s" % lane,
        "deps: %s" % deps,
        "size: %s" % size,
        "owns: %s" % owns,
    ]
    if appends is not None:
        lines.append("appends: %s" % appends)
    if stubs is not None:
        lines.append("stubs: %s" % stubs)
    lines += ["---", "", "# %s" % wp_id, ""]
    return "\n".join(lines)


class TreeCase(unittest.TestCase):
    """每个用例使用独立的临时目录。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_checks(self, strict: bool = False) -> check_docs.Report:
        return check_docs.run_checks(self.root, strict=strict)

    def assertHasError(self, report: check_docs.Report, *needles: str) -> None:
        for err in report.errors:
            if all(n in err for n in needles):
                return
        self.fail("未找到包含 %r 的错误，实际错误：%r" % (needles, report.errors))


class LinkTests(TreeCase):
    def test_clean_tree_passes(self) -> None:
        self.write("docs/README.md", GOOD_DOC + "\n[甲](01-a.md)\n")
        self.write("docs/01-a.md", GOOD_DOC)
        self.assertEqual(self.run_checks().errors, [])

    def test_broken_relative_link_is_reported_with_file_and_target(self) -> None:
        self.write("docs/README.md", GOOD_DOC + "\n[坏](99-missing.md)\n")
        report = self.run_checks()
        self.assertHasError(report, "docs/README.md", "99-missing.md")

    def test_link_inside_code_fence_is_ignored(self) -> None:
        self.write("docs/README.md", GOOD_DOC + "\n```\n[坏](99-missing.md)\n```\n")
        self.assertEqual(self.run_checks().errors, [])

    def test_link_inside_inline_code_is_ignored(self) -> None:
        self.write("docs/README.md", GOOD_DOC + "\n示例 `[坏](99-missing.md)`\n")
        self.assertEqual(self.run_checks().errors, [])

    def test_external_links_are_ignored(self) -> None:
        self.write("docs/README.md", GOOD_DOC + "\n[外](https://example.com/a.md) [信](mailto:a@b.c)\n")
        self.assertEqual(self.run_checks().errors, [])

    def test_missing_anchor_is_reported(self) -> None:
        self.write("docs/README.md", GOOD_DOC + "\n[甲](01-a.md#不存在)\n")
        self.write("docs/01-a.md", GOOD_DOC + "\n## 4. 页面规格\n")
        self.assertHasError(self.run_checks(), "不存在", "01-a.md#不存在")

    def test_existing_chinese_anchor_passes(self) -> None:
        self.write("docs/README.md", GOOD_DOC + "\n[甲](01-a.md#4-页面规格)\n")
        self.write("docs/01-a.md", GOOD_DOC + "\n## 4. 页面规格\n")
        self.assertEqual(self.run_checks().errors, [])

    def test_same_file_anchor_is_checked(self) -> None:
        self.write("docs/README.md", GOOD_DOC + "\n## 小节\n\n[好](#小节) [坏](#没有)\n")
        report = self.run_checks()
        self.assertEqual(len(report.errors), 1)
        self.assertHasError(report, "#没有")

    def test_duplicate_heading_gets_numeric_suffix(self) -> None:
        self.write("docs/README.md", GOOD_DOC + "\n## 例子\n\n## 例子\n\n[二](#例子-1)\n")
        self.assertEqual(self.run_checks().errors, [])

    def test_heading_inside_code_fence_does_not_count(self) -> None:
        self.write("docs/README.md", GOOD_DOC + "\n```\n## 假标题\n```\n\n[坏](#假标题)\n")
        self.assertHasError(self.run_checks(), "#假标题")


class DocNameTests(TreeCase):
    def test_stale_numbered_doc_name_is_reported(self) -> None:
        self.write("docs/README.md", GOOD_DOC + "\n详见 `05-接口与状态模型.md`。\n")
        self.write("docs/05-接口契约.md", GOOD_DOC)
        self.assertHasError(self.run_checks(), "05-接口与状态模型.md")

    def test_existing_numbered_doc_name_passes(self) -> None:
        self.write("docs/README.md", GOOD_DOC + "\n详见 `05-接口契约.md`。\n")
        self.write("docs/05-接口契约.md", GOOD_DOC)
        self.assertEqual(self.run_checks().errors, [])

    def test_docs_prefixed_name_is_checked(self) -> None:
        self.write("docs/README.md", GOOD_DOC + "\n见 docs/77-不存在.md\n")
        self.assertHasError(self.run_checks(), "77-不存在.md")

    def test_wp_filename_is_not_mistaken_for_doc_name(self) -> None:
        self.write("docs/README.md", GOOD_DOC + "\n见 `docs/wp/mvp0/C-03-storage.md`。\n")
        self.assertEqual(self.run_checks().errors, [])


class StatusTests(TreeCase):
    def test_missing_status_is_error(self) -> None:
        self.write("docs/README.md", "# 标题\n\n没有状态\n")
        self.assertHasError(self.run_checks(), "docs/README.md", "状态")

    def test_legacy_status_warns_in_normal_mode(self) -> None:
        self.write("docs/README.md", GOOD_DOC)
        self.write("docs/02-a.md", LEGACY_DOC)
        report = self.run_checks()
        self.assertEqual(report.errors, [])
        self.assertTrue(any("02-a.md" in w for w in report.warnings))

    def test_legacy_status_fails_in_strict_mode(self) -> None:
        self.write("docs/README.md", GOOD_DOC)
        self.write("docs/02-a.md", LEGACY_DOC)
        self.assertHasError(self.run_checks(strict=True), "02-a.md", "待重写")

    def test_status_is_not_required_in_wp_folder(self) -> None:
        self.write("docs/README.md", GOOD_DOC)
        self.write("docs/wp/README.md", "# 看板\n")
        self.assertEqual(self.run_checks().errors, [])


class FrontMatterTests(unittest.TestCase):
    def test_parses_scalars_and_flow_lists(self) -> None:
        text = "---\nid: C-03\ndeps: [WP-00, C-01]\nowns: []\n---\n正文"
        data = check_docs.parse_front_matter(text)
        self.assertEqual(data["id"], "C-03")
        self.assertEqual(data["deps"], ["WP-00", "C-01"])
        self.assertEqual(data["owns"], [])

    def test_returns_none_without_front_matter(self) -> None:
        self.assertIsNone(check_docs.parse_front_matter("# 只有标题\n"))

    def test_rejects_malformed_line(self) -> None:
        with self.assertRaises(ValueError):
            check_docs.parse_front_matter("---\n这行没有冒号\n---\n")


class WorkPackageTests(TreeCase):
    def setUp(self) -> None:
        super().setUp()
        self.write("docs/README.md", GOOD_DOC)

    def test_valid_graph_passes(self) -> None:
        self.write("docs/wp/mvp0/WP-00-skeleton.md", wp_text("WP-00"))
        self.write("docs/wp/mvp0/C-01-rpc.md", wp_text("C-01", deps="[WP-00]"))
        self.write("docs/wp/mvp0/C-02-bridge.md", wp_text("C-02", deps="[WP-00, C-01]"))
        self.assertEqual(self.run_checks().errors, [])

    def test_missing_dependency_is_reported(self) -> None:
        self.write("docs/wp/mvp0/C-01-rpc.md", wp_text("C-01", deps="[WP-99]"))
        self.assertHasError(self.run_checks(), "C-01", "WP-99")

    def test_dependency_cycle_is_reported(self) -> None:
        self.write("docs/wp/mvp0/C-01-a.md", wp_text("C-01", deps="[C-02]"))
        self.write("docs/wp/mvp0/C-02-b.md", wp_text("C-02", deps="[C-03]"))
        self.write("docs/wp/mvp0/C-03-c.md", wp_text("C-03", deps="[C-01]"))
        self.assertHasError(self.run_checks(), "依赖成环")

    def test_self_dependency_is_a_cycle(self) -> None:
        self.write("docs/wp/mvp0/C-01-a.md", wp_text("C-01", deps="[C-01]"))
        self.assertHasError(self.run_checks(), "依赖成环")

    def test_duplicate_id_is_reported(self) -> None:
        self.write("docs/wp/mvp0/C-01-a.md", wp_text("C-01"))
        self.write("docs/wp/mvp0/C-01-b.md", wp_text("C-01", owns="[core/other/]"))
        self.assertHasError(self.run_checks(), "C-01", "重复")

    def test_missing_required_key_is_reported(self) -> None:
        self.write("docs/wp/mvp0/C-01-a.md", "---\nid: C-01\ntitle: 示例\n---\n")
        self.assertHasError(self.run_checks(), "C-01-a.md", "phase")

    def test_filename_must_start_with_id(self) -> None:
        self.write("docs/wp/mvp0/other-name.md", wp_text("C-01"))
        self.assertHasError(self.run_checks(), "other-name.md", "文件名")

    def test_folder_must_match_phase(self) -> None:
        self.write("docs/wp/v1/C-01-a.md", wp_text("C-01", phase="mvp0"))
        self.assertHasError(self.run_checks(), "C-01-a.md", "phase")

    def test_mvp0_cannot_depend_on_v1(self) -> None:
        self.write("docs/wp/v1/V-01-a.md", wp_text("V-01", phase="v1"))
        self.write("docs/wp/mvp0/C-01-a.md", wp_text("C-01", deps="[V-01]"))
        self.assertHasError(self.run_checks(), "C-01", "V-01", "v1")

    def test_invalid_size_is_reported(self) -> None:
        self.write("docs/wp/mvp0/C-01-a.md", wp_text("C-01", size="L"))
        self.assertHasError(self.run_checks(), "C-01", "size")

    def test_no_wp_folder_is_skipped_without_error(self) -> None:
        report = self.run_checks()
        self.assertEqual(report.errors, [])
        self.assertTrue(any("工作包" in n for n in report.notes))


class PlatformLaneTests(TreeCase):
    def setUp(self) -> None:
        super().setUp()
        self.write("docs/README.md", GOOD_DOC)

    def test_invalid_platform_is_reported(self) -> None:
        self.write("docs/wp/mvp0/C-01-a.md", wp_text("C-01", platform="linux"))
        self.assertHasError(self.run_checks(), "C-01", "platform")

    def test_invalid_lane_is_reported(self) -> None:
        self.write("docs/wp/mvp0/C-01-a.md", wp_text("C-01", lane="misc"))
        self.assertHasError(self.run_checks(), "C-01", "lane")

    def test_windows_platform_requires_windows_lane(self) -> None:
        self.write("docs/wp/mvp0/W-01-a.md", wp_text("W-01", platform="windows", lane="core"))
        self.assertHasError(self.run_checks(), "W-01", "windows")

    def test_windows_lane_requires_windows_platform(self) -> None:
        self.write("docs/wp/mvp0/W-01-a.md", wp_text("W-01", platform="shared", lane="windows"))
        self.assertHasError(self.run_checks(), "W-01", "windows")

    def test_shared_cannot_depend_on_windows(self) -> None:
        self.write("docs/wp/mvp0/W-01-a.md", wp_text("W-01", platform="windows", lane="windows"))
        self.write("docs/wp/mvp0/C-01-a.md", wp_text("C-01", deps="[W-01]"))
        self.assertHasError(self.run_checks(), "C-01", "W-01", "Windows")

    def test_macos_cannot_depend_on_windows(self) -> None:
        self.write("docs/wp/mvp0/W-01-a.md", wp_text("W-01", platform="windows", lane="windows"))
        self.write("docs/wp/mvp0/M-01-a.md", wp_text("M-01", platform="macos", deps="[W-01]"))
        self.assertHasError(self.run_checks(), "M-01", "W-01", "Windows")

    def test_windows_may_depend_on_shared_and_macos_free_chain(self) -> None:
        self.write("docs/wp/mvp0/C-01-a.md", wp_text("C-01"))
        self.write("docs/wp/mvp0/W-01-a.md", wp_text("W-01", platform="windows", lane="windows", deps="[C-01]"))
        self.write("docs/wp/mvp0/W-02-b.md", wp_text("W-02", platform="windows", lane="windows", deps="[W-01]"))
        self.assertEqual(self.run_checks().errors, [])


class OwnershipTests(TreeCase):
    def setUp(self) -> None:
        super().setUp()
        self.write("docs/README.md", GOOD_DOC)

    def test_identical_owned_path_is_reported(self) -> None:
        self.write("docs/wp/mvp0/C-01-a.md", wp_text("C-01", owns="[core/x/]"))
        self.write("docs/wp/mvp0/C-02-b.md", wp_text("C-02", owns="[core/x/]"))
        self.assertHasError(self.run_checks(), "owns", "C-01", "C-02")

    def test_file_inside_other_owned_directory_is_reported(self) -> None:
        self.write("docs/wp/mvp0/C-01-a.md", wp_text("C-01", owns="[core/x/]"))
        self.write("docs/wp/mvp0/C-02-b.md", wp_text("C-02", owns="[core/x/db.py]"))
        self.assertHasError(self.run_checks(), "owns", "core/x/db.py")

    def test_sibling_paths_do_not_overlap(self) -> None:
        self.write("docs/wp/mvp0/C-01-a.md", wp_text("C-01", owns="[core/x/, core/xy.py]"))
        self.write("docs/wp/mvp0/C-02-b.md", wp_text("C-02", owns="[core/y/]"))
        self.assertEqual(self.run_checks().errors, [])

    def test_appends_without_owner_is_reported(self) -> None:
        self.write("docs/wp/mvp0/C-01-a.md", wp_text("C-01", appends="[core/registry.py]"))
        self.assertHasError(self.run_checks(), "C-01", "core/registry.py", "拥有者")

    def test_appends_requires_dependency_on_owner(self) -> None:
        self.write("docs/wp/mvp0/WP-00-a.md", wp_text("WP-00", owns="[core/registry.py]"))
        self.write("docs/wp/mvp0/C-01-b.md", wp_text("C-01", appends="[core/registry.py]"))
        self.assertHasError(self.run_checks(), "C-01", "WP-00", "依赖")

    def test_appends_with_transitive_dependency_passes(self) -> None:
        self.write("docs/wp/mvp0/WP-00-a.md", wp_text("WP-00", owns="[core/registry.py]"))
        self.write("docs/wp/mvp0/C-01-b.md", wp_text("C-01", deps="[WP-00]"))
        self.write(
            "docs/wp/mvp0/C-02-c.md",
            wp_text("C-02", deps="[C-01]", appends="[core/registry.py]"),
        )
        self.assertEqual(self.run_checks().errors, [])

    def test_stub_without_taker_is_reported(self) -> None:
        self.write("docs/wp/mvp0/WP-00-a.md", wp_text("WP-00", stubs="[core/x.py]"))
        self.assertHasError(self.run_checks(), "WP-00", "core/x.py", "接手")

    def test_stub_taker_must_depend_on_stubber(self) -> None:
        self.write("docs/wp/mvp0/WP-00-a.md", wp_text("WP-00", stubs="[core/x.py]"))
        self.write("docs/wp/mvp0/C-01-b.md", wp_text("C-01", owns="[core/x.py]"))
        self.assertHasError(self.run_checks(), "C-01", "WP-00", "依赖")

    def test_stub_handover_passes(self) -> None:
        self.write("docs/wp/mvp0/WP-00-a.md", wp_text("WP-00", stubs="[core/x.py, core/y/z.css]"))
        self.write("docs/wp/mvp0/C-01-b.md", wp_text("C-01", deps="[WP-00]", owns="[core/x.py]"))
        self.write(
            "docs/wp/mvp0/W-01-c.md",
            wp_text("W-01", platform="windows", lane="windows", deps="[WP-00]", owns="[core/y/]"),
        )
        self.assertEqual(self.run_checks().errors, [])

    def test_stubber_must_not_own_the_stub_path(self) -> None:
        self.write(
            "docs/wp/mvp0/WP-00-a.md",
            wp_text("WP-00", owns="[core/x.py]", stubs="[core/x.py]"),
        )
        self.assertHasError(self.run_checks(), "WP-00", "stubs", "owns")

    def test_stubs_must_be_a_list(self) -> None:
        self.write("docs/wp/mvp0/WP-00-a.md", wp_text("WP-00", stubs="core/x.py"))
        self.assertHasError(self.run_checks(), "WP-00-a.md", "stubs")

    def test_owner_may_append_to_own_file(self) -> None:
        self.write(
            "docs/wp/mvp0/WP-00-a.md",
            wp_text("WP-00", owns="[core/registry.py]", appends="[core/registry.py]"),
        )
        self.assertEqual(self.run_checks().errors, [])


if __name__ == "__main__":
    unittest.main()
