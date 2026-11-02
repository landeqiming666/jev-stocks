"""doctor.py 的单元测试。运行：python3 -m unittest discover -s scripts/tests -v"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import doctor  # noqa: E402


class FakeResult:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


def make_run(node_version="v26.1.0"):
    def run(argv, **kwargs):
        name = Path(str(argv[0])).name
        if name == "node":
            return FakeResult(node_version + "\n")
        if name == "python3" or str(argv[0]) == sys.executable:
            return FakeResult("Python 3.9.6\n")
        return FakeResult(name + " version 1.0.0\n")

    return run


def make_which(missing=()):
    def which(name):
        if name in missing:
            return None
        return "/fake/" + name

    return which


def run_main(root, missing=(), node_version="v26.1.0"):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = doctor.main(
            [],
            run=make_run(node_version),
            which=make_which(missing),
            root=Path(root),
        )
    return code, buffer.getvalue()


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_missing_required_tool_returns_1(self) -> None:
        code, output = run_main(self.root, missing=("pnpm",))
        self.assertEqual(code, 1)
        self.assertIn("pnpm", output)
        self.assertIn("npm install -g pnpm", output)

    def test_missing_optional_tool_returns_0(self) -> None:
        code, _ = run_main(self.root, missing=("cmake",))
        self.assertEqual(code, 0)

    def test_node_major_mismatch_is_warning_only(self) -> None:
        (self.root / ".node-version").write_text("22\n", encoding="utf-8")
        code, output = run_main(self.root, node_version="v26.1.0")
        self.assertEqual(code, 0)
        self.assertIn("WARN", output)


if __name__ == "__main__":
    unittest.main()
