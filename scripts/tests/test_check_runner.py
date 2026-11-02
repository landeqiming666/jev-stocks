"""check.py 的单元测试。运行：python3 -m unittest discover -s scripts/tests -v"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check as runner  # noqa: E402


class FakeResult:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode


class Recorder:
    """记录 run_steps 调用的假 runner。"""

    def __init__(self, codes=None) -> None:
        self.codes = list(codes or [])
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), dict(kwargs)))
        code = self.codes.pop(0) if self.codes else 0
        return FakeResult(code)


def fake_which(name):
    return name


def collect(lines):
    def out(message):
        lines.append(message)

    return out


def make_step(name="a", command=None, cwd=".", requires=None, needs_flag=None):
    return runner.Step(
        name=name,
        command=command or ["echo", "ok"],
        cwd=cwd,
        requires=requires or [],
        needs_flag=needs_flag,
    )


class RunStepsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_skips_step_when_required_path_missing(self) -> None:
        rec = Recorder()
        lines = []
        code = runner.run_steps(
            [make_step(requires=["nope"])],
            self.root,
            runner=rec,
            which=fake_which,
            out=collect(lines),
        )
        self.assertEqual(code, 0)
        self.assertTrue(any("SKIP" in line for line in lines))
        self.assertEqual(rec.calls, [])

    def test_runs_step_and_reports_pass(self) -> None:
        (self.root / "present").write_text("", encoding="utf-8")
        rec = Recorder([0])
        lines = []
        code = runner.run_steps(
            [make_step(requires=["present"])],
            self.root,
            runner=rec,
            which=fake_which,
            out=collect(lines),
        )
        self.assertEqual(code, 0)
        self.assertTrue(any("PASS" in line for line in lines))
        self.assertEqual(len(rec.calls), 1)

    def test_failure_does_not_stop_later_steps_and_returns_1(self) -> None:
        rec = Recorder([1, 0])
        lines = []
        code = runner.run_steps(
            [make_step("a"), make_step("b")],
            self.root,
            runner=rec,
            which=fake_which,
            out=collect(lines),
        )
        self.assertEqual(code, 1)
        self.assertEqual(len(rec.calls), 2)
        self.assertTrue(any("失败 1" in line for line in lines))

    def test_only_filter_runs_selected_steps(self) -> None:
        rec = Recorder([0])
        lines = []
        code = runner.run_steps(
            [make_step("a"), make_step("b"), make_step("c")],
            self.root,
            only=["b"],
            runner=rec,
            which=fake_which,
            out=collect(lines),
        )
        self.assertEqual(code, 0)
        self.assertEqual([call[0][0] for call in rec.calls], ["echo"])
        self.assertEqual(len(rec.calls), 1)
        self.assertTrue(any("SKIP" in line and "未选中" in line for line in lines))

    def test_optional_step_requires_flag(self) -> None:
        rec = Recorder([0])
        lines = []
        runner.run_steps(
            [make_step("e2e", needs_flag="e2e")],
            self.root,
            flags=set(),
            runner=rec,
            which=fake_which,
            out=collect(lines),
        )
        self.assertEqual(rec.calls, [])
        self.assertTrue(any("SKIP" in line and "--e2e" in line for line in lines))

        runner.run_steps(
            [make_step("e2e", needs_flag="e2e")],
            self.root,
            flags={"e2e"},
            runner=rec,
            which=fake_which,
            out=collect(lines),
        )
        self.assertEqual(len(rec.calls), 1)

    def test_missing_executable_is_failure_with_hint(self) -> None:
        rec = Recorder()
        lines = []
        code = runner.run_steps(
            [make_step(command=["pnpm", "test"])],
            self.root,
            runner=rec,
            which=lambda name: None,
            out=collect(lines),
        )
        self.assertEqual(code, 1)
        joined = "\n".join(lines)
        self.assertIn("FAIL", joined)
        self.assertIn("doctor", joined)
        self.assertEqual(rec.calls, [])

    def test_paths_with_spaces_are_passed_as_single_argv_items(self) -> None:
        spaced = self.root / "with space"
        (spaced / "sub dir").mkdir(parents=True)
        (spaced / "needed file").write_text("", encoding="utf-8")
        rec = Recorder([0])
        lines = []
        code = runner.run_steps(
            [make_step(command=["echo", "a b"], cwd="sub dir", requires=["needed file"])],
            spaced,
            runner=rec,
            which=fake_which,
            out=collect(lines),
        )
        self.assertEqual(code, 0)
        argv, kwargs = rec.calls[0]
        self.assertEqual(argv, ["echo", "a b"])
        self.assertEqual(kwargs["cwd"], str(spaced / "sub dir"))
        self.assertNotIn("shell", kwargs)

    def test_python_placeholder_is_replaced(self) -> None:
        rec = Recorder([0])
        runner.run_steps(
            [make_step(command=["{python}", "x.py"])],
            self.root,
            runner=rec,
            which=fake_which,
            out=collect([]),
        )
        argv, _ = rec.calls[0]
        self.assertEqual(argv[0], sys.executable)

    def test_list_flag_prints_steps_without_running(self) -> None:
        rec = Recorder()
        lines = []
        code = runner.main(
            ["--list"],
            steps=[make_step("alpha"), make_step("beta", requires=["nope"])],
            root=self.root,
            runner=rec,
            which=fake_which,
            out=collect(lines),
        )
        joined = "\n".join(lines)
        self.assertEqual(code, 0)
        self.assertIn("alpha", joined)
        self.assertIn("beta", joined)
        self.assertEqual(rec.calls, [])


if __name__ == "__main__":
    unittest.main()
