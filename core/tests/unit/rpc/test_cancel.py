from __future__ import annotations

import pytest

from sentinel.errors import CancelledError
from sentinel.rpc.cancel import CancelRegistry, CancelToken


def test_cancel_sets_token_and_raises_cancelled() -> None:
    token = CancelToken()
    assert not token.cancelled
    token.cancel()
    assert token.cancelled and token.is_cancelled()
    with pytest.raises(CancelledError) as raised:
        token.raise_if_cancelled()
    assert raised.value.code == "CANCELLED"


def test_registry_default_is_not_cancellable() -> None:
    registry = CancelRegistry()
    token = CancelToken()
    registry.register("r-1", token)
    assert not registry.cancel("r-1")
    assert not token.cancelled
    assert not registry.cancel("unknown")


def test_registry_rejects_duplicate_without_replacing_token() -> None:
    registry = CancelRegistry()
    first, second = CancelToken(), CancelToken()
    registry.register("r-1", first, cancellable=True)
    with pytest.raises(ValueError):
        registry.register("r-1", second)
    assert registry.cancel("r-1")
    assert first.cancelled and not second.cancelled
    registry.unregister("r-1")
    registry.unregister("r-1")
    assert not registry.cancel("r-1")
