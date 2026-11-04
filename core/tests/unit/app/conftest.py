from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from sentinel.app.args import AppArgs
from sentinel.app.container import AppContainer, build_container
from sentinel.secrets import MemorySecretStore

ROOT = Path(__file__).resolve().parents[4]
RESOURCES = ROOT / "resources"


@pytest.fixture(autouse=True)
def _isolated_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """组合根会重配全局日志；单测里保持 caplog 与其他用例的日志行为不变。"""
    monkeypatch.setattr("sentinel.app.main.logging_setup.configure", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _isolated_policies() -> Iterator[None]:
    """真实行情源会在构造时调整全局限流策略；测试结束恢复，避免污染其他用例。"""
    from sentinel.http.policy import POLICIES

    snapshot = dict(POLICIES)
    try:
        yield
    finally:
        POLICIES.clear()
        POLICIES.update(snapshot)


@pytest.fixture
def args(tmp_path: Path) -> AppArgs:
    return AppArgs(tmp_path / "data", RESOURCES, None, "WARN")


@pytest.fixture
def store() -> MemorySecretStore:
    return MemorySecretStore()


@pytest.fixture
def container(args: AppArgs, store: MemorySecretStore) -> Iterator[AppContainer]:
    built = build_container(args, secret_store=store)
    try:
        yield built
    finally:
        built.close()
