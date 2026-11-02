import logging

import pytest

from sentinel.clock import parse_iso
from sentinel.errors import InternalError, UserError
from sentinel.logging_setup import JsonFormatter
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


@pytest.mark.parametrize("operation", ["get", "set", "delete"])
def test_keyring_errors_are_safe_and_preserve_old_key(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    import keyring

    values = {("sentinel", "typesafe_api_key"): "old-test-key-do-not-use"}
    monkeypatch.setattr(keyring, "get_password", lambda s, a: values.get((s, a)))
    monkeypatch.setattr(keyring, "set_password", lambda s, a, v: values.update({(s, a): v}))
    monkeypatch.setattr(keyring, "delete_password", lambda s, a: values.pop((s, a), None))

    def fail(*args: object) -> None:
        raise RuntimeError("private-provider-payload old-test-key-do-not-use")

    monkeypatch.setattr(keyring, operation + "_password", fail)
    service = SecretsService(KeyringSecretStore(), lambda: parse_iso("2026-11-02T00:35:00Z"))
    with pytest.raises(InternalError) as caught:
        {
            "get": service.status,
            "set": lambda: service.set_jev_key("new-test-key-do-not-use"),
            "delete": service.clear_jev_key,
        }[operation]()
    assert "private-provider-payload" not in str(caught.value.to_wire("r-c04"))
    assert values[("sentinel", "typesafe_api_key")] == "old-test-key-do-not-use"


def test_provider_failure_after_delete_restores_old_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import keyring

    values = {("sentinel", "typesafe_api_key"): "old-test-key-do-not-use"}
    monkeypatch.setattr(keyring, "get_password", lambda s, a: values.get((s, a)))

    def set_password(s: str, a: str, v: str) -> None:
        values.pop((s, a), None)
        if v == "new-test-key-do-not-use":
            raise RuntimeError("private-provider-payload")
        values[(s, a)] = v

    monkeypatch.setattr(keyring, "set_password", set_password)
    service = SecretsService(KeyringSecretStore(), lambda: parse_iso("2026-11-02T00:35:00Z"))
    with pytest.raises(InternalError):
        service.set_jev_key("new-test-key-do-not-use")
    assert service.get_jev_key() == "old-test-key-do-not-use"


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
