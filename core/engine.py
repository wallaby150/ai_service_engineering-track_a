"""뽑기 · 역확률 · 목표 달성까지의 횟수. 전부 결정적 코드다.

같은 시드는 같은 인생을 낸다. 난수는 노드 순서(국가 → 성별 → 생존 → 경제)대로
항상 네 번 쓴다 — 데이터가 없는 노드도 자리는 소비해서, 시드와 결과의 대응이 흔들리지 않게 한다.
"""

from __future__ import annotations

import bisect
import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from core.errors import UnknownValue
from core.model import (
    ECONOMIES,
    SEXES,
    SURVIVALS,
    Dist,
    country_dist,
    economy_dist,
    sex_dist,
    survival_dist,
)
from core.stats import Country, Snapshot

MAX_SEED = 2**31 - 1


@dataclass(frozen=True)
class Step:
    """체인의 한 칸. value가 None이면 그 나라에 통계가 없다는 뜻이다."""

    node: str
    value: Optional[str]
    p: Optional[float]
    assumed: bool = False


@dataclass(frozen=True)
class Life:
    seed: int
    country: Country
    steps: Tuple[Step, ...]

    def value(self, node: str) -> Optional[str]:
        for s in self.steps:
            if s.node == node:
                return s.value
        return None

    @property
    def joint_p(self) -> float:
        """이 조합 그대로 태어날 확률. 통계가 없는 칸은 곱에서 빠진다(complete로 알린다)."""
        p = 1.0
        for s in self.steps:
            if s.p is not None:
                p *= s.p
        return p

    @property
    def complete(self) -> bool:
        return all(s.value is not None for s in self.steps)

    @property
    def life_expectancy(self) -> Optional[float]:
        return self.country.life_expectancy.get(self.value("sex") or "")


@dataclass(frozen=True)
class Target:
    """역확률의 대상. None인 칸은 '상관없음'이다."""

    country: Optional[str] = None
    sex: Optional[str] = None
    survival: Optional[str] = None
    economy: Optional[str] = None

    def fields(self) -> Dict[str, str]:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def matches(self, values: Dict[str, Optional[str]]) -> bool:
        return all(values.get(k) == v for k, v in self.fields().items())


@dataclass(frozen=True)
class Odds:
    target: Target
    p: Optional[float]
    coverage: float
    steps: Tuple[Step, ...] = ()
    reason: Optional[str] = None

    @property
    def expected_tries(self) -> Optional[float]:
        return None if not self.p else 1 / self.p

    def tries(self, q: float) -> Optional[int]:
        return tries_needed(self.p or 0.0, q)


@dataclass(frozen=True)
class UntilResult:
    found: bool
    tries: int
    max_tries: int
    life: Optional[Life]


def tries_needed(p: float, q: float) -> Optional[int]:
    """확률 q로 적어도 한 번 나오려면 몇 번 뽑아야 하나. ⌈ln(1−q) / ln(1−p)⌉"""
    if not 0 < q < 1:
        raise ValueError("q는 0과 1 사이여야 한다")
    if p <= 0:
        return None
    if p >= 1:
        return 1
    return max(1, math.ceil(math.log1p(-q) / math.log1p(-p)))


def new_seed() -> int:
    return random.SystemRandom().randint(0, MAX_SEED)


def _pick(dist: Dist, u: float) -> Tuple[str, float]:
    acc = 0.0
    for value, p in dist.probs:
        acc += p
        if u < acc:
            return value, p
    return dist.probs[-1]  # 부동소수 끝자락 — 마지막 값


