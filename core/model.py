"""조건부 확률 체인의 노드들. 정의는 docs/probability-model.md 와 1:1 이다.

국가 → 성별 → 생존(국가·성별) , 국가 → 경제 수준
각 함수는 부모 값이 주어졌을 때의 분포를 돌려준다. 통계가 없으면 None(0이 아니다).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from core.stats import Country, Snapshot

SEXES = ("male", "female")
SURVIVALS = ("infant_death", "child_death", "survived_5")
ECONOMIES = ("below_3_00", "below_4_20", "below_8_30", "above_8_30")
NODES = ("country", "sex", "survival", "economy")

DEFAULT_SEX_RATIO = 1.05

LABELS: Dict[str, Dict[str, str]] = {
    "sex": {"male": "남자", "female": "여자"},
    "survival": {
        "infant_death": "첫돌을 맞지 못했다",
        "child_death": "다섯 살을 맞지 못했다",
        "survived_5": "다섯 살까지 살아남았다",
    },
    "economy": {
        "below_3_00": "하루 $3.00 미만 (극빈)",
        "below_4_20": "하루 $3.00~$4.20",
        "below_8_30": "하루 $4.20~$8.30",
        "above_8_30": "하루 $8.30 이상",
    },
}
NODE_LABELS = {"country": "국가", "sex": "성별", "survival": "다섯 살까지", "economy": "가정의 경제 수준"}


@dataclass(frozen=True)
class Dist:
    """한 노드의 조건부 분포. 순서가 곧 뽑기의 누적 순서다."""

    probs: Tuple[Tuple[str, float], ...]
    assumed: bool = False

    def p(self, value: str) -> float:
        for v, p in self.probs:
            if v == value:
                return p
        return 0.0


def country_dist(snapshot: Snapshot) -> Dist:
    total = snapshot.total_births
    return Dist(tuple((c.iso3, c.births / total) for c in snapshot.countries))


def sex_dist(country: Country) -> Dist:
    ratio = country.sex_ratio
    assumed = ratio is None
    r = DEFAULT_SEX_RATIO if ratio is None else ratio
    return Dist((("male", r / (1 + r)), ("female", 1 / (1 + r))), assumed=assumed)


def survival_dist(country: Country, sex: str) -> Optional[Dist]:
    s = country.survival.get(sex)
    if s is None:
        return None
    infant = s.imr / 1000
    child = (s.u5mr - s.imr) / 1000
    return Dist(
        (("infant_death", infant), ("child_death", child), ("survived_5", 1 - s.u5mr / 1000)),
        assumed=s.assumed_from_total,
    )


def economy_dist(country: Country) -> Optional[Dist]:
    e = country.economy
    if e is None:
        return None
    a, b, c = e.pct_below_3_00 / 100, e.pct_below_4_20 / 100, e.pct_below_8_30 / 100
    return Dist((("below_3_00", a), ("below_4_20", b - a), ("below_8_30", c - b), ("above_8_30", 1 - c)))
