"""서사가 맥락으로 쓸 수 있는 읽기 전용 조회. 전부 스냅샷에서 코드가 계산한다.

LLM은 어떤 조회를 할지만 고르고, 숫자(평균·배율·순위)는 여기서 나온다.
'세계 평균의 몇 배'를 모델이 나눗셈으로 만들면 틀릴 수 있으므로 배율까지 미리 계산해 준다.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from core.model import INCOME_LABELS, REGION_LABELS
from core.stats import Country, Snapshot

METRICS = ("u5mr", "life_expectancy", "poverty_3_00")
METRIC_LABELS = {
    "u5mr": "5세 미만 사망률(출생아 1,000명당, 남녀 평균)",
    "life_expectancy": "기대수명(세, 남녀 평균)",
    "poverty_3_00": "하루 $3.00 미만 극빈 인구 비율(%)",
}


def _mean(*xs: Optional[float]) -> Optional[float]:
    vals = [x for x in xs if x is not None]
    return sum(vals) / len(vals) if vals else None


def _metric(c: Country, metric: str) -> Optional[float]:
    if metric == "u5mr":
        m, f = c.survival.get("male"), c.survival.get("female")
        return _mean(m.u5mr if m else None, f.u5mr if f else None)
    if metric == "life_expectancy":
        return _mean(c.life_expectancy.get("male"), c.life_expectancy.get("female"))
    if metric == "poverty_3_00":
        return c.economy.pct_below_3_00 if c.economy else None
    raise ValueError(f"metric은 {METRICS} 중 하나")


def _r(x: Optional[float], digits: int = 1) -> Optional[float]:
    return None if x is None else round(x, digits)


def country_profile(snapshot: Snapshot, iso3: str) -> Dict[str, object]:
    c = snapshot.get(iso3)
    if c is None:
        raise KeyError(iso3)
    m, f = c.survival.get("male"), c.survival.get("female")
    return {
        "country": c.name_ko,
        "region": REGION_LABELS.get(c.region, c.region),
        "income_level": INCOME_LABELS.get(c.income_level, c.income_level),
        "births_per_year": c.births,
        "share_of_world_births_pct": _r(100 * c.births / snapshot.total_births, 2),
        "life_expectancy_male": _r(c.life_expectancy.get("male")),
        "life_expectancy_female": _r(c.life_expectancy.get("female")),
        "imr_male_per_1000": m.imr if m else None,
        "imr_female_per_1000": f.imr if f else None,
        "u5mr_male_per_1000": m.u5mr if m else None,
        "u5mr_female_per_1000": f.u5mr if f else None,
        "pct_below_3_00": c.economy.pct_below_3_00 if c.economy else None,
        "pct_below_8_30": c.economy.pct_below_8_30 if c.economy else None,
        "economy_year": c.economy.year if c.economy else None,
    }


def world_comparison(snapshot: Snapshot, iso3: str, metric: str) -> Dict[str, object]:
    """출생아 가중 세계 평균과 비교. rank는 값이 큰 순서(1 = 가장 높음)."""
    c = snapshot.get(iso3)
    if c is None:
        raise KeyError(iso3)
    rows: List[Tuple[str, float, int]] = [
        (x.iso3, v, x.births) for x in snapshot.countries for v in [_metric(x, metric)] if v is not None
    ]
    total = sum(b for _, _, b in rows)
    world = sum(v * b for _, v, b in rows) / total if total else None
    value = _metric(c, metric)
    ranked = sorted(rows, key=lambda r: -r[1])
    rank = next((i + 1 for i, r in enumerate(ranked) if r[0] == iso3), None)
    return {
        "metric": METRIC_LABELS[metric],
        "country_value": _r(value),
        "world_average": _r(world),
        "ratio_to_world": _r(value / world) if value is not None and world else None,
        "rank_high_to_low": rank,
        "countries_with_data": len(rows),
    }


def region_peers(snapshot: Snapshot, iso3: str, limit: int = 5) -> Dict[str, object]:
    """같은 지역(World Bank 분류)에서 출생아가 많은 나라들."""
    c = snapshot.get(iso3)
    if c is None:
        raise KeyError(iso3)
    peers = sorted((x for x in snapshot.countries if x.region == c.region), key=lambda x: -x.births)[:limit]
    return {
        "region": REGION_LABELS.get(c.region, c.region),
        "peers": [
            {
                "country": x.name_ko,
                "u5mr_per_1000": _r(_metric(x, "u5mr")),
                "life_expectancy": _r(_metric(x, "life_expectancy")),
                "pct_below_3_00": _r(_metric(x, "poverty_3_00")),
            }
            for x in peers
        ],
    }


# 서사 계획자가 고를 수 있는 조회 전부. 국가는 항상 코드가 넣는다 — 모델이 남의 나라를 고를 수 없다.
TOOLS: Dict[str, Tuple[str, Callable[..., Dict[str, object]]]] = {
    "country_profile": ("태어난 나라의 기본 통계(기대수명, 영아·5세 미만 사망률, 빈곤율, 출생아 수)", country_profile),
    "world_comparison": ("태어난 나라의 지표를 세계 평균과 비교(배율·순위 포함). metric 필요", world_comparison),
    "region_peers": ("같은 지역에서 출생아가 많은 나라들의 지표", region_peers),
}


def run_tool(snapshot: Snapshot, name: str, iso3: str, metric: Optional[str] = None) -> Dict[str, object]:
    if name not in TOOLS:
        return {"error": f"없는 조회: {name}. 가능한 조회: {list(TOOLS)}"}
    fn = TOOLS[name][1]
    if name == "world_comparison":
        if metric not in METRICS:
            return {"error": f"metric={metric!r} 는 지원하지 않는다. 가능한 값: {list(METRICS)}"}
        return fn(snapshot, iso3, metric)
    return fn(snapshot, iso3)
