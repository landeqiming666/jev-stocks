"""W-01 behavioral contracts, prepared before the Windows implementation.

All filesystem and ACL operations are restricted to pytest-owned temporary paths.
"""

from __future__ import annotations

import csv
import json
import os
import queue
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from sentinel import platform

pytestmark = pytest.mark.windows

BROAD_SIDS = {"S-1-1-0", "S-1-5-32-545", "S-1-5-11"}
FULL_CONTROL = 0x1F01FF


@contextmanager
def _restore_acl_after(path: Path):
    """Restore this owned test object's original DACL, including on assertion failure."""
    prefix = (
        "$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
        "$target=$env:W01_TEST_ACL_PATH;"
    )
    kind = "Directory" if path.is_dir() else "File"
    command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"]
    environment = {**os.environ, "W01_TEST_ACL_PATH": str(path)}
    original = (
        subprocess.run(
            [
                *command,
                prefix + f"$acl=[IO.{kind}]::GetAccessControl($target);"
                "$acl.GetSecurityDescriptorSddlForm([Security.AccessControl.AccessControlSections]::Access)",
            ],
            env=environment,
            capture_output=True,
            check=True,
            timeout=15,
        )
        .stdout.decode("utf-8-sig")
        .strip()
    )
    try:
        yield
    finally:
        environment["W01_TEST_ORIGINAL_DACL"] = original
        restore = (
            prefix + f"$acl=[Security.AccessControl.{kind}Security]::new();"
            "$acl.SetSecurityDescriptorSddlForm($env:W01_TEST_ORIGINAL_DACL,"
            "[Security.AccessControl.AccessControlSections]::Access);"
            f"[IO.{kind}]::SetAccessControl($target,$acl)"
        )
        subprocess.run(
            [*command, restore], env=environment, capture_output=True, check=True, timeout=15
        )


def _current_user_sid() -> str:
    result = subprocess.run(
        ["whoami.exe", "/user", "/fo", "csv", "/nh"],
        check=True,
        capture_output=True,
        timeout=10,
    )
    row = next(csv.reader(result.stdout.decode("oem").splitlines()))
    return row[1]


def _acl_entries(path: Path) -> list[dict[str, object]]:
    """Read SID values instead of localized English or Chinese group names."""
    script = (
        "$ErrorActionPreference='Stop';"
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
        "$target=$env:W01_TEST_ACL_PATH;"
        "if([IO.Directory]::Exists($target)){$acl=[IO.Directory]::GetAccessControl($target)}"
        "else{$acl=[IO.File]::GetAccessControl($target)};"
        "$entries=@($acl.GetAccessRules($true,$true,"
        "[Security.Principal.SecurityIdentifier]) | "
        "ForEach-Object { @{sid=$_.IdentityReference.Value;"
        "allow=($_.AccessControlType -eq 'Allow');"
        "rights=[int]$_.FileSystemRights;inherited=$_.IsInherited} });"
        "ConvertTo-Json -InputObject $entries -Compress"
    )
    environment = {**os.environ, "W01_TEST_ACL_PATH": str(path)}
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env=environment,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    entries = json.loads(result.stdout.decode("utf-8-sig"))
    assert isinstance(entries, list)
    return entries


def _assert_current_user_only(path: Path, *, inherited: bool = False) -> None:
    sid = _current_user_sid()
    (entry,) = _acl_entries(path)
    assert entry["sid"] == sid
    assert entry["allow"] is True
    assert entry["inherited"] is inherited
    assert int(entry["rights"]) & FULL_CONTROL == FULL_CONTROL


def test_name_is_windows() -> None:
    assert platform.name() == "windows"


def test_default_data_dir_uses_localappdata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    expected = tmp_path / "Sentinel"
    assert platform.default_data_dir() == expected
    assert not expected.exists()


def test_default_data_dir_falls_back_without_localappdata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    home = tmp_path / "test-home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    expected = home / "AppData" / "Local" / "Sentinel"
    assert platform.default_data_dir() == expected
    assert not expected.exists()


def test_is_process_alive_for_current_process() -> None:
    assert platform.is_process_alive(os.getpid()) is True


def test_is_process_alive_false_after_exit() -> None:
    with subprocess.Popen([sys.executable, "-c", "pass"]) as child:
        assert child.wait(timeout=10) == 0
        assert platform.is_process_alive(child.pid) is False


def test_is_process_alive_false_for_invalid_pids() -> None:
    assert platform.is_process_alive(0) is False
    assert platform.is_process_alive(-1) is False


def test_file_lock_is_exclusive_within_process(tmp_path: Path) -> None:
    path = tmp_path / "core.lock"
    with platform.file_lock(path):
        with pytest.raises(platform.AlreadyRunning) as error, platform.file_lock(path):
            pytest.fail("A second handle must not acquire the same byte")
        assert isinstance(error.value.__cause__, OSError)
    assert path.exists()
    with platform.file_lock(path):
        pass


