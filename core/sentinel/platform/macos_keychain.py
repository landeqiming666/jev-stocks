"""Use Security.framework's atomic update, not keyring's delete/add sequence."""

from __future__ import annotations

import ctypes
from collections.abc import Mapping
from functools import lru_cache
from typing import Any, Protocol

ITEM_NOT_FOUND = -25300
DUPLICATE_ITEM = -25299


class KeychainWriteError(Exception):
    pass


class Bindings(Protocol):
    def string(self, value: str) -> int: ...
    def data(self, value: bytes) -> int: ...
    def constant(self, name: str) -> int: ...
    def dictionary(self, values: Mapping[str, int]) -> int: ...
    def update(self, query: int, attributes: int) -> int: ...
    def add(self, attributes: int) -> int: ...
    def release(self, value: int) -> None: ...


def _function(library: ctypes.CDLL, name: str, result: Any, arguments: list[Any]) -> Any:
    function = getattr(library, name)
    function.restype = result
    function.argtypes = arguments
    return function


class NativeBindings:
    def __init__(self) -> None:
        self._security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        self._cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        pointer, index = ctypes.c_void_p, ctypes.c_ssize_t
        self._string = _function(
            self._cf,
            "CFStringCreateWithCString",
            pointer,
            [pointer, ctypes.c_char_p, ctypes.c_uint32],
        )
        self._data = _function(self._cf, "CFDataCreate", pointer, [pointer, pointer, index])
        self._dictionary = _function(
            self._cf,
            "CFDictionaryCreate",
            pointer,
            [pointer, ctypes.POINTER(pointer), ctypes.POINTER(pointer), index, pointer, pointer],
        )
        self._release = _function(self._cf, "CFRelease", None, [pointer])
        self._update = _function(
            self._security, "SecItemUpdate", ctypes.c_int32, [pointer, pointer]
        )
        self._add = _function(self._security, "SecItemAdd", ctypes.c_int32, [pointer, pointer])
        self._key_callbacks = ctypes.addressof(
            ctypes.c_byte.in_dll(self._cf, "kCFTypeDictionaryKeyCallBacks")
        )
        self._value_callbacks = ctypes.addressof(
            ctypes.c_byte.in_dll(self._cf, "kCFTypeDictionaryValueCallBacks")
        )

    def string(self, value: str) -> int:
        return int(self._string(None, value.encode("utf-8"), 0x08000100) or 0)

    def data(self, value: bytes) -> int:
        buffer = ctypes.create_string_buffer(value)
        return int(self._data(None, buffer, len(value)) or 0)

    def constant(self, name: str) -> int:
        value = ctypes.c_void_p.in_dll(self._security, name).value
        if value is None:
            raise KeychainWriteError("missing Security.framework constant")
        return value

    def dictionary(self, values: Mapping[str, int]) -> int:
        pointers = ctypes.c_void_p * len(values)
        keys = pointers(*(self.constant(name) for name in values))
        data = pointers(*values.values())
        return int(
            self._dictionary(
                None, keys, data, len(values), self._key_callbacks, self._value_callbacks
            )
            or 0
        )

    def update(self, query: int, attributes: int) -> int:
        return int(self._update(query, attributes))

    def add(self, attributes: int) -> int:
        return int(self._add(attributes, None))

    def release(self, value: int) -> None:
        self._release(value)


@lru_cache(maxsize=1)
def native_bindings() -> NativeBindings:
    return NativeBindings()


def set_generic_password_atomic(
    service: str, account: str, value: str, *, bindings: Bindings | None = None
) -> None:
    api = bindings if bindings is not None else native_bindings()
    owned: list[int] = []

    def keep(reference: int) -> int:
        if not reference:
            raise KeychainWriteError("CoreFoundation allocation failed")
        owned.append(reference)
        return reference

    try:
        identity = {
            "kSecClass": api.constant("kSecClassGenericPassword"),
            "kSecAttrService": keep(api.string(service)),
            "kSecAttrAccount": keep(api.string(account)),
        }
        data = keep(api.data(value.encode("utf-8")))
        query = keep(api.dictionary(identity))
        attributes = keep(api.dictionary({"kSecValueData": data}))
        status = api.update(query, attributes)
        if status == ITEM_NOT_FOUND:
            new_item = keep(api.dictionary(identity | {"kSecValueData": data}))
            status = api.add(new_item)
            if status == DUPLICATE_ITEM:
                status = api.update(query, attributes)
        if status:
            raise KeychainWriteError(f"Security.framework write failed: {status}")
    finally:
        for reference in reversed(owned):
            api.release(reference)
