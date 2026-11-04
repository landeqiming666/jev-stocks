"""Canonical ticker identity and punctuation-free search keys."""

import re
import unicodedata

from sentinel.errors import UserError

DEFAULT_LIMIT = 20
MAX_LIMIT = 50
_SYMBOL = re.compile(r"[A-Z0-9]+(?:\.[A-Z0-9]+)*", re.ASCII)


def normalize_symbol(raw: str) -> str | None:
    if not isinstance(raw, str):
        return None
    symbol = raw.strip().upper().replace("-", ".")
    return symbol if _SYMBOL.fullmatch(symbol) else None


def norm_query(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKC", value).lower() if char.isalnum())


def validate_search(query: str, limit: int) -> str:
    if not isinstance(query, str) or not 1 <= len(query) <= 64:
        raise UserError("INVALID_ARGUMENT", field="query")
    normalized = norm_query(query)
    if not normalized:
        raise UserError("INVALID_ARGUMENT", field="query")
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise UserError("INVALID_ARGUMENT", field="limit")
    return normalized
