from dataclasses import dataclass

from .base import validate_count

CHARS_PER_TOKEN = 3.5
ESTIMATE_MARGIN = 1.2
DEFAULT_DAILY_BUDGET = 2_000_000


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    reserved: int
    remaining: int


def estimate_tokens(chars: int) -> int:
    validate_count(chars)
    return (chars * 2 + 6) // 7


def reserve_tokens(raw_tokens: int) -> int:
    validate_count(raw_tokens)
    return (raw_tokens * 6 + 4) // 5


def check_budget(used_today: int, raw_tokens: int, limit_tokens: int) -> BudgetDecision:
    validate_count(used_today)
    validate_count(limit_tokens)
    reserved = reserve_tokens(raw_tokens)
    return BudgetDecision(
        used_today + reserved <= limit_tokens, reserved, max(limit_tokens - used_today, 0)
    )
