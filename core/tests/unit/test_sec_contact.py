import json
import subprocess

import pytest

from sentinel.domain.contact import (
    CONTACT_EMAIL_PATTERN,
    is_valid_sec_email,
    raw_contact_email_pattern,
)


def email(length: int) -> str:
    return "a" * 64 + "@" + "b" * (length - 69) + ".com"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("name@example.com", True),
        ("first.last+research@sub.example.co", True),
        (email(120), True),
        (email(121), False),
        ("a" * 65 + "@example.com", False),
        ("a@example..com", False),
        ("a..b@example.com", False),
        ("a@-example.com", False),
        ("a@example-.com", False),
        ("a@example.c", False),
        ("a@" + "b" * 64 + ".com", False),
        ("a\x00@example.com", False),
        ("a\x7f@example.com", False),
        ("\u96ea@example.com", False),
        ("a\u001cb@example.com", False),
        (" a@example.com ", False),
        ("a@example.com\n", False),
        ("", False),
        (None, False),
        (True, False),
    ],
)
def test_canonical_sec_email_is_header_safe(value: object, expected: bool) -> None:
    assert is_valid_sec_email(value) is expected
    if expected:
        assert isinstance(value, str)
        value.encode("ascii")


def test_raw_pattern_matches_python_strip_and_node() -> None:
    import re

    values = [
        email(120),
        email(121),
        "name@example.com",
        "a..b@example.com",
        "\u96ea@example.com",
        "",
    ]
    cases = []
    pattern = raw_contact_email_pattern()
    for whitespace in ["", " ", "\u001c", "\u0085", "\u3000", "\n" * 1000]:
        for value in values:
            raw = whitespace + value + whitespace
            expected = not raw.strip() or is_valid_sec_email(raw.strip())
            assert (re.fullmatch(pattern, raw) is not None) is expected
            cases.append({"pattern": pattern, "value": raw, "expected": expected})
    result = subprocess.run(
        [
            "node",
            "-e",
            "const fs=require('fs');"
            "const c=JSON.parse(fs.readFileSync(0,'utf8'));"
            "console.log(JSON.stringify(c.map(x=>new RegExp(x.pattern,'u').test(x.value))));",
        ],
        input=json.dumps(cases),
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout) == [case["expected"] for case in cases]


def test_contract_email_patterns_match_shared_policy() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    types = json.loads((root / "contracts/types.schema.json").read_text())
    assert (
        types["$defs"]["Settings"]["properties"]["secContactEmail"]["anyOf"][0]["pattern"]
        == CONTACT_EMAIL_PATTERN
    )
    method = json.loads((root / "contracts/methods/settings.update.json").read_text())
    assert (
        method["params"]["properties"]["secContactEmail"]["anyOf"][0]["pattern"]
        == raw_contact_email_pattern()
    )
