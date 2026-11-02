from __future__ import annotations

import logging
import threading
from typing import Protocol

import keyring

from sentinel.errors import InternalError
from sentinel.logging_setup import get_logger, log_event
from sentinel.platform import keyring_store
from sentinel.platform.keyring_store import AtomicWriteError, PasswordBackend
from sentinel.security.redact import register_secret

KEYRING_SERVICE = "sentinel"
KEYRING_ACCOUNT = "typesafe_api_key"


class SecretStore(Protocol):
    def get(self, account: str) -> str | None: ...
    def set(self, account: str, value: str) -> None: ...
    def delete(self, account: str) -> None: ...


class MemorySecretStore:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._lock = threading.RLock()

    def get(self, account: str) -> str | None:
        with self._lock:
            return self._values.get(account)

    def set(self, account: str, value: str) -> None:
        with self._lock:
            self._values[account] = value

    def delete(self, account: str) -> None:
        with self._lock:
            self._values.pop(account, None)


class KeyringSecretStore:
    def __init__(self, *, backend: PasswordBackend | None = None) -> None:
        try:
            self._backend = backend if backend is not None else keyring.get_keyring()
        except Exception:
            raise _unavailable() from None
        self._lock = threading.RLock()

    def get(self, account: str) -> str | None:
        try:
            return self._backend.get_password(KEYRING_SERVICE, account)
        except Exception:
            raise _unavailable() from None

    def set(self, account: str, value: str) -> None:
        with self._lock:
            previous = self.get(account)
            if previous:
                register_secret(previous)
            if previous == value:
                return
            try:
                keyring_store.set_password(self._backend, KEYRING_SERVICE, account, value)
            except AtomicWriteError:
                # native 没有删旧值；补偿会覆盖并发更新或制造新的不安全写入。
                raise _unavailable() from None
            except Exception:
                # 仅 generic backend 可能先删后写，比较实际变化后再补偿。
                self._restore(account, previous)
                raise _unavailable() from None

    def _restore(self, account: str, previous: str | None) -> None:
        try:
            current = self.get(account)
            if current != previous:
                if previous is None:
                    self._backend.delete_password(KEYRING_SERVICE, account)
                else:
                    keyring_store.set_password(self._backend, KEYRING_SERVICE, account, previous)
        except Exception:
            log_event(
                get_logger(__name__),
                logging.ERROR,
                event="secrets.keyring_restore_failed",
                error_code="INTERNAL",
            )
            raise InternalError(
                message_key="settings.keyring_unavailable", detail="keyring:restore_failed"
            ) from None

    def delete(self, account: str) -> None:
        with self._lock:
            previous = self.get(account)
            if previous is None:
                return
            register_secret(previous)
            try:
                self._backend.delete_password(KEYRING_SERVICE, account)
            except AtomicWriteError:
                raise _unavailable() from None
            except Exception:
                self._restore(account, previous)
                raise _unavailable() from None


def _unavailable() -> InternalError:
    log_event(
        get_logger(__name__),
        logging.ERROR,
        event="secrets.keyring_unavailable",
        error_code="INTERNAL",
    )
    return InternalError(message_key="settings.keyring_unavailable", detail="keyring:unavailable")
