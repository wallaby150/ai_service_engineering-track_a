"""테스트 보조: 카이제곱 적합도. scipy 없이 Wilson–Hilferty 근사로 임계값을 낸다."""

from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable


def chi_square_critical(df: int, z: float = 3.09) -> float:
    """유의수준 약 0.001(z=3.09)의 카이제곱 임계값 근사."""
    k = 2 / (9 * df)
    return df * (1 - k + z * k ** 0.5) ** 3


def fits(observed: Iterable[str], expected: Dict[str, float]) -> bool:
    counts = Counter(observed)
    n = sum(counts.values())
    stat = 0.0
    for value, p in expected.items():
        if p <= 0:
            assert counts.get(value, 0) == 0, f"{value}는 확률 0인데 {counts[value]}번 나왔다"
            continue
        e = n * p
        stat += (counts.get(value, 0) - e) ** 2 / e
    df = sum(1 for p in expected.values() if p > 0) - 1
    return stat < chi_square_critical(df)
