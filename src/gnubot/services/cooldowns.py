"""Per-key cooldown helper."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class CooldownTracker:
    """Monotonic cooldown map."""

    _last: dict[str, float] = field(default_factory=dict)

    def ready(self, key: str, cooldown_seconds: float) -> bool:
        if cooldown_seconds <= 0:
            return True
        now = time.monotonic()
        last = self._last.get(key, 0.0)
        return (now - last) >= cooldown_seconds

    def touch(self, key: str) -> None:
        self._last[key] = time.monotonic()

    def remaining(self, key: str, cooldown_seconds: float) -> float:
        if cooldown_seconds <= 0:
            return 0.0
        now = time.monotonic()
        last = self._last.get(key, 0.0)
        return max(0.0, cooldown_seconds - (now - last))
