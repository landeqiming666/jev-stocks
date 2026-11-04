"""Platform-specific credential writes without a delete-before-add window."""

from __future__ import annotations

import sys
from typing import Protocol


class PasswordBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


class AtomicWriteError(Exception):
    """The native write failed without a delete; compensating writes are unsafe."""


def set_password(backend: PasswordBackend, service: str, account: str, value: str) -> None:
    if sys.platform == "darwin":
        from keyring.backends.macOS import Keyring

        if isinstance(backend, Keyring):
            from .macos_keychain import set_generic_password_atomic

            try:
                set_generic_password_atomic(service, account, value)
            except Exception:
                raise AtomicWriteError("native credential write failed") from None
            return
    backend.set_password(service, account, value)
