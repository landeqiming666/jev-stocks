import sys
from types import SimpleNamespace

import pytest

from sentinel.platform import keyring_store, macos_keychain


class FakeBackend:
    def __init__(self) -> None:
        self.writes: list[tuple[str, str, str]] = []

    def get_password(self, service: str, username: str) -> str | None:
        return None

    def set_password(self, service: str, username: str, password: str) -> None:
        self.writes.append((service, username, password))

    def delete_password(self, service: str, username: str) -> None:
        pass


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_custom_backend_remains_injected(monkeypatch: pytest.MonkeyPatch, platform: str) -> None:
    monkeypatch.setattr(keyring_store, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setitem(
        sys.modules, "keyring.backends.macOS", SimpleNamespace(Keyring=type("Native", (), {}))
    )
    backend = FakeBackend()
    keyring_store.set_password(backend, "test-service", "test-account", "test-value")
    assert backend.writes == [("test-service", "test-account", "test-value")]


def test_real_macos_backend_uses_atomic_platform_writer(monkeypatch: pytest.MonkeyPatch) -> None:
    class Native(FakeBackend):
        pass

    monkeypatch.setattr(keyring_store, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setitem(sys.modules, "keyring.backends.macOS", SimpleNamespace(Keyring=Native))
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        macos_keychain, "set_generic_password_atomic", lambda *args: calls.append(args)
    )
    backend = Native()
    keyring_store.set_password(backend, "test-service", "test-account", "test-value")
    assert calls == [("test-service", "test-account", "test-value")]
    assert not backend.writes


def test_native_failure_has_atomic_marker_and_no_sensitive_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Native(FakeBackend):
        pass

    monkeypatch.setattr(keyring_store, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setitem(sys.modules, "keyring.backends.macOS", SimpleNamespace(Keyring=Native))

    def fail(*args: str) -> None:
        raise RuntimeError("test-sensitive-value")

    monkeypatch.setattr(macos_keychain, "set_generic_password_atomic", fail)
    backend = Native()
    with pytest.raises(keyring_store.AtomicWriteError) as error:
        keyring_store.set_password(backend, "test-service", "test-account", "test-sensitive-value")
    assert "test-sensitive-value" not in str(error.value)
    assert not backend.writes
