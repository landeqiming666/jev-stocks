"""ULID 与确定性段落 ID 的单元测试。"""

from __future__ import annotations

import pytest

from sentinel.ids import is_ulid, new_id, passage_id, ulid_to_timestamp_ms


def test_new_id_with_fixed_entropy_returns_expected_ulid() -> None:
    value = new_id(timestamp_ms=1_700_000_000_000, entropy=b"\x00" * 10)

    assert value == "01HF7YAT000000000000000000"


def test_new_id_round_trips_timestamp() -> None:
    value = new_id(timestamp_ms=1_700_000_000_000, entropy=b"\x00" * 10)

    assert ulid_to_timestamp_ms(value) == 1_700_000_000_000
    assert len(value) == 26
    assert is_ulid(value)
    assert not is_ulid(value[:-1])
    assert not is_ulid("8" + value[1:])
    assert not is_ulid("01HF7YAT00000000000000000I")
    with pytest.raises(ValueError):
        ulid_to_timestamp_ms(value[:-1])


def test_ulid_rejects_out_of_range_timestamp() -> None:
    with pytest.raises(ValueError):
        new_id(timestamp_ms=281_474_976_710_656, entropy=b"\x00" * 10)
    with pytest.raises(ValueError):
        new_id(timestamp_ms=-1, entropy=b"\x00" * 10)
    with pytest.raises(ValueError):
        new_id(timestamp_ms=0, entropy=b"\x00" * 9)


def test_passage_id_is_stable_and_32_hex() -> None:
    value = passage_id("us:0001234567-26-000123", 1, 0, 120)

    assert value == "e4d8d292502f3875926ca657013c0720"
    assert len(value) == 32
    assert all(char in "0123456789abcdef" for char in value)
    assert value == passage_id("us:0001234567-26-000123", 1, 0, 120)
    with pytest.raises(ValueError):
        passage_id("us:0001234567-26-000123", -1, 0, 120)
    with pytest.raises(ValueError):
        passage_id("us:0001234567-26-000123", 1, 120, 120)
