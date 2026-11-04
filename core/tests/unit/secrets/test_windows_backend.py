"""WinVault tests use only unique, disposable identities."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import traceback
from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

from sentinel.clock import parse_iso
from sentinel.logging_setup import JsonFormatter, get_logger
from sentinel.rpc import CancelToken, Dispatcher
from sentinel.rpc.dispatcher import RequestContext
from sentinel.secrets import KeyringSecretStore, SecretsService, service, store
from sentinel.secrets.windows_backend import (
    MAX_SECRET_CHARS,
    CredentialBackendError,
    CredentialBackendUnavailable,
    WindowsCredentialBackend,
)
from sentinel.settings import SettingsService, register
from sentinel.settings.models import EngineSnapshot
from sentinel.settings.repository import SettingsRepository
from sentinel.settings.service import ConnectionProbe
from sentinel.storage import Database

pytestmark = pytest.mark.windows


@pytest.fixture
def temporary_credential() -> Iterator[tuple[WindowsCredentialBackend, str]]:
    token = uuid4().hex
    backend = WindowsCredentialBackend(
        service=f"sentinel-test-{token}", account=f"sentinel-test-{token}"
    )
    try:
        yield backend, f"test-key-do-not-use-{token}"
    finally:
        backend.delete()
        assert not backend.exists()


@pytest.fixture
def broken_credential(monkeypatch: pytest.MonkeyPatch) -> tuple[WindowsCredentialBackend, str]:
    class FailingBackend:
        def set_password(self, service: str, account: str, password: str) -> None:
            raise OSError(0, f"unsafe native error included {password}", None, 1312)

    token = uuid4().hex
    backend = WindowsCredentialBackend(
        service=f"sentinel-test-{token}", account=f"sentinel-test-{token}"
    )
    monkeypatch.setattr(backend, "_backend", FailingBackend())
    return backend, f"test-key-do-not-use-{token}"


def test_winvault_is_active_backend() -> None:
    from keyring.backends.Windows import WinVaultKeyring
    from win32ctypes.pywin32 import win32cred

    active = WindowsCredentialBackend()._backend
    assert type(active) is WinVaultKeyring
    assert active.priority > 0
    assert active.persist == win32cred.CRED_PERSIST_LOCAL_MACHINE


def test_service_and_account_are_exact() -> None:
    backend = WindowsCredentialBackend()
    assert backend.service == "sentinel"
    assert backend.account == "typesafe_api_key"


def test_set_get_delete_roundtrip(
    temporary_credential: tuple[WindowsCredentialBackend, str],
) -> None:
    backend, value = temporary_credential
    value = value.ljust(MAX_SECRET_CHARS, "x")
    backend.set(value)
    if backend.get() != value:
        pytest.fail("WinVault did not preserve the 512-character fixture")
    replacement = f"{value[:-1]}y"
    backend.set(replacement)
    if backend.get() != replacement:
        pytest.fail("WinVault did not replace the fixture")
    backend.delete()
    assert backend.get() is None


def test_secret_survives_new_process(
    temporary_credential: tuple[WindowsCredentialBackend, str],
) -> None:
    backend, value = temporary_credential
    backend.set(value)
    core = Path(__file__).resolve().parents[3]
    pythonpath = os.pathsep.join(filter(None, (str(core), os.environ.get("PYTHONPATH"))))
    script = (
        "import os, sys\n"
        "from sentinel.secrets.windows_backend import WindowsCredentialBackend\n"
        "backend = WindowsCredentialBackend(service=os.environ['W04_TEST_SERVICE'],\n"
        "                                   account=os.environ['W04_TEST_ACCOUNT'])\n"
        "sys.exit(0 if backend.get() == os.environ['W04_TEST_VALUE'] else 1)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={
            **os.environ,
            "PYTHONPATH": pythonpath,
            "W04_TEST_SERVICE": backend.service,
            "W04_TEST_ACCOUNT": backend.account,
            "W04_TEST_VALUE": value,
        },
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == result.stderr == b""


def test_delete_removes_credential(
    temporary_credential: tuple[WindowsCredentialBackend, str],
) -> None:
    backend, value = temporary_credential
    backend.set(value)
    assert backend.exists()
    backend.delete()
    backend.delete()
    assert not backend.exists()


def test_probe_reports_all_steps_true(
    temporary_credential: tuple[WindowsCredentialBackend, str],
) -> None:
    backend, value = temporary_credential
    backend.set(value)
    result = backend.probe()
    assert result.backend == "Windows Credential Locker"
    assert result.write_ok and result.read_ok and result.delete_ok
    assert result.service.startswith("sentinel-test-") and result.service != backend.service
    assert result.account.startswith("sentinel-test-") and result.account != backend.account
    probe = WindowsCredentialBackend(service=result.service, account=result.account)
    try:
        assert not probe.exists()
        if backend.get() != value:
            pytest.fail("The probe altered the calling backend's credential")
    finally:
        probe.delete()


def test_error_message_never_contains_secret(
    broken_credential: tuple[WindowsCredentialBackend, str],
) -> None:
    backend, value = broken_credential
    with pytest.raises(CredentialBackendError) as caught:
        backend.set(value)
    error = caught.value
    assert error.__context__ is None
    assert error.__cause__ is None
    assert "OSError" in str(error) and "1312" in str(error)
    formatted = "".join(traceback.format_exception(error))
    if value in str(error) or value in repr(error) or value in formatted:
        pytest.fail("The adapter exposed a fake credential in its exception")


def test_no_secret_in_logs_or_database(
    temporary_credential: tuple[WindowsCredentialBackend, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend, value = temporary_credential
    failed_value = f"test-key-do-not-use-{uuid4().hex}"
    # C-04 uses a fixed identity. Redirect both constants before any RPC reads.
    monkeypatch.setattr(store, "KEYRING_SERVICE", backend.service)
    monkeypatch.setattr(service, "KEYRING_ACCOUNT", backend.account)
    database_path = tmp_path / "sentinel.duckdb"
    log_path = tmp_path / "core.jsonl"
    database = Database(database_path)
    now = parse_iso("2026-11-04T00:00:00Z")
    dispatcher = Dispatcher()
    probe = Mock(spec=ConnectionProbe)
    responses: list[dict[str, object]] = []

    def call(method: str, params: dict[str, str]) -> dict[str, object]:
        result = dispatcher.dispatch(
            dispatcher.lookup(method), params, RequestContext("r-w04", method, CancelToken(), now)
        )
        responses.append(result)
        return result

    def fail_write(service: str, account: str, password: str) -> None:
        raise OSError(0, f"unsafe native error included {password}", None, 1312)

    with ExitStack() as cleanup:
        database.open()
        cleanup.callback(database.close)
        database.migrate()
        logger = get_logger("sentinel")
        handler = logging.FileHandler(log_path, encoding="utf-8")
        cleanup.callback(handler.close)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        cleanup.callback(logger.removeHandler, handler)

        secrets = SecretsService(KeyringSecretStore(backend=backend), lambda: now)
        settings = SettingsService(SettingsRepository(database), lambda: now)
        register(
            dispatcher,
            settings,
            secrets,
            database,
            "windows",
            EngineSnapshot("auto", None, False),
            probe,
        )
        assert call("secrets.status", {})["result"] == {"jevKey": False}
        assert call("secrets.set", {"name": "jevKey", "value": value})["result"] == {"ok": True}
        assert call("secrets.status", {})["result"] == {"jevKey": True}
        if backend.get() != value:
            pytest.fail("The RPC did not write the fake credential to WinVault")
        with monkeypatch.context() as patch:
            patch.setattr(backend._backend, "set_password", fail_write)
            failure = call("secrets.set", {"name": "jevKey", "value": failed_value})
            assert failure["error"]["code"] == "INTERNAL"
        if backend.get() != value:
            pytest.fail("The failed RPC write changed the stored credential")
        assert call("secrets.clear", {"name": "jevKey"})["result"] == {"ok": True}
        assert call("secrets.status", {})["result"] == {"jevKey": False}
        assert not backend.exists()
        assert not probe.mock_calls

    log = log_path.read_text(encoding="utf-8")
    assert "secrets.keyring_unavailable" in log
    wire = json.dumps(responses, ensure_ascii=False)
    database_bytes = database_path.read_bytes()
    for secret in (value, failed_value):
        if secret in log or secret in wire:
            pytest.fail("A fake credential leaked into C-04 RPC output or logs")
        if any(secret.encode(encoding) in database_bytes for encoding in ("utf-8", "utf-16-le")):
            pytest.fail("A fake credential leaked into the C-04 database")


@pytest.mark.parametrize("value", ["", "x" * (MAX_SECRET_CHARS + 1), "x\ry", "x\ny"])
def test_invalid_values_are_rejected_before_backend_call(
    broken_credential: tuple[WindowsCredentialBackend, str],
    value: str,
) -> None:
    backend, _ = broken_credential
    with pytest.raises(ValueError):
        backend.set(value)


def test_rejects_non_winvault_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    import keyring.backends.Windows

    class MemoryBackend:
        priority = 100

    monkeypatch.setattr(keyring.backends.Windows, "WinVaultKeyring", MemoryBackend)
    with pytest.raises(CredentialBackendUnavailable, match="WinVault backend is unavailable"):
        WindowsCredentialBackend()


def test_c04_adapter_rejects_unconfigured_identity(
    broken_credential: tuple[WindowsCredentialBackend, str],
) -> None:
    backend, value = broken_credential
    with pytest.raises(CredentialBackendError, match="identity does not match"):
        backend.set_password(backend.service + "-other", backend.account, value)
    with pytest.raises(CredentialBackendError, match="identity does not match"):
        backend.get_password(backend.service, backend.account + "-other")
    with pytest.raises(CredentialBackendError, match="identity does not match"):
        backend.delete_password(backend.service, backend.account + "-other")
