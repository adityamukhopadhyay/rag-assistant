"""In-process limiter: per-IP sliding window per minute + a global daily budget. Single-instance, which is what runs."""
from __future__ import annotations
import time
from collections import deque
from rag.config import settings

class Limiter:
    def __init__(self):
        self.per_ip: dict[str, deque] = {}
        self.day: deque = deque()
        self.per_user: dict[str, deque] = {}     # uncached questions per visitor, 24 h window

    def _user_q(self, uid: str) -> deque:
        q = self.per_user.setdefault(uid, deque()); now = time.time()
        while q and now - q[0] > 86400:
            q.popleft()
        return q

    def remaining(self, uid: str, ip: str | None = None) -> int | None:
        if settings.rate_limit_per_user <= 0:
            return None                            # unlimited
        r = max(0, settings.rate_limit_per_user - len(self._user_q(uid)))
        if ip:                                     # client ids are self-issued: the IP caps at 4× the per-user limit
            r = min(r, max(0, settings.rate_limit_per_user * 4 - len(self._user_q("ip:" + ip))))
        return r

    def consume(self, uid: str, ip: str | None = None) -> None:
        if settings.rate_limit_per_user > 0:
            self._user_q(uid).append(time.time())
            if ip: self._user_q("ip:" + ip).append(time.time())

    def check(self, ip: str) -> tuple[bool, str]:
        now = time.time()
        while self.day and now - self.day[0] > 86400:
            self.day.popleft()
        if len(self.day) >= settings.rate_limit_per_day:
            return False, "daily request budget exhausted — please try again tomorrow"
        q = self.per_ip.setdefault(ip, deque())
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= settings.rate_limit_per_min:
            return False, "too many requests — slow down for a minute"
        q.append(now); self.day.append(now)
        if len(self.per_ip) > 5000:   # bound memory on a long-running process
            for k in [k for k, v in self.per_ip.items() if not v or now - v[-1] > 600][:2500]:
                self.per_ip.pop(k, None)
        return True, ""

    def snapshot(self) -> dict:
        return {"requests_today": len(self.day), "daily_budget": settings.rate_limit_per_day,
                "active_ips": len(self.per_ip), "per_min": settings.rate_limit_per_min,
                "per_user": settings.rate_limit_per_user, "users_today": len(self.per_user)}

limiter = Limiter()