class Engine:
    def __init__(self, snapshot: Snapshot) -> None:
        self.snapshot = snapshot
        self._countries: Sequence[Country] = snapshot.countries
        self._by_iso3 = {c.iso3: c for c in snapshot.countries}
        cdist = country_dist(snapshot)
        self._country_p = dict(cdist.probs)
        self._cum: List[float] = []
        acc = 0.0
        for _, p in cdist.probs:
            acc += p
            self._cum.append(acc)
        self._sex = {c.iso3: sex_dist(c) for c in self._countries}
        self._surv = {(c.iso3, s): survival_dist(c, s) for c in self._countries for s in SEXES}
        self._eco = {c.iso3: economy_dist(c) for c in self._countries}

    # ── 검증 ──────────────────────────────────────────────
    def check_country(self, iso3: Optional[str]) -> Optional[str]:
        if iso3 is None:
            return None
        code = iso3.upper()
        if code not in self._by_iso3:
            raise UnknownValue("country", iso3, sorted(self._by_iso3))
        return code

    def check_target(self, target: Target) -> Target:
        for field, allowed in (("sex", SEXES), ("survival", SURVIVALS), ("economy", ECONOMIES)):
            v = getattr(target, field)
            if v is not None and v not in allowed:
                raise UnknownValue(field, v, allowed)
        return Target(self.check_country(target.country), target.sex, target.survival, target.economy)

    # ── 뽑기 ──────────────────────────────────────────────
    def _draw(self, rng: random.Random, fixed_country: Optional[str]) -> Tuple[Step, ...]:
        u_country, u_sex, u_surv, u_eco = rng.random(), rng.random(), rng.random(), rng.random()
        if fixed_country:
            iso3 = fixed_country
        else:
            i = min(bisect.bisect_right(self._cum, u_country * self._cum[-1]), len(self._cum) - 1)
            iso3 = self._countries[i].iso3
        steps = [Step("country", iso3, self._country_p[iso3])]

        sd = self._sex[iso3]
        sex, p_sex = _pick(sd, u_sex)
        steps.append(Step("sex", sex, p_sex, sd.assumed))

        vd = self._surv[(iso3, sex)]
        if vd is None:
            steps.append(Step("survival", None, None))
        else:
            v, p = _pick(vd, u_surv)
            steps.append(Step("survival", v, p, vd.assumed))

        ed = self._eco[iso3]
        if ed is None:
            steps.append(Step("economy", None, None))
        else:
            v, p = _pick(ed, u_eco)
            steps.append(Step("economy", v, p, ed.assumed))
        return tuple(steps)

    def sample(self, seed: int, country: Optional[str] = None) -> Life:
        fixed = self.check_country(country)
        steps = self._draw(random.Random(seed), fixed)
        return Life(seed=seed, country=self._by_iso3[steps[0].value or ""], steps=steps)

    def sample_until(self, target: Target, seed: int, max_tries: int) -> UntilResult:
        """조건이 나올 때까지 시드를 하나씩 올려 가며 뽑는다. 상한을 넘으면 멈춘다."""
        target = self.check_target(target)
        for i in range(max_tries):
            steps = self._draw(random.Random(seed + i), None)
            if target.matches({s.node: s.value for s in steps}):
                life = Life(seed=seed + i, country=self._by_iso3[steps[0].value or ""], steps=steps)
                return UntilResult(True, i + 1, max_tries, life)
        return UntilResult(False, max_tries, max_tries, None)

    # ── 역확률 ────────────────────────────────────────────
    def _covered(self, c: Country, target: Target, sexes: Sequence[str]) -> bool:
        if target.survival and any(self._surv[(c.iso3, s)] is None for s in sexes):
            return False
        if target.economy and self._eco[c.iso3] is None:
            return False
        return True

    def _f(self, c: Country, target: Target, sexes: Sequence[str]) -> float:
        """P(성별·생존·경제 조건 | 국가 c)"""
        total = 0.0
        for s in sexes:
            p = self._sex[c.iso3].p(s)
            if target.survival:
                p *= self._surv[(c.iso3, s)].p(target.survival)  # type: ignore[union-attr]
            total += p
        if target.economy:
            total *= self._eco[c.iso3].p(target.economy)  # type: ignore[union-attr]
        return total

    def probability(self, target: Target) -> Odds:
        """조건의 정확한 확률. 통계가 있는 국가의 출생아만을 모집단으로 삼고, 그 비율을 coverage로 알린다."""
        target = self.check_target(target)
        sexes = (target.sex,) if target.sex else SEXES

        covered_mass, numerator = 0.0, 0.0
        for c in self._countries:
            if not self._covered(c, target, sexes):
                continue
            w = self._country_p[c.iso3]
            covered_mass += w
            if target.country and c.iso3 != target.country:
                continue
            numerator += w * self._f(c, target, sexes)

        if target.country and not self._covered(self._by_iso3[target.country], target, sexes):
            missing = [n for n in ("survival", "economy") if getattr(target, n)]
            return Odds(target, None, covered_mass, reason=f"이 나라에는 {', '.join(missing)} 통계가 없다")
        if covered_mass == 0:
            return Odds(target, None, 0.0, reason="조건에 맞는 통계가 있는 나라가 없다")

        steps = self._explain(target, sexes, covered_mass) if target.country else ()
        return Odds(target, numerator / covered_mass, covered_mass, steps)

    def _explain(self, target: Target, sexes: Sequence[str], covered_mass: float) -> Tuple[Step, ...]:
        """국가가 정해졌을 때 확률을 칸별 조건부 확률의 곱으로 풀어 쓴다."""
        c = self._by_iso3[target.country or ""]
        steps = [Step("country", c.iso3, self._country_p[c.iso3] / covered_mass)]
        if target.sex:
            steps.append(Step("sex", target.sex, self._sex[c.iso3].p(target.sex), self._sex[c.iso3].assumed))
        if target.survival:
            p = sum(
                self._sex[c.iso3].p(s) * self._surv[(c.iso3, s)].p(target.survival)  # type: ignore[union-attr]
                for s in sexes
            ) / sum(self._sex[c.iso3].p(s) for s in sexes)
            steps.append(Step("survival", target.survival, p))
        if target.economy:
            steps.append(Step("economy", target.economy, self._eco[c.iso3].p(target.economy)))  # type: ignore[union-attr]
        return tuple(steps)
