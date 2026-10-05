"""뽑힌 인생을 '서사가 쓸 수 있는 사실'의 목록으로 바꾼다.

서사(템플릿이든 LLM이든)는 여기 있는 값만 쓴다. v0.5에서 LLM 서사를 검증할 때도
이 목록이 정답지가 된다 — 서사에 나온 숫자가 여기 없으면 지어낸 것이다.
"""

from __future__ import annotations

from typing import Dict, Optional, Union

from core.engine import Life
from core.model import LABELS

Fact = Union[str, float, int, None]


def _pct(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(x * 100, 2)


def facts_of(life: Life) -> Dict[str, Fact]:
    c = life.country
    sex = life.value("sex") or ""
    surv = c.survival.get(sex)
    eco = c.economy
    steps = {s.node: s for s in life.steps}
    economy = life.value("economy")

    facts: Dict[str, Fact] = {
        "country": c.name_ko,
        "region": c.region,
        "income_level": c.income_level,
        "sex": LABELS["sex"].get(sex),
        "survival": LABELS["survival"].get(life.value("survival") or ""),
        "economy": LABELS["economy"].get(economy or ""),
        "country_share_pct": _pct(steps["country"].p),
        "births_per_year": c.births,
        "imr_per_1000": surv.imr if surv else None,
        "u5mr_per_1000": surv.u5mr if surv else None,
        "survivors_per_1000": None if surv is None else round(1000 - surv.u5mr, 1),
        "economy_band_pct": _pct(steps["economy"].p),
        "pct_below_3_00": eco.pct_below_3_00 if eco else None,
        "life_expectancy": life.life_expectancy,
        "joint_one_in": round(1 / life.joint_p) if life.joint_p > 0 else None,
    }
    return facts
