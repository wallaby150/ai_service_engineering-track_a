"""출생 코호트 안에서의 위치 한 줄. 무엇을 요약할지 고르는 규칙과, 그 위치의 비율을 코드로 낸다.

"이 나라에서 태어나는 아이 중 N%는 나보다 낮은 구간, N%는 같은 구간, N%는 높은 구간"처럼 말한다.
기준은 출생 연도별 코호트가 아니라 스냅샷의 기준 연도 통계다 — 그래서 '같은 해'라고 말하지 않는다.

요약 규칙(choose_headline) — 한 사람의 삶에서 가장 무게가 큰 사실을 고른다:
1. 첫돌 또는 다섯 살을 맞지 못했다 → 생존
2. 가정의 경제 수준 통계가 있다      → 경제
3. 생존 통계가 있다                → 생존
4. 둘 다 없다                      → 요약하지 않는다(None)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from core.model import ECONOMIES, SURVIVALS

# 낮은 쪽(더 불리한 쪽)부터의 순서
ORDER = {"economy": ECONOMIES, "survival": SURVIVALS}


@dataclass(frozen=True)
class Share:
    """한 모집단에서 나보다 불리한 쪽 / 나와 같은 / 유리한 쪽의 비율(합 1)."""

    below: float
    same: float
    above: float


@dataclass(frozen=True)
class Headline:
    node: str  # "economy" | "survival"
    value: str
    country: Share  # 이 나라에서 태어나는 아이(생존이면 같은 성별) 중
    world: Optional[Share]  # 통계가 있는 나라의 출생아 전체 중
    world_coverage: float  # 세계 비율이 대상으로 삼은 출생아의 비율
    year: Optional[str]  # 이 나라 값의 기준 연도


def choose_headline(survival: Optional[str], economy: Optional[str]) -> Optional[str]:
    """위치 한 줄로 무엇을 말할지. 규칙은 모듈 설명 참고."""
    if survival in ("infant_death", "child_death"):
        return "survival"
    if economy is not None:
        return "economy"
    if survival is not None:
        return "survival"
    return None


def share_of(node: str, probs: Sequence[Tuple[str, float]], value: str) -> Share:
    """분포에서 value보다 낮은 쪽·같은·높은 쪽의 비율. 순서는 ORDER[node]를 따른다."""
    order = ORDER[node]
    p = dict(probs)
    total = sum(p.get(v, 0.0) for v in order)
    rank = order.index(value)
    below = sum(p.get(v, 0.0) for v in order[:rank]) / total
    same = p.get(value, 0.0) / total
    return Share(below=below, same=same, above=max(0.0, 1.0 - below - same))
