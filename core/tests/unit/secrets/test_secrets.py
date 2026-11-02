import logging

import pytest

from sentinel.clock import parse_iso
from sentinel.errors import InternalError, UserError
from sentinel.logging_setup import JsonFormatter
from sentinel.messages.settings import MESSAGES
from sentinel.secrets import KeyringSecretStore, MemorySecretStore, SecretsService
from sentinel.security.redact import MASK, clear_secrets, redact_text


@pytest.fixture
def service() -> SecretsService:
    clear_secrets()
    return SecretsService(MemorySecretStore(), lambda: parse_iso("2026-11-02T00:35:00Z"))


def test_secret_is_never_returned(service: SecretsService) -> None:
    assert service.status() == {"jevKey": False}
    service.set_jev_key(" test-key-do-not-use ")
    assert service.status() == {"jevKey": True}
    assert service.get_jev_key() == "test-key-do-not-use"
    service.clear_jev_key()
    service.clear_jev_key()
    assert service.status() == {"jevKey": False}
    assert redact_text("test-key-do-not-use") == MASK


@pytest.mark.parametrize(
    "value", ["", " \x1c", "sk test", "a\nb", "a\tb", "a\u2003b", "x" * 513, True]
)
def test_secret_rejects_whitespace(service: SecretsService, value: object) -> None:
    with pytest.raises(UserError):
        service.set_jev_key(value)
    assert service.status() == {"jevKey": False}


def test_secret_normalized_length_boundary(service: SecretsService) -> None:
    service.set_jev_key("\x1c" + "x" * 512 + "\x1c")
    assert service.get_jev_key() == "x" * 512


def test_existing_key_and_replaced_key_stay_redacted(service: SecretsService) -> None:
    store = MemorySecretStore()
    store.set("typesafe_api_key", "old-test-key-do-not-use")
    service = SecretsService(store, lambda: parse_iso("2026-11-02T00:35:00Z"))
    assert service.status() == {"jevKey": True}
    service.set_jev_key("new-test-key-do-not-use")
    service.clear_jev_key()
    record = logging.LogRecord(
        "sentinel", logging.INFO, "", 0, "old-test-key-do-not-use new-test-key-do-not-use", (), None
    )
    text = JsonFormatter().format(record)
    assert "old-test-key-do-not-use" not in text and "new-test-key-do-not-use" not in text


class FakeBackend:
    def __init__(self, failed: str = "", destructive: bool = False) -> None:
        self.values = {("sentinel", "typesafe_api_key"): "old-test-key-do-not-use"}
        self.failed = failed
        self.destructive = destructive

    def _check(self, operation: str) -> None:
        if self.failed == operation:
            raise RuntimeError("private-provider-payload old-test-key-do-not-use")

    def get_password(self, service: str, username: str) -> str | None:
        self._check("get")
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._check("set")
        if self.destructive and password == "new-test-key-do-not-use":
            self.values.pop((service, username), None)
            raise RuntimeError("private-provider-payload")
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._check("delete")
        self.values.pop((service, username), None)


@pytest.mark.parametrize("operation", ["get", "set", "delete"])
def test_keyring_errors_are_safe_and_preserve_old_key(operation: str) -> None:
    backend = FakeBackend(failed=operation)
    service = SecretsService(
        KeyringSecretStore(backend=backend), lambda: parse_iso("2026-11-02T00:35:00Z")
    )
    with pytest.raises(InternalError) as caught:
        {
            "get": service.status,
            "set": lambda: service.set_jev_key("new-test-key-do-not-use"),
            "delete": service.clear_jev_key,
        }[operation]()
    assert "private-provider-payload" not in str(caught.value.to_wire("r-c04"))
    assert caught.value.message_key == "settings.keyring_unavailable"
    assert MESSAGES[caught.value.message_key].format()
    assert backend.values[("sentinel", "typesafe_api_key")] == "old-test-key-do-not-use"


def test_provider_failure_after_delete_restores_old_key() -> None:
    backend = FakeBackend(destructive=True)
    service = SecretsService(
        KeyringSecretStore(backend=backend), lambda: parse_iso("2026-11-02T00:35:00Z")
    )
    with pytest.raises(InternalError):
        service.set_jev_key("new-test-key-do-not-use")
    assert service.get_jev_key() == "old-test-key-do-not-use"


def test_default_backend_is_selected_once_and_never_global_password_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import keyring

    backend = FakeBackend()
    calls: list[str] = []

    def get_keyring() -> FakeBackend:
        calls.append("provider")
        return backend

    monkeypatch.setattr(keyring, "get_keyring", get_keyring)
    store = KeyringSecretStore()
    store.set("typesafe_api_key", "new-test-key-do-not-use")
    assert store.get("typesafe_api_key") == "new-test-key-do-not-use"
    store.delete("typesafe_api_key")
    store.delete("typesafe_api_key")
    assert store.get("typesafe_api_key") is None
    assert calls == ["provider"]


