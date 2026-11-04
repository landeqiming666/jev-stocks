import ctypes
import sys
from collections.abc import Mapping

import pytest

from sentinel.platform.macos_keychain import (
    DUPLICATE_ITEM,
    ITEM_NOT_FOUND,
    KeychainWriteError,
    NativeBindings,
    set_generic_password_atomic,
)


class FakeBindings:
    def __init__(self, updates: list[int], additions: list[int] | None = None) -> None:
        self.updates, self.additions = list(updates), list(additions or [])
        self.objects: dict[int, object] = {1: "generic-password-class"}
        self.created: list[int] = []
        self.released: list[int] = []
        self.calls: list[str] = []
        self.current = b"test-old-value"
        self.allocation_fails = False
        self.fail_after: int | None = None

    def allocate(self, value: object) -> int:
        if self.allocation_fails or self.fail_after == len(self.created):
            return 0
        ref = len(self.objects) + 1
        self.objects[ref] = value
        self.created.append(ref)
        return ref

    def string(self, value: str) -> int:
        return self.allocate(value)

    def data(self, value: bytes) -> int:
        return self.allocate(value)

    def constant(self, name: str) -> int:
        assert name == "kSecClassGenericPassword"
        return 1

    def dictionary(self, values: Mapping[str, int]) -> int:
        return self.allocate({name: self.objects[ref] for name, ref in values.items()})

    def update(self, query: int, attributes: int) -> int:
        identity = self.objects[query]
        assert identity == {
            "kSecClass": "generic-password-class",
            "kSecAttrService": "test-service",
            "kSecAttrAccount": "test-account",
        }
        self.calls.append("update")
        status = self.updates.pop(0)
        if status == 0:
            assert isinstance(self.objects[attributes], dict)
            self.current = self.objects[attributes]["kSecValueData"]
        return status

    def add(self, attributes: int) -> int:
        self.calls.append("add")
        status = self.additions.pop(0)
        if status == 0:
            assert isinstance(self.objects[attributes], dict)
            self.current = self.objects[attributes]["kSecValueData"]
        return status

    def release(self, value: int) -> None:
        self.released.append(value)


@pytest.mark.parametrize(
    "updates,additions,calls",
    [
        ([0], [], ["update"]),
        ([ITEM_NOT_FOUND], [0], ["update", "add"]),
        ([ITEM_NOT_FOUND, 0], [DUPLICATE_ITEM], ["update", "add", "update"]),
    ],
)
def test_update_or_add_is_atomic_and_releases_cf_objects(
    updates: list[int], additions: list[int], calls: list[str]
) -> None:
    api = FakeBindings(updates, additions)
    value = "test-\u96ea-\x00-value"
    set_generic_password_atomic("test-service", "test-account", value, bindings=api)
    assert api.current == value.encode("utf-8")
    assert api.calls == calls
    assert api.released == list(reversed(api.created))


@pytest.mark.parametrize(
    "updates,additions",
    [([-128], []), ([ITEM_NOT_FOUND], [-128]), ([ITEM_NOT_FOUND, -128], [DUPLICATE_ITEM])],
)
def test_failure_never_deletes_existing_value_or_leaks_it(
    updates: list[int], additions: list[int]
) -> None:
    api = FakeBindings(updates, additions)
    with pytest.raises(KeychainWriteError) as error:
        set_generic_password_atomic("test-service", "test-account", "test-new-value", bindings=api)
    assert api.current == b"test-old-value"
    assert "test-old-value" not in str(error.value)
    assert "test-new-value" not in str(error.value)
    assert api.released == list(reversed(api.created))


def test_allocation_failure_does_not_call_security_api() -> None:
    api = FakeBindings([0])
    api.allocation_fails = True
    with pytest.raises(KeychainWriteError):
        set_generic_password_atomic("test-service", "test-account", "test-new-value", bindings=api)
    assert not api.calls
    assert not api.released


@pytest.mark.parametrize("fail_after", [1, 2, 3, 4])
def test_partial_allocation_failure_releases_every_owned_reference(fail_after: int) -> None:
    api = FakeBindings([0])
    api.fail_after = fail_after
    with pytest.raises(KeychainWriteError):
        set_generic_password_atomic("test-service", "test-account", "test-new-value", bindings=api)
    assert not api.calls
    assert api.released == list(reversed(api.created))


def test_non_utf8_password_fails_before_security_call_and_releases_identity() -> None:
    api = FakeBindings([0])
    with pytest.raises(UnicodeEncodeError):
        set_generic_password_atomic("test-service", "test-account", "\ud800", bindings=api)
    assert not api.calls
    assert api.released == list(reversed(api.created))


@pytest.mark.skipif(
    sys.platform != "darwin", reason="requires CoreFoundation, not a keychain write"
)
def test_native_bindings_build_cfdata_and_queries_without_accessing_keychain() -> None:
    api = NativeBindings()
    service = api.string("test-service")
    data = api.data(b"test-\x00-value")
    query = api.dictionary({"kSecAttrService": service, "kSecValueData": data})
    try:
        cf = api._cf
        cf.CFDataGetLength.argtypes = [ctypes.c_void_p]
        cf.CFDataGetLength.restype = ctypes.c_ssize_t
        assert cf.CFDataGetLength(data) == len(b"test-\x00-value")
        cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cf.CFDictionaryGetValue.restype = ctypes.c_void_p
        assert cf.CFDictionaryGetValue(query, api.constant("kSecValueData")) == data
    finally:
        for reference in (query, data, service):
            api.release(reference)
