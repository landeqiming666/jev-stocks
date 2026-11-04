"""Persistent Windows Credential Locker adapter for one service and account."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast
from uuid import uuid4

if TYPE_CHECKING:
    from keyring.backend import KeyringBackend

SERVICE = "sentinel"
ACCOUNT = "typesafe_api_key"
MAX_SECRET_CHARS = 512


class CredentialBackendUnavailable(RuntimeError):
    """WinVault cannot be initialized."""


class CredentialBackendError(RuntimeError):
    """A credential operation failed without retaining the original exception."""


@dataclass(frozen=True)
class CredentialProbeResult:
    backend: str
    service: str
    account: str
    write_ok: bool
    read_ok: bool
    delete_ok: bool


def _operation_error(operation: str, error: Exception) -> CredentialBackendError:
    code = getattr(error, "winerror", None)
    detail = type(error).__name__
    if isinstance(code, int):
        detail += f", Win32 error {code}"
    return CredentialBackendError(f"WinVault {operation} failed ({detail})")


class WindowsCredentialBackend:
    SERVICE = SERVICE
    ACCOUNT = ACCOUNT

    def __init__(self, *, service: str = SERVICE, account: str = ACCOUNT) -> None:
        if not service or not account:
            raise ValueError("Credential service and account must be nonempty")
        self.service = service
        self.account = account
        try:
            from keyring.backends.Windows import WinVaultKeyring

            backend = cast(Callable[[], WinVaultKeyring], WinVaultKeyring)()
            if type(backend).__name__ != "WinVaultKeyring" or backend.priority <= 0:
                raise RuntimeError("WinVault is not active")
            backend.persist = "local machine"
        except Exception:
            pass
        else:
            self._backend: KeyringBackend = backend
            return
        raise CredentialBackendUnavailable("WinVault backend is unavailable")

    def set(self, value: str) -> None:
        if not isinstance(value, str) or not 1 <= len(value) <= MAX_SECRET_CHARS:
            del value
            raise ValueError(f"Credential must contain 1–{MAX_SECRET_CHARS} characters")
        if "\r" in value or "\n" in value:
            del value
            raise ValueError("Credential cannot contain line breaks")
        try:
            self._backend.set_password(self.service, self.account, value)
        except Exception as error:
            failure = _operation_error("write", error)
        else:
            return
        # Raise after leaving the handler so the native traceback is not retained.
        del value
        raise failure

    def get(self) -> str | None:
        try:
            value: object = self._backend.get_password(self.service, self.account)
        except Exception as error:
            failure = _operation_error("read", error)
        else:
            if value is None or isinstance(value, str):
                return value
            del value
            self.delete()
            raise CredentialBackendError("WinVault returned a non-string credential")
        raise failure

    def delete(self) -> None:
        from keyring.errors import PasswordDeleteError

        try:
            self._backend.delete_password(self.service, self.account)
        except PasswordDeleteError:
            # The WinVault implementation uses this error for a missing entry.
            return
        except Exception as error:
            failure = _operation_error("delete", error)
        else:
            return
        raise failure

    def exists(self) -> bool:
        return self.get() is not None

    def _check_identity(self, service: str, username: str) -> None:
        if (service, username) != (self.service, self.account):
            raise CredentialBackendError("WinVault credential identity does not match")

    def set_password(self, service: str, username: str, password: str) -> None:
        try:
            self._check_identity(service, username)
            self.set(password)
        finally:
            del password

    def get_password(self, service: str, username: str) -> str | None:
        self._check_identity(service, username)
        return self.get()

    def delete_password(self, service: str, username: str) -> None:
        self._check_identity(service, username)
        self.delete()

    def probe(self) -> CredentialProbeResult:
        token = uuid4().hex
        # WinVault may replace another account under the same service on write.
        service = account = f"sentinel-test-{token}"
        probe = WindowsCredentialBackend(service=service, account=account)
        try:
            probe.set(f"test-key-do-not-use-{token}")
            read_ok = probe.get() == f"test-key-do-not-use-{token}"
            probe.delete()
            return CredentialProbeResult(
                backend="Windows Credential Locker",
                service=service,
                account=account,
                write_ok=True,
                read_ok=read_ok,
                delete_ok=probe.get() is None,
            )
        finally:
            probe.delete()