def test_atomic_platform_write_failure_never_mutates_old_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sentinel.platform import keyring_store

    backend = FakeBackend()
    calls: list[tuple[str, str]] = []

    def fail(provider, service: str, account: str, value: str) -> None:
        assert provider is backend
        calls.append((service, account))
        raise RuntimeError("private-atomic-error new-test-key-do-not-use")

    monkeypatch.setattr(keyring_store, "set_password", fail)
    store = KeyringSecretStore(backend=backend)
    with pytest.raises(InternalError) as caught:
        store.set("typesafe_api_key", "new-test-key-do-not-use")
    assert store.get("typesafe_api_key") == "old-test-key-do-not-use"
    assert calls == [("sentinel", "typesafe_api_key")]
    assert caught.value.message_key == "settings.keyring_unavailable"
    assert "private-atomic-error" not in str(caught.value.to_wire("r-c04"))


def test_invalid_secret_selects_domain_message(service: SecretsService) -> None:
    from sentinel.settings.models import SecretSet

    for value in ("", "a\x1cb", "x" * 513, True):
        with pytest.raises(UserError) as caught:
            if isinstance(value, str):
                service.set_jev_key(value)
            else:
                SecretSet.model_validate({"name": "jevKey", "value": value})
        assert caught.value.field == "value"
        assert caught.value.message_key == "settings.secret_invalid"
        assert MESSAGES[caught.value.message_key].format()


def test_provider_selection_failure_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    import keyring

    def fail():
        raise RuntimeError("private-provider-payload test-key-do-not-use")

    monkeypatch.setattr(keyring, "get_keyring", fail)
    with pytest.raises(InternalError) as caught:
        KeyringSecretStore()
    assert caught.value.message_key == "settings.keyring_unavailable"
    assert "private-provider-payload" not in str(caught.value.to_wire("r-c04"))


def test_sensitive_domain_error_is_not_forwarded(
    service: SecretsService, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(account: str) -> str | None:
        raise InternalError(params={"payload": "test-key-do-not-use"}, detail="private-payload")

    monkeypatch.setattr(service._store, "get", fail)
    with pytest.raises(InternalError) as caught:
        service.status()
    assert "test-key-do-not-use" not in str(caught.value.to_wire("r-c04"))
    assert "private-payload" not in str(caught.value.to_wire("r-c04"))


@pytest.mark.parametrize(
    "existing,concurrent",
    [
        ("old-test-key-do-not-use", None),
        ("old-test-key-do-not-use", "concurrent-test-key-do-not-use"),
        (None, "concurrent-test-key-do-not-use"),
    ],
)
def test_native_atomic_error_never_reads_back_restores_deletes_or_rewrites(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    existing: str | None,
    concurrent: str | None,
) -> None:
    from sentinel.platform import keyring_store

    backend = FakeBackend()
    identity = ("sentinel", "typesafe_api_key")
    backend.values.clear()
    if existing is not None:
        backend.values[identity] = existing
    calls: list[str] = []

    def read(service: str, username: str) -> str | None:
        calls.append("get")
        return backend.values.get((service, username))

    def forbidden(*args: object) -> None:
        pytest.fail("native AtomicWriteError must not compensate or mutate backend")

    def native_fail(provider, service: str, account: str, value: str) -> None:
        assert provider is backend and (service, account) == identity
        calls.append("native")
        if concurrent is not None:
            # 模拟其他写入者在 native 失败前完成更新；adapter 不得把它还原为旧值。
            backend.values[identity] = concurrent
        raise keyring_store.AtomicWriteError("private-native-payload new-test-key-do-not-use")

    store = KeyringSecretStore(backend=backend)
    monkeypatch.setattr(backend, "get_password", read)
    monkeypatch.setattr(backend, "set_password", forbidden)
    monkeypatch.setattr(backend, "delete_password", forbidden)
    monkeypatch.setattr(store, "_restore", forbidden)
    monkeypatch.setattr(keyring_store, "set_password", native_fail)
    with pytest.raises(InternalError) as caught:
        store.set("typesafe_api_key", "new-test-key-do-not-use")
    assert calls == ["get", "native"]
    assert backend.values.get(identity) == (concurrent if concurrent is not None else existing)
    assert caught.value.message_key == "settings.keyring_unavailable"
    assert caught.value.detail == "keyring:unavailable"
    assert "private-native-payload" not in str(caught.value.to_wire("r-c04"))
    assert "new-test-key-do-not-use" not in str(caught.value.to_wire("r-c04"))
    assert all(
        record.sentinel["event"] == "secrets.keyring_unavailable" for record in caplog.records
    )


def test_atomic_marker_from_delete_does_not_compensate(monkeypatch: pytest.MonkeyPatch) -> None:
    from sentinel.platform.keyring_store import AtomicWriteError

    backend = FakeBackend()
    store = KeyringSecretStore(backend=backend)

    def fail(service: str, username: str) -> None:
        raise AtomicWriteError("private-native-payload")

    def forbidden(*args: object) -> None:
        pytest.fail("AtomicWriteError must bypass restore")

    monkeypatch.setattr(backend, "delete_password", fail)
    monkeypatch.setattr(store, "_restore", forbidden)
    with pytest.raises(InternalError) as caught:
        store.delete("typesafe_api_key")
    assert backend.values[("sentinel", "typesafe_api_key")] == "old-test-key-do-not-use"
    assert caught.value.message_key == "settings.keyring_unavailable"
