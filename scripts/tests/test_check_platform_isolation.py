"""check_platform_isolation.py 的单元测试。运行：python3 -m unittest discover -s scripts/tests -v"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_platform_isolation as isolation  # noqa: E402


class ScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, relative: str, text: str, encoding: str = "utf-8") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=encoding)
        return path

    def test_python_sys_platform_outside_platform_layer_is_reported(self) -> None:
        self.write(
            "core/sentinel/app/x.py",
            'import sys\nif sys.platform == "win32": pass\n',
        )
        findings = isolation.scan(self.root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "core/sentinel/app/x.py")
        self.assertEqual(findings[0].line, 2)

    def test_sys_platform_inside_platform_layer_is_allowed(self) -> None:
        self.write(
            "core/sentinel/platform/__init__.py",
            'import sys\nif sys.platform == "win32": pass\n',
        )
        self.assertEqual(isolation.scan(self.root), [])

    def test_rust_cfg_target_os_outside_platform_layer_is_reported(self) -> None:
        self.write(
            "apps/desktop/src-tauri/src/lib.rs",
            '#[cfg(target_os = "macos")]\nfn main() {}\n',
        )
        findings = isolation.scan(self.root)
        self.assertEqual(len(findings), 1)

    def test_rust_cfg_inside_platform_layer_is_allowed(self) -> None:
        self.write(
            "apps/desktop/src-tauri/src/platform/mod.rs",
            '#[cfg(target_os = "macos")]\nmod macos;\n',
        )
        self.assertEqual(isolation.scan(self.root), [])

    def test_ts_process_platform_is_reported(self) -> None:
        self.write("apps/desktop/src/x.ts", "const p = process.platform;\n")
        self.assertEqual(len(isolation.scan(self.root)), 1)

    def test_ts_navigator_user_agent_is_reported(self) -> None:
        self.write("apps/desktop/src/x.ts", "const ua = navigator.userAgent;\n")
        self.assertEqual(len(isolation.scan(self.root)), 1)

    def test_generated_and_vendor_dirs_are_ignored(self) -> None:
        self.write("node_modules/a.js", "process.platform;\n")
        self.write("apps/desktop/src/rpc/generated/a.ts", "navigator.userAgent;\n")
        self.assertEqual(isolation.scan(self.root), [])

    def test_unpaired_shell_script_is_reported(self) -> None:
        self.write("scripts/a.sh", "#!/bin/sh\n")
        findings = isolation.scan(self.root)
        self.assertEqual(len(findings), 1)
        self.assertIn("a.ps1", findings[0].message)

    def test_paired_scripts_pass(self) -> None:
        self.write("scripts/a.sh", "#!/bin/sh\n")
        self.write("scripts/a.ps1", "exit 0\n")
        self.assertEqual(isolation.scan(self.root), [])

    def test_underscore_helper_scripts_are_exempt_from_pairing(self) -> None:
        self.write("scripts/_py.ps1", "exit 0\n")
        self.assertEqual(isolation.scan(self.root), [])

    def test_unpaired_ps1_script_is_reported(self) -> None:
        self.write("scripts/b.ps1", "exit 0\n")
        findings = isolation.scan(self.root)
        self.assertEqual(len(findings), 1)
        self.assertIn("b.sh", findings[0].message)

    def test_non_utf8_file_is_reported_not_skipped(self) -> None:
        path = self.root / "core" / "bad.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xff\xfe")
        findings = isolation.scan(self.root)
        self.assertEqual(len(findings), 1)
        self.assertIn("UTF-8", findings[0].message)

    def test_clean_tree_passes_and_main_returns_0(self) -> None:
        self.write("core/sentinel/app/ok.py", "value = 1\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(isolation.main([str(self.root)]), 0)


if __name__ == "__main__":
    unittest.main()
