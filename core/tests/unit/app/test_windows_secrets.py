from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from sentinel.app import container as composition
from sentinel.app.args import AppArgs
from sentinel.errors import InternalError
from sentinel.secrets import KeyringSecretStore, MemorySecretStore, SecretsService
from sentinel.secrets.store import KEYRING_ACCOUNT, KEYRING_SERVICE
from sentinel.secrets.windows_backend import CredentialBackendUnavailable

NOW = datetime(2026, 11, 17, tzinfo=UTC)
FAKE_KEY = "test-key-do-not-use-composition"


def test_windows_composition_selects_the_explicit_winvault_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(composition.platform, "name", lambda: "windows")
    backend = Mock()
    backend.get_password.return_value = None
    constructor = Mock(return_value=backend)
    monkeypatch.setattr("sentinel.secrets.windows_backend.WindowsCredentialBackend", constructor)
    generic_selection = Mock(side_effect=AssertionError("generic backend must not be selected"))
    monkeypatch.setattr("keyring.get_keyring", generic_selection)

    store = composition._secret_store()
    assert isinstance(store, KeyringSecretStore)
    assert store.get(KEYRING_ACCOUNT) is None
    store.set(KEYRING_ACCOUNT, FAKE_KEY)

    constructor.assert_called_once_with()
    generic_selection.assert_not_called()
    backend.get_password.assert_called_with(KEYRING_SERVICE, KEYRING_ACCOUNT)
    backend.set_password.assert_called_once_with(KEYRING_SERVICE, KEYRING_ACCOUNT, FAKE_KEY)


def test_unavailable_winvault_keeps_bootstrap_unconfigured_and_refuses_saves(
    args: AppArgs, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(composition.platform, "name", lambda: "windows")
    monkeypatch.setattr(
        "sentinel.secrets.windows_backend.WindowsCredentialBackend",
        Mock(side_effect=CredentialBackendUnavailable("test backend unavailable")),
    )
    caplog.set_level(logging.WARNING)

    built = composition.build_container(args)
    try:
        assert built.platform_name == "windows"
        snapshot = built.engine.snapshot()
        bootstrap = built.settings.bootstrap(snapshot, built.secrets, built.db, "windows", True)
        assert bootstrap.configured.jev_key is False
        assert built.secrets.status() == {"jevKey": False}
        with pytest.raises(InternalError) as save:
            built.secrets.set_jev_key(FAKE_KEY)
        assert save.value.message_key == "settings.keyring_unavailable"
        assert built.secrets.status() == {"jevKey": False}
        with pytest.raises(InternalError) as clear:
            built.secrets.clear_jev_key()
        assert clear.value.message_key == "settings.keyring_unavailable"
        assert FAKE_KEY not in caplog.text
        assert "MEMORY_STORE" not in caplog.text
    finally:
        built.close()

    restarted = SecretsService(composition._secret_store(), lambda: NOW)
    assert restarted.status() == {"jevKey": False}
    with pytest.raises(InternalError):
        restarted.set_jev_key(FAKE_KEY)


def test_nonwindows_composition_preserves_the_existing_keyring_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(composition.platform, "name", lambda: "macos")
    monkeypatch.setattr(composition, "KeyringSecretStore", Mock(side_effect=RuntimeError))
    windows_constructor = Mock(side_effect=AssertionError("Windows backend must not be selected"))
    monkeypatch.setattr(
        "sentinel.secrets.windows_backend.WindowsCredentialBackend", windows_constructor
    )

    store = composition._secret_store()
    assert isinstance(store, MemorySecretStore)
    store.set(KEYRING_ACCOUNT, FAKE_KEY)
    assert store.get(KEYRING_ACCOUNT) == FAKE_KEY
    windows_constructor.assert_not_called()
