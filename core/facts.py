"""뽑힌 인생을 '서사가 쓸 수 있는 사실'의 목록으로 바꾼다.

서사(템플릿이든 LLM이든)는 여기 있는 값만 쓴다. v0.5에서 LLM 서사를 검증할 때도
이 목록이 정답지가 된다 — 서사에 나온 숫자가 여기 없으면 지어낸 것이다.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Union

from core.engine import Life
from core.model import INCOME_LABELS, LABELS, REGION_LABELS
from core.units import births_per_minute, minutes_per_birth, one_in

Fact = Union[str, float, int, None]


def _pct(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(x * 100, 2)


def _round(x: Optional[float], digits: int) -> Optional[float]:
    return None if x is None else round(x, digits)


def _year(text: Optional[str]) -> Optional[int]:
    """'2025년 하반기' → 2025. 서사가 연도를 쓰면 검증이 숫자로 대조할 수 있게."""
    m = re.search(r"\d{4}", text or "")
    return int(m.group()) if m else None


def _korea_facts(steps: dict) -> Dict[str, Fact]:
    """대한민국에서 태어났을 때만 붙는 사실. 열리지 않은 칸의 키는 아예 넣지 않는다."""
    out: Dict[str, Fact] = {}
    prov = steps.get("province")
    if prov is None:
        return out
    out.update({
        "province": prov.label,
        "province_share_pct": _pct(prov.p),  # 대한민국의 같은 성별 출생아 중 이 시도의 비중
        "province_births_year": _year(prov.year),
    })
    emp = steps.get("employment")
    if emp is not None and emp.p is not None:
        rate = emp.p if emp.value == "employed" else 1 - emp.p
        out.update({
            "employment": LABELS["employment"].get(emp.value or ""),
            "employment_rate_pct": _pct(rate),  # 이 시도·성별 15세 이상 중 일하는 사람의 비율
            "not_employed_pct": _pct(1 - rate),
            "employment_year": _year(emp.year),
            "employment_period": emp.year,
        })
    occ = steps.get("occupation")
    if occ is not None and occ.p is not None:
        out.update({
            "occupation": occ.label,
            "occupation_share_pct": _pct(occ.p),  # 이 시도·성별 취업자 중 이 직업의 비중
            "occupation_year": _year(occ.year),
            "occupation_period": occ.year,
        })
    return out


def _headline_facts(life: Life) -> Dict[str, Fact]:
    """위치 한 줄. 문장이 그대로 쓸 수 있게 경제는 100명당, 생존은 1,000명당으로 미리 바꿔 둔다."""
    h = life.headline
    if h is None:
        return {}
    scale, unit = (100, "per_100") if h.node == "economy" else (1000, "per_1000")
    out: Dict[str, Fact] = {"headline": h.node, "headline_year": _year(h.year), "headline_period": h.year}
    for scope, share in (("country", h.country), ("world", h.world)):
        if share is None:
            continue
        for part in ("below", "same", "above"):
            out[f"headline_{scope}_{part}_{unit}"] = round(getattr(share, part) * scale, 1)
    if h.world is not None:
        out["headline_world_coverage_pct"] = _pct(h.world_coverage)
    return out


def facts_of(life: Life) -> Dict[str, Fact]:
    c = life.country
    sex = life.value("sex") or ""
    surv = c.survival.get(sex)
    eco = c.economy
    steps = {s.node: s for s in life.steps}
    economy = life.value("economy")

    facts: Dict[str, Fact] = {
        "country": c.name_ko,
        "region": REGION_LABELS.get(c.region, c.region),
        "income_level": INCOME_LABELS.get(c.income_level, c.income_level),
        "sex": LABELS["sex"].get(sex),
        "survival": LABELS["survival"].get(life.value("survival") or ""),
        "economy": LABELS["economy"].get(economy or ""),
        "country_share_pct": _pct(steps["country"].p),
        "births_per_year": c.births,
        "country_one_in": one_in(steps["country"].p),  # 세계 출생아 'N명 중 1명'이 이 나라에서 태어난다
        "births_per_minute": _round(births_per_minute(c.births), 2),
        "minutes_per_birth": _round(minutes_per_birth(c.births), 1),
        "imr_per_1000": surv.imr if surv else None,
        "u5mr_per_1000": surv.u5mr if surv else None,
        "survivors_per_1000": None if surv is None else round(1000 - surv.u5mr, 1),
        "economy_band_pct": _pct(steps["economy"].p),
        "pct_below_3_00": eco.pct_below_3_00 if eco else None,
        "life_expectancy": life.life_expectancy,
        "joint_one_in": round(1 / life.joint_p) if life.joint_p > 0 else None,
    }
    facts.update(_korea_facts(steps))
    facts.update(_headline_facts(life))
    return facts


def peer_facts(life: Life) -> Dict[str, Fact]:
    """같은 순간 태어난 다른 사람의 사실 — 해석가가 대비를 만들 재료. 뽑힌 값과 그 나라 통계만 담는다."""
    f = facts_of(life)
    keys = ("country", "sex", "survival", "economy", "u5mr_per_1000", "life_expectancy", "province", "occupation")
    return {k: f[k] for k in keys if f.get(k) is not None}