def test_file_lock_is_exclusive_across_processes(tmp_path: Path) -> None:
    path = tmp_path / "shared.lock"
    code = (
        "from pathlib import Path\n"
        "import sys\n"
        "from sentinel import platform\n"
        "with platform.file_lock(Path(sys.argv[1])):\n"
        "    print('LOCKED', flush=True)\n"
        "    sys.stdin.read()\n"
    )
    with subprocess.Popen(
        [sys.executable, "-u", "-c", code, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ) as child:
        ready: queue.Queue[str] = queue.Queue()
        assert child.stdout is not None
        threading.Thread(target=lambda: ready.put(child.stdout.readline()), daemon=True).start()
        try:
            assert ready.get(timeout=8).strip() == "LOCKED"
            with pytest.raises(platform.AlreadyRunning), platform.file_lock(path):
                pytest.fail("Parent acquired a lock held by its controlled child")
        finally:
            assert child.stdin is not None
            # EOF reaches the interpreter even when sys.executable is a venv launcher.
            child.stdin.close()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        assert child.returncode == 0
    with platform.file_lock(path):
        pass


def test_file_lock_creates_parent_directory(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "x.lock"
    with platform.file_lock(path):
        assert path.parent.is_dir()
    assert path.is_file()


def test_harden_permissions_removes_broad_groups(tmp_path: Path) -> None:
    directory = tmp_path / "temporary-acl-target"
    directory.mkdir()
    existing_child = directory / "existing.txt"
    existing_child.touch()
    child_acl = _acl_entries(existing_child)
    with _restore_acl_after(directory):
        # Explicit grants expose implementations which only remove inheritance.
        subprocess.run(
            ["icacls.exe", str(directory), "/grant", *[f"*{sid}:(RX)" for sid in BROAD_SIDS]],
            check=True,
            capture_output=True,
            timeout=10,
        )
        assert {entry["sid"] for entry in _acl_entries(directory)} >= BROAD_SIDS
        platform.harden_permissions(directory)
        _assert_current_user_only(directory)
        assert _acl_entries(existing_child) == child_acl
        sample = directory / "writable.txt"
        sample.write_text("probe", encoding="utf-8")
        assert sample.read_text(encoding="utf-8") == "probe"
        _assert_current_user_only(sample, inherited=True)


def test_harden_permissions_missing_path_raises(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    with pytest.raises(FileNotFoundError):
        platform.harden_permissions(missing)
    assert not missing.exists()


def test_harden_permissions_handles_spaces_and_unicode(tmp_path: Path) -> None:
    directory = tmp_path / "含 空格 目录"
    directory.mkdir()
    with _restore_acl_after(directory):
        platform.harden_permissions(directory)
        sample = directory / "probe.txt"
        sample.write_text("可读写", encoding="utf-8")
        assert sample.read_text(encoding="utf-8") == "可读写"
        _assert_current_user_only(directory)


def test_file_lock_nonempty_file_keeps_content_and_exclusion(tmp_path: Path) -> None:
    path = tmp_path / "nonempty.lock"
    path.write_bytes(b"existing-content")
    with platform.file_lock(path), pytest.raises(platform.AlreadyRunning), platform.file_lock(path):
        pass
    assert path.read_bytes() == b"existing-content"


def test_file_lock_releases_when_context_body_raises(tmp_path: Path) -> None:
    path = tmp_path / "exception.lock"
    with pytest.raises(RuntimeError, match="controlled error"), platform.file_lock(path):
        raise RuntimeError("controlled error")
    with platform.file_lock(path):
        pass


def test_harden_permissions_handles_a_file(tmp_path: Path) -> None:
    path = tmp_path / "temporary-file.txt"
    path.write_text("before", encoding="utf-8")
    with _restore_acl_after(path):
        platform.harden_permissions(path)
        path.write_text("after", encoding="utf-8")
        assert path.read_text(encoding="utf-8") == "after"
        _assert_current_user_only(path)


def test_file_lock_locks_byte_zero_on_nonempty_file(tmp_path: Path) -> None:
    path = tmp_path / "byte-zero.lock"
    path.write_bytes(b"existing-content")
    code = (
        "import msvcrt,sys\n"
        "with open(sys.argv[1], 'r+b') as stream:\n"
        "    stream.seek(0)\n"
        "    try:\n"
        "        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)\n"
        "    except OSError:\n"
        "        print('blocked')\n"
        "    else:\n"
        "        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)\n"
        "        print('acquired')\n"
        "        sys.exit(3)\n"
    )
    with platform.file_lock(path):
        result = subprocess.run(
            [sys.executable, "-c", code, str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "blocked"
    assert path.read_bytes() == b"existing-content"


def test_is_process_alive_false_for_terminated_exit_259() -> None:
    """The actual exit code 259 does not make a terminated process alive."""
    with subprocess.Popen([sys.executable, "-c", "import os; os._exit(259)"]) as child:
        assert child.wait(timeout=10) == 259
        assert platform.is_process_alive(child.pid) is False


@pytest.mark.parametrize("pid", [2**32, 2**32 + os.getpid()])
def test_is_process_alive_rejects_pid_outside_dword(pid: int) -> None:
    # The second value must not wrap around and query this test process instead.
    assert platform.is_process_alive(pid) is False
