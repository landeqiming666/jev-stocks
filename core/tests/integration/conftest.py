from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.integration.harness import ROOT, CoreConfig, CoreHarness


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    path = tmp_path / "含 空格 目录" / "sentinel"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def core(data_dir: Path) -> Iterator[CoreHarness]:
    harness = CoreHarness(CoreConfig(data_dir=data_dir, resource_dir=ROOT / "resources"))
    harness.start()
    try:
        yield harness
    finally:
        harness.stop()
