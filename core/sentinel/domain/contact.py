"""A common SEC contact-email policy that can safely form an ASCII HTTP header."""

from __future__ import annotations

import re

_ATOM = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_MAILBOX = _ATOM + r"(?:\." + _ATOM + r")*@" + _LABEL + r"(?:\." + _LABEL + r")*\.[A-Za-z]{2,63}"
CONTACT_EMAIL_PATTERN = (
    r"^(?=[\x21-\x7E]{1,120}(?![\s\S]))(?=[^@]{1,64}@)" + _MAILBOX + r"(?![\s\S])"
)
_CONTACT_EMAIL = re.compile(CONTACT_EMAIL_PATTERN)


def is_valid_sec_email(value: object) -> bool:
    return isinstance(value, str) and _CONTACT_EMAIL.fullmatch(value) is not None


def raw_contact_email_pattern() -> str:
    whitespace = (
        r"[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]"
    )
    return (
        "^"
        + whitespace
        + r"*(?:(?=[\x21-\x7E]{1,120}"
        + whitespace
        + r"*(?![\s\S]))(?=[^@]{1,64}@)"
        + _MAILBOX
        + whitespace
        + r"*)?(?![\s\S])"
    )
