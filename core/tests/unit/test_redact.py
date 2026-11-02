"""文本与对象脱敏的单元测试。"""

from __future__ import annotations

from sentinel.security.redact import MASK, clear_secrets, redact_obj, redact_text, register_secret


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


def test_registered_secret_in_mapping_key_is_redacted() -> None:
    import json

    secret = "test-credential-in-a-key"
    register_secret(secret)
    try:
        redacted = redact_obj({secret: "public", "nested": {secret: "value"}})
        assert secret not in json.dumps(redacted)
    finally:
        clear_secrets()
