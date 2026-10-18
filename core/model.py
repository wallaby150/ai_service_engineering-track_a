"""조건부 확률 체인의 노드들. 정의는 docs/probability-model.md 와 1:1 이다.

국가 → 성별 → 생존(국가·성별) , 국가 → 경제 수준
각 함수는 부모 값이 주어졌을 때의 분포를 돌려준다. 통계가 없으면 None(0이 아니다).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from core.stats import Country, Korea, Province, Snapshot

SEXES = ("male", "female")
SURVIVALS = ("infant_death", "child_death", "survived_5")
ECONOMIES = ("below_3_00", "below_4_20", "below_8_30", "above_8_30")
EMPLOYMENTS = ("employed", "not_employed")
NODES = ("country", "sex", "survival", "economy", "province", "employment", "occupation")
KOREA_NODES = ("province", "employment", "occupation")  # 대한민국에서 태어났을 때만 열린다
KOREA_ISO3 = "KOR"

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
    "employment": {"employed": "일하고 있다", "not_employed": "일하지 않고 있다"},
}
NODE_LABELS = {
    "country": "국가", "sex": "성별", "survival": "다섯 살까지", "economy": "가정의 경제 수준",
    "province": "태어난 시도", "employment": "어른이 되어", "occupation": "직업(대분류)",
}

# 칸마다 사용자에게 밝힐 가정. docs/probability-model.md의 '가정'과 1:1이다 — 한쪽을 고치면 다른 쪽도 고친다
NODE_ASSUMPTIONS = {
    "country": "출생아 수는 조출생률 × 총인구로 어림했습니다. 두 값의 기준 연도가 다를 수 있습니다.",
    "sex": "출생 성비를 그대로 씁니다. 성비 통계가 없는 나라는 1.05로 가정합니다(추정 표시).",
    "survival": "UN IGME 추정치입니다. 성별 값이 없으면 남녀 합친 값을 씁니다(추정 표시).",
    "economy": "전체 인구의 빈곤율을 신생아에게 그대로 적용했습니다. 아동 빈곤율이 더 높은 나라가 많아 신생아의 빈곤을 실제보다 낮게 잡습니다.",
    "province": "같은 성별 출생아 가운데 이 시도에서 태어난 비중입니다.",
    "employment": "15세 이상 전체(노년 포함)의 고용률이라 한창 일할 나이의 고용률보다 낮습니다. 다섯 살 이후의 사망과 이사는 모델에 없습니다.",
    "occupation": "2020년 인구총조사 값이라 고용률(2025년)과 기준 연도가 다릅니다. 태어난 시도에서 산다고 봅니다.",
}


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

def province_dist(korea: Korea, sex: str) -> Dist:
    """P(시도 | 대한민국, 성별) = 그 성별 출생아 중 시도의 비중."""
    total = sum(p.births[sex] for p in korea.provinces)
    return Dist(tuple((p.code, p.births[sex] / total) for p in korea.provinces))


def employment_dist(province: Province, sex: str) -> Optional[Dist]:
    """P(일한다 | 시도, 성별) = 15세 이상 고용률. 다섯 살 이후 성인이 될 때까지의 사망·이사는 모델에 없다."""
    rate = province.employment_rate_pct.get(sex)
    if rate is None:
        return None
    return Dist((("employed", rate / 100), ("not_employed", 1 - rate / 100)))


def occupation_dist(province: Province, sex: str) -> Optional[Dist]:
    """P(직업 | 시도, 성별, 일한다) = 그 시도·성별 취업자의 직업 대분류 비중."""
    counts = province.occupations.get(sex)
    if not counts:
        return None
    total = sum(counts.values())
    return Dist(tuple((code, n / total) for code, n in sorted(counts.items())))


def label_of(snapshot: Snapshot, node: str, value: Optional[str]) -> Optional[str]:
    """칸의 값 → 사람이 읽는 이름. 국가·시도·직업은 스냅샷에서, 나머지는 LABELS에서."""
    if value is None:
        return None
    if node == "country":
        c = snapshot.get(value)
        return c.name_ko if c else None
    if node == "province":
        p = snapshot.korea.province(value) if snapshot.korea else None
        return p.name if p else None
    if node == "occupation":
        return snapshot.korea.occupation_labels.get(value) if snapshot.korea else None
    return LABELS.get(node, {}).get(value)


# World Bank 분류의 한국어 이름. 서사와 화면이 영어 원문을 그대로 쓰지 않게 한다
REGION_LABELS = {
    "East Asia & Pacific": "동아시아·태평양",
    "Europe & Central Asia": "유럽·중앙아시아",
    "Latin America & Caribbean": "라틴아메리카·카리브",
    "Middle East, North Africa, Afghanistan & Pakistan": "중동·북아프리카·아프가니스탄·파키스탄",
    "North America": "북아메리카",
    "South Asia": "남아시아",
    "Sub-Saharan Africa": "사하라 이남 아프리카",
}
INCOME_LABELS = {
    "High income": "고소득국",
    "Upper middle income": "중상위 소득국",
    "Lower middle income": "중하위 소득국",
    "Low income": "저소득국",
}
