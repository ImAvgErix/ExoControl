"""Safety rails: rate limits, kill switch, dangerous-action guards."""
from __future__ import annotations
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional


@dataclass
class SafetyConfig:
    max_actions_per_minute: int = 90
    max_clicks_per_minute: int = 45
    min_action_interval_s: float = 0.04
    kill_switch: bool = False
    require_confirm_patterns: tuple = ("format", "delete all", "shutdown", "rm -rf")


class SafetyGate:
    def __init__(self, config: Optional[SafetyConfig] = None):
        self.config = config or SafetyConfig()
        self._times: Deque[float] = deque(maxlen=200)
        self._click_times: Deque[float] = deque(maxlen=200)
        self._last: float = 0.0
        self.blocked_count = 0

    def arm_kill_switch(self) -> None:
        self.config.kill_switch = True

    def disarm_kill_switch(self) -> None:
        self.config.kill_switch = False

    def check(
        self,
        kind: str = "action",
        text: str = "",
        confirm: bool = False,
        record: bool = True,
    ) -> tuple[bool, str]:
        """Return (allowed, reason). Destructive patterns require confirm=True."""
        if self.config.kill_switch:
            self.blocked_count += 1
            return False, "kill_switch armed — all actions blocked"
        low = (text or "").lower()
        for pat in self.config.require_confirm_patterns:
            if pat and pat in low and not confirm:
                self.blocked_count += 1
                return False, f"destructive pattern requires confirm=true: {pat}"
        now = time.time()
        if now - self._last < self.config.min_action_interval_s:
            time.sleep(self.config.min_action_interval_s - (now - self._last))
            now = time.time()
        cutoff = now - 60.0
        while self._times and self._times[0] < cutoff:
            self._times.popleft()
        while self._click_times and self._click_times[0] < cutoff:
            self._click_times.popleft()
        if len(self._times) >= self.config.max_actions_per_minute:
            self.blocked_count += 1
            return False, "rate limit: max_actions_per_minute"
        if kind == "click" and len(self._click_times) >= self.config.max_clicks_per_minute:
            self.blocked_count += 1
            return False, "rate limit: max_clicks_per_minute"
        if record:
            self._times.append(now)
            if kind == "click":
                self._click_times.append(now)
            self._last = now
        return True, "ok"

    def stats(self) -> dict:
        return {
            "kill_switch": self.config.kill_switch,
            "actions_last_min": len(self._times),
            "clicks_last_min": len(self._click_times),
            "blocked": self.blocked_count,
        }
