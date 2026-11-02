"""核心包冒烟测试：版本、时区、平台层。"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pytest

import sentinel
from sentinel import platform


def test_package_is_importable_and_versioned() -> None:
    assert sentinel.__version__ == "0.1.0"


def test_duckdb_version_is_pinned() -> None:
    assert duckdb.__version__ == "1.4.3"


@pytest.mark.macos
def test_platform_name_is_macos_here() -> None:
    assert platform.name() == "macos"


def test_new_york_timezone_handles_dst_boundaries() -> None:
    new_york = ZoneInfo("America/New_York")
    cases = [
        (datetime(2026, 3, 8, 6, 59, tzinfo=UTC), -5),
        (datetime(2026, 3, 8, 7, 0, tzinfo=UTC), -4),
        (datetime(2026, 11, 1, 5, 59, tzinfo=UTC), -4),
        (datetime(2026, 11, 1, 6, 0, tzinfo=UTC), -5),
    ]
    for moment, expected_hours in cases:
        offset = moment.astimezone(new_york).utcoffset()
        assert offset is not None
        assert offset.total_seconds() == expected_hours * 3600


@pytest.mark.macos
def test_posix_is_process_alive() -> None:
    assert platform.is_process_alive(os.getpid()) is True

    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=10)
    assert platform.is_process_alive(child.pid) is False

    assert platform.is_process_alive(0) is False
    assert platform.is_process_alive(-1) is False


@pytest.mark.macos
def test_posix_file_lock_is_exclusive(tmp_path: Path) -> None:
    lock_path = tmp_path / "core.lock"
    with platform.file_lock(lock_path):  # noqa: SIM117 - 嵌套才能表达“持锁期间再抢锁”
        with pytest.raises(platform.AlreadyRunning):
            with platform.file_lock(lock_path):
                pass

    with platform.file_lock(lock_path):
        pass


@pytest.mark.macos
def test_posix_harden_permissions_sets_modes(tmp_path: Path) -> None:
    directory = tmp_path / "data"
    directory.mkdir()
    file_path = tmp_path / "secret"
    file_path.write_text("x", encoding="utf-8")

    platform.harden_permissions(directory)
    platform.harden_permissions(file_path)

    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(file_path.stat().st_mode) == 0o600

    with pytest.raises(FileNotFoundError):
        platform.harden_permissions(tmp_path / "missing")


@pytest.mark.macos
def test_posix_default_data_dir_is_under_application_support() -> None:
    path = platform.default_data_dir()
    assert path.parts[-3:] == ("Library", "Application Support", "Sentinel")
