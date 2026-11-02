from dataclasses import dataclass, field

import pytest


@dataclass
class FakeClock:
    value: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture(autouse=True)
def isolate_source_state(monkeypatch: pytest.MonkeyPatch) -> None:
    from sentinel.http import client

    monkeypatch.setattr(client, "_shared_sources", {})
    from sentinel.http import policy

    monkeypatch.setattr(policy, "POLICIES", dict(policy.POLICIES))
    monkeypatch.setattr(policy, "_warned", set())
