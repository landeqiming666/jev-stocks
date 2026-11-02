"""文本与对象脱敏的单元测试。"""

from __future__ import annotations

from sentinel.security.redact import MASK, redact_obj, redact_text


def test_redact_text_masks_sk_and_bearer() -> None:
    value = redact_text("key sk-abcdefgh12345678 header Bearer abc.def")

    assert value == "key ***REDACTED*** header Bearer ***REDACTED***"


def test_redact_obj_masks_sensitive_keys_and_is_cycle_safe() -> None:
    source: dict[str, object] = {"apiKey": "x", "n": {"token": "y"}}
    source["self"] = source

    value = redact_obj(source)

    assert value["apiKey"] == MASK  # type: ignore[index]
    assert value["n"]["token"] == MASK  # type: ignore[index]
    assert value["self"] == "<cycle>"  # type: ignore[index]
