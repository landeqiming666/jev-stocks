from __future__ import annotations

import logging
import threading
from typing import Protocol

import keyring

from sentinel.errors import InternalError
from sentinel.logging_setup import get_logger, log_event
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
    def __init__(self) -> None:
        self._lock = threading.RLock()

    def get(self, account: str) -> str | None:
        try:
            return keyring.get_password(KEYRING_SERVICE, account)
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
                keyring.set_password(KEYRING_SERVICE, account, value)
            except Exception:
                # 系统 provider 可能先删后写；仅在发生变化时补偿，避免无谓地重写旧值。
                self._restore(account, previous)
                raise _unavailable() from None

    def _restore(self, account: str, previous: str | None) -> None:
        try:
            current = self.get(account)
            if current != previous:
                if previous is None:
                    keyring.delete_password(KEYRING_SERVICE, account)
                else:
                    keyring.set_password(KEYRING_SERVICE, account, previous)
        except Exception:
            log_event(
                get_logger(__name__),
                logging.ERROR,
                event="secrets.keyring_restore_failed",
                error_code="INTERNAL",
            )
            raise InternalError(detail="keyring:restore_failed") from None

    def delete(self, account: str) -> None:
        with self._lock:
            previous = self.get(account)
            if previous is None:
                return
            register_secret(previous)
            try:
                keyring.delete_password(KEYRING_SERVICE, account)
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
    return InternalError(detail="keyring:unavailable")
