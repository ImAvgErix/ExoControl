"""Safety rails: rate limits, kill switch, destructive-action guards."""
from __future__ import annotations
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional



# Word-ish destructive phrases. Intentionally not a sandbox — just a tripwire.
# Wipe patterns (format/shutdown/rm -rf) need explicit confirm in default/trusted.
_DESTRUCTIVE = (
    re.compile(r"\bdelete\s+all\b", re.I),
    re.compile(r"\bremove-item\b.*-(recurse|force)\b", re.I),
)
_WIPE = (
    re.compile(r"\brm\s+-rf\b", re.I),
    re.compile(r"\bformat\s+[c-z]:", re.I),
    re.compile(r"\bshutdown(\s+/s)?\b", re.I),
    re.compile(r"\bstop-computer\b", re.I),
    re.compile(r"\bdel\s+/[fs]", re.I),
)


@dataclass
class SafetyConfig:
    max_actions_per_minute: int = 90
    max_clicks_per_minute: int = 45
    min_action_interval_s: float = 0.04
    kill_switch: bool = False


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
        from exo_control.trust import human_kill_armed

        if human_kill_armed():
            self.config.kill_switch = True
            return
        self.config.kill_switch = False

    def check(
        self,
        kind: str = "action",
        text: str = "",
        confirm: bool = False,
        record: bool = True,
    ) -> tuple[bool, str]:
        """Return (allowed, reason). Destructive patterns require confirm=True."""
        from exo_control.trust import (
            human_kill_armed,
            kill_file_present,
            min_action_interval_s,
            rate_limit_multiplier,
        )
        from exo_control.policy import confirm_ok, parse_confirm

        if human_kill_armed() or self.config.kill_switch:
            self.config.kill_switch = True
            self.blocked_count += 1
            kill = kill_file_present()
            if kill is not None:
                return False, f"kill_switch armed — all actions blocked (file {kill})"
            if human_kill_armed():
                return False, "kill_switch armed — all actions blocked (EXO_KILL_SWITCH=1)"
            return False, "kill_switch armed — all actions blocked"
        low = text or ""
        explicit = parse_confirm(confirm)
        from exo_control.trust import unrestricted

        owner = unrestricted()
        for pat in _WIPE:
            if pat.search(low) and not explicit and not owner:
                self.blocked_count += 1
                return False, f"destructive pattern requires confirm=true: {pat.pattern}"
        confirmed = confirm_ok(confirm, kind="destructive")
        for pat in _DESTRUCTIVE:
            if pat.search(low) and not confirmed:
                self.blocked_count += 1
                return False, f"destructive pattern requires confirm=true: {pat.pattern}"
        now = time.time()
        interval = min_action_interval_s(self.config.min_action_interval_s)
        if interval > 0 and now - self._last < interval:
            time.sleep(interval - (now - self._last))
            now = time.time()
        cutoff = now - 60.0
        while self._times and self._times[0] < cutoff:
            self._times.popleft()
        while self._click_times and self._click_times[0] < cutoff:
            self._click_times.popleft()
        mult = rate_limit_multiplier()
        max_actions = max(1, int(self.config.max_actions_per_minute * mult))
        max_clicks = max(1, int(self.config.max_clicks_per_minute * mult))
        if len(self._times) >= max_actions:
            self.blocked_count += 1
            return False, "rate limit: max_actions_per_minute"
        if kind == "click" and len(self._click_times) >= max_clicks:
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
