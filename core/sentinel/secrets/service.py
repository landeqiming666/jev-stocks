from __future__ import annotations

import re
import threading
from collections.abc import Callable
from datetime import datetime

from sentinel.errors import UserError
from sentinel.security.redact import register_secret

from .store import KEYRING_ACCOUNT, SecretStore, _unavailable

MAX_SECRET_CHARS = 512


class SecretsService:
    def __init__(self, store: SecretStore, clock: Callable[[], datetime]) -> None:
        self._store, self._clock = store, clock
        self._lock = threading.RLock()

    def set_jev_key(self, value: str) -> None:
        if not isinstance(value, str):
            raise UserError(
                "INVALID_ARGUMENT", message_key="settings.secret_invalid", field="value"
            )
        normalized = value.strip()
        if not 1 <= len(normalized) <= MAX_SECRET_CHARS or re.search(r"\s", normalized):
            raise UserError(
                "INVALID_ARGUMENT", message_key="settings.secret_invalid", field="value"
            )
        with self._lock:
            self.get_jev_key()
            register_secret(normalized)
            try:
                self._store.set(KEYRING_ACCOUNT, normalized)
            except Exception:
                raise _unavailable() from None

    def clear_jev_key(self) -> None:
        with self._lock:
            self.get_jev_key()
            try:
                self._store.delete(KEYRING_ACCOUNT)
            except Exception:
                raise _unavailable() from None

    def status(self) -> dict[str, bool]:
        return {"jevKey": bool(self.get_jev_key())}

    def get_jev_key(self) -> str | None:
        with self._lock:
            try:
                value = self._store.get(KEYRING_ACCOUNT)
            except Exception:
                raise _unavailable() from None
            if value:
                register_secret(value)
            return value
