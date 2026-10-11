"""확률과 출생아 수를 사람이 체감하는 단위로 바꾼다. 화면·서사는 이 값을 받아 쓰기만 한다.

- one_in(p): "N명 중 1명" — 1/p를 정수로 반올림
- births_per_minute: 한 해 출생아 수 → 1분에 몇 명 (1년 = 365.25일)
- minutes_per_birth: 그 역수 — "약 N분에 1명"
"""

from __future__ import annotations

from typing import Optional

MINUTES_PER_YEAR = 365.25 * 24 * 60


def one_in(p: Optional[float]) -> Optional[int]:
    """확률 p를 'N명 중 1명'의 N으로. 확률이 없거나 0이면 None(무한대를 지어내지 않는다)."""
    if p is None or p <= 0:
        return None
    return max(1, round(1 / p))


def births_per_minute(births_per_year: Optional[int]) -> Optional[float]:
    if not births_per_year or births_per_year <= 0:
        return None
    return births_per_year / MINUTES_PER_YEAR


def minutes_per_birth(births_per_year: Optional[int]) -> Optional[float]:
    rate = births_per_minute(births_per_year)
    return None if rate is None else 1 / rate
