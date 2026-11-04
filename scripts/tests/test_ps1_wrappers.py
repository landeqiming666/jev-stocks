"""W-01 包装器测试，在临时副本中用受控 Python 脚本验证参数与退出码。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
WRAPPERS = ("doctor", "check", "setup", "dev")
STUB = """import json, os, sys
print(json.dumps({"script": __file__, "argv": sys.argv[1:], "cwd": os.getcwd()}))
sys.exit(int(os.environ.get("W01_STUB_EXIT", "0")))
"""


@unittest.skipUnless(os.name == "nt", "PowerShell 包装器仅在 Windows 上验证")
class PowerShellWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.shells = []
        for name in ("powershell.exe", "pwsh.exe"):
            executable = shutil.which(name)
            if executable:
                cls.shells.append(executable)
        if not cls.shells:
            raise unittest.SkipTest("没有可用的 Windows PowerShell 或 PowerShell 7")

    def setUp(self) -> None:
        parent = ROOT.parent / "tmp" / "w01" / "ps1-tests"
        parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="包装器 含空格 ", dir=parent)
        self.addCleanup(temporary.cleanup)
        self.fixture = Path(temporary.name)
        self.cwd = self.fixture / "工作目录 带 空格"
        self.cwd.mkdir()

    def run_ps1(self, shell, path, arguments=(), *, extra_env=None):
        env = os.environ.copy()
        env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        env.update(extra_env or {})
        result = subprocess.run(
            [shell, "-NoProfile", "-File", str(path), *arguments],
            cwd=self.cwd, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=45,
        )
        try:
            output = result.stdout.decode("utf-8")
        except UnicodeDecodeError:
            output = result.stdout.decode("cp936", errors="replace")
        return result.returncode, output

    def isolated_wrappers(self):
        scripts = self.fixture / "工程 含空格" / "scripts"
        scripts.mkdir(parents=True)
        for name in WRAPPERS:
            shutil.copy2(SCRIPTS / (name + ".ps1"), scripts)
            (scripts / (name + ".py")).write_text(STUB, encoding="utf-8")
        helper = SCRIPTS / "_py.ps1"
        if helper.exists():
            shutil.copy2(helper, scripts)
        return scripts

    def test_doctor_ps1_runs_and_mentions_uv(self) -> None:
        for shell in self.shells:
            with self.subTest(shell=Path(shell).name):
                code, output = self.run_ps1(shell, SCRIPTS / "doctor.ps1")
                self.assertIn(code, (0, 1), output)
                self.assertIn("uv", output.lower(), output)

    def test_check_ps1_list_prints_all_steps(self) -> None:
        for shell in self.shells:
            with self.subTest(shell=Path(shell).name):
                code, output = self.run_ps1(shell, SCRIPTS / "check.ps1", ("--list",))
                self.assertEqual(code, 0, output)
                for step in ("docs", "py-test", "web-lint", "rust-clippy"):
                    self.assertIn(step, output)

    def test_wrapper_passes_arguments_with_spaces(self) -> None:
        isolated = self.isolated_wrappers()
        arguments = ("--only", "docs", "--label", "中文 参数 含 空格", "值&分号;原样")
        for shell in self.shells:
            with self.subTest(shell=Path(shell).name):
                code, output = self.run_ps1(shell, isolated / "check.ps1", arguments)
                self.assertEqual(code, 0, output)
                payload = json.loads(output.strip())
                self.assertEqual(payload["argv"], list(arguments))
                self.assertEqual(Path(payload["cwd"]), self.cwd)
                self.assertEqual(Path(payload["script"]), isolated / "check.py")
                code, output = self.run_ps1(
                    shell, SCRIPTS / "check.ps1", ("--only", "docs")
                )
                self.assertEqual(code, 0, output)

    def test_wrapper_preserves_empty_quoted_and_trailing_backslash_arguments(self) -> None:
        isolated = self.isolated_wrappers()
        arguments = ("", '嵌入"引号" 和空格', "尾随 反斜杠\\", '反斜杠\\" 和引号', "O'Brien")
        driver = isolated / "driver.ps1"
        literals = ", ".join("'" + value.replace("'", "''") + "'" for value in arguments)
        driver.write_text(
            f"$values = @({literals})\n"
            '& "$PSScriptRoot\\check.ps1" @values\n'
            "exit $LASTEXITCODE\n",
            encoding="utf-8-sig",
        )
        for shell in self.shells:
            with self.subTest(shell=Path(shell).name):
                code, output = self.run_ps1(shell, driver)
                self.assertEqual(code, 0, output)
                self.assertEqual(json.loads(output.strip())["argv"], list(arguments))

    def test_wrapper_exit_code_is_propagated(self) -> None:
        isolated = self.isolated_wrappers()
        for shell in self.shells:
            for name in WRAPPERS:
                with self.subTest(shell=Path(shell).name, wrapper=name):
                    code, output = self.run_ps1(
                        shell, isolated / (name + ".ps1"), ("含 空格 参数",),
                        extra_env={"W01_STUB_EXIT": "7"},
                    )
                    self.assertEqual(code, 7, output)
                    payload = json.loads(output.strip())
                    self.assertEqual(Path(payload["script"]), isolated / (name + ".py"))
                    self.assertEqual(payload["argv"], ["含 空格 参数"])

    def test_every_ps1_wrapper_has_a_sh_pair(self) -> None:
        for path in sorted(SCRIPTS.glob("*.ps1")):
            if not path.stem.startswith("_"):
                with self.subTest(wrapper=path.name):
                    self.assertTrue(path.with_suffix(".sh").is_file())

    def test_ps1_files_have_utf8_bom_and_crlf(self) -> None:
        for name in (*WRAPPERS, "_py"):
            with self.subTest(script=name):
                path = SCRIPTS / (name + ".ps1")
                self.assertTrue(path.is_file(), str(path))
                data = path.read_bytes()
                self.assertTrue(data.startswith(b"\xef\xbb\xbf"), "需要 UTF-8 BOM")
                self.assertIn(b"\r\n", data, "需要 CRLF")
                self.assertNotIn(b"\n", data.replace(b"\r\n", b""), "存在单独 LF")


if __name__ == "__main__":
    unittest.main()
