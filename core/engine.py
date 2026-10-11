"""뽑기 · 역확률 · 목표 달성까지의 횟수. 전부 결정적 코드다.

같은 시드는 같은 인생을 낸다. 난수는 노드 순서대로 항상 일곱 번 뽑는다:
국가 → 성별 → 생존 → 경제 → 시도 → 고용 → 직업. 데이터가 없거나 해당 없는 칸도 자리는 소비해서
시드와 결과의 대응이 흔들리지 않는다. 앞의 네 개는 v0.2와 같아서, 예전 공유 링크도 같은 인생을 낸다.

한국 칸(시도·고용·직업)은 대한민국에서 태어났을 때만 열리고, 고용은 다섯 살까지 살아남았을 때만,
직업은 일하고 있을 때만 열린다. 열리지 않은 칸은 '통계 없음'이 아니라 아예 없는 칸이다.
"""

from __future__ import annotations

import bisect
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from core.errors import UnknownValue
from core.model import (
    ECONOMIES,
    EMPLOYMENTS,
    KOREA_ISO3,
    SEXES,
    SURVIVALS,
    Dist,
    country_dist,
    economy_dist,
    employment_dist,
    occupation_dist,
    province_dist,
    sex_dist,
    survival_dist,
)
from core.position import Headline, choose_headline, share_of
from core.stats import Country, Snapshot

MAX_SEED = 2**31 - 1
DRAWS = 7


@dataclass(frozen=True)
class Step:
    """체인의 한 칸. value가 None이면 그 나라에 통계가 없다는 뜻이다."""

    node: str
    value: Optional[str]
    p: Optional[float]
    assumed: bool = False
    label: Optional[str] = None  # 한국 칸(시도·직업)의 이름 — 스냅샷 없이도 서사가 쓸 수 있게
    year: Optional[str] = None  # 한국 칸이 기댄 통계의 기준 시점(예: "2025년 하반기")


@dataclass(frozen=True)
class Life:
    seed: int
    country: Country
    steps: Tuple[Step, ...]
    headline: Optional[Headline] = field(default=None, compare=False)  # 출생 코호트 안의 위치 한 줄

    def value(self, node: str) -> Optional[str]:
        for s in self.steps:
            if s.node == node:
                return s.value
        return None

    @property
    def joint_p(self) -> float:
        """이 조합 그대로 나올 확률. 통계가 없는 칸은 곱에서 빠진다(complete로 알린다)."""
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
    province: Optional[str] = None
    employment: Optional[str] = None
    occupation: Optional[str] = None

    def fields(self) -> Dict[str, str]:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def matches(self, values: Dict[str, Optional[str]]) -> bool:
        return all(values.get(k) == v for k, v in self.fields().items())

    @property
    def korean(self) -> bool:
        return any((self.province, self.employment, self.occupation))

    @property
    def adult(self) -> bool:
        """어른이 된 뒤의 칸을 묻는가 — 그러려면 다섯 살까지 살아남아야 한다."""
        return bool(self.employment or self.occupation)


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


def same_moment_seeds(seed: int, n: int = 4) -> List[int]:
    """같은 순간 세계 어딘가에서 태어난 다른 n명의 시드.

    본 인생의 난수(random.Random(seed))와 따로 뽑는다 — 본 인생은 그대로다. 문자열 시드는 sha512로
    정수가 되므로 실행·플랫폼·PYTHONHASHSEED와 무관하게 같은 값을 낸다.
    """
    rng = random.Random(f"{seed}:same-moment")
    out: List[int] = []
    while len(out) < n:
        s = rng.randint(0, MAX_SEED)
        if s != seed and s not in out:
            out.append(s)
    return out


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

        k = snapshot.korea
        self._korea_on = k is not None and KOREA_ISO3 in self._by_iso3
        self._prov = {s: province_dist(k, s) for s in SEXES} if k else {}
        self._emp = {(p.code, s): employment_dist(p, s) for p in k.provinces for s in SEXES} if k else {}
        self._occ = {(p.code, s): occupation_dist(p, s) for p in k.provinces for s in SEXES} if k else {}
        self._province_codes = [p.code for p in k.provinces] if k else []
        self._occupation_codes = sorted(k.occupation_labels) if k else []
        self._province_names = {p.code: p.name for p in k.provinces} if k else {}
        self._occupation_names = dict(k.occupation_labels) if k else {}
        self._years = dict(k.years) if k else {}

    # ── 검증 ──────────────────────────────────────────────
    def check_country(self, iso3: Optional[str]) -> Optional[str]:
        if iso3 is None:
            return None
        code = iso3.upper()
        if code not in self._by_iso3:
            raise UnknownValue("country", iso3, sorted(self._by_iso3))
        return code

    def check_target(self, target: Target) -> Target:
        checks = [("sex", SEXES), ("survival", SURVIVALS), ("economy", ECONOMIES), ("employment", EMPLOYMENTS)]
        if self._korea_on:  # 한국 데이터가 없으면 값 검사 대신 probability()가 '통계 없음'으로 답한다
            checks += [("province", self._province_codes), ("occupation", self._occupation_codes)]
        for field, allowed in checks:
            v = getattr(target, field)
            if v is not None and v not in allowed:
                raise UnknownValue(field, v, allowed)
        return Target(self.check_country(target.country), target.sex, target.survival, target.economy,
                      target.province, target.employment, target.occupation)

    # ── 기준 연도 ──────────────────────────────────────────
    @staticmethod
    def _year_of(node: str, c: Country, sex: Optional[str]) -> Optional[str]:
        """세계 칸이 기댄 통계의 기준 연도. 나라마다 '가장 최근 값'의 연도가 다르다."""
        year: Optional[int] = None
        if node == "country":
            year = c.years.get("births")
        elif node == "sex":
            year = c.years.get("sex_ratio")
        elif node == "survival":
            surv = c.survival.get(sex or "")
            year = surv.year if surv else None
        elif node == "economy":
            year = c.economy.year if c.economy else None
        return f"{year}년" if year else None

    # ── 뽑기 ──────────────────────────────────────────────
    def _draw(self, rng: random.Random, fixed_country: Optional[str]) -> Tuple[Step, ...]:
        u = [rng.random() for _ in range(DRAWS)]
        if fixed_country:
            iso3 = fixed_country
        else:
            i = min(bisect.bisect_right(self._cum, u[0] * self._cum[-1]), len(self._cum) - 1)
            iso3 = self._countries[i].iso3
        c = self._by_iso3[iso3]
        steps = [Step("country", iso3, self._country_p[iso3], year=self._year_of("country", c, None))]

        sd = self._sex[iso3]
        sex, p_sex = _pick(sd, u[1])
        steps.append(Step("sex", sex, p_sex, sd.assumed, year=self._year_of("sex", c, sex)))

        survival: Optional[str] = None
        vd = self._surv[(iso3, sex)]
        if vd is None:
            steps.append(Step("survival", None, None))
        else:
            survival, p = _pick(vd, u[2])
            steps.append(Step("survival", survival, p, vd.assumed, year=self._year_of("survival", c, sex)))

        ed = self._eco[iso3]
        if ed is None:
            steps.append(Step("economy", None, None))
        else:
            v, p = _pick(ed, u[3])
            steps.append(Step("economy", v, p, ed.assumed, year=self._year_of("economy", c, None)))

        if iso3 == KOREA_ISO3 and self._korea_on:
            steps.extend(self._draw_korea(sex, survival, u[4], u[5], u[6]))
        return tuple(steps)

    def _draw_korea(self, sex: str, survival: Optional[str], u_prov: float, u_emp: float, u_occ: float) -> List[Step]:
        y = self._years
        code, p = _pick(self._prov[sex], u_prov)
        steps = [Step("province", code, p, label=self._province_names.get(code), year=y.get("births"))]
        if survival != "survived_5":
            return steps  # 어른이 되지 못한 삶에는 고용·직업 칸이 없다
        ed = self._emp[(code, sex)]
        if ed is None:
            return steps + [Step("employment", None, None)]
        employment, p = _pick(ed, u_emp)
        steps.append(Step("employment", employment, p, year=y.get("employment")))
        if employment != "employed":
            return steps
        od = self._occ[(code, sex)]
        if od is None:
            return steps + [Step("occupation", None, None)]
        occupation, p = _pick(od, u_occ)
        return steps + [Step("occupation", occupation, p, label=self._occupation_names.get(occupation),
                             year=y.get("occupation"))]

    def sample(self, seed: int, country: Optional[str] = None) -> Life:
        fixed = self.check_country(country)
        steps = self._draw(random.Random(seed), fixed)
        return Life(seed=seed, country=self._by_iso3[steps[0].value or ""], steps=steps, headline=self._headline(steps))

    def same_moment(self, seed: int, n: int = 4) -> List[Life]:
        """같은 순간 태어난 다른 n명. 국가를 고정하지 않고 세계에서 뽑는다."""
        return [self.sample(s) for s in same_moment_seeds(seed, n)]

    def sample_until(self, target: Target, seed: int, max_tries: int) -> UntilResult:
        """조건이 나올 때까지 시드를 하나씩 올려 가며 뽑는다. 상한을 넘으면 멈춘다."""
        target = self.check_target(target)
        for i in range(max_tries):
            s_i = (seed + i) % (MAX_SEED + 1)  # 돌려받은 시드로 다시 요청할 수 있게 범위 안에 감는다
            steps = self._draw(random.Random(s_i), None)
            if target.matches({s.node: s.value for s in steps}):
                life = Life(seed=s_i, country=self._by_iso3[steps[0].value or ""], steps=steps,
                            headline=self._headline(steps))
                return UntilResult(True, i + 1, max_tries, life)
        return UntilResult(False, max_tries, max_tries, None)

    # ── 출생 코호트 안의 위치 ─────────────────────────────────
    def _world_tables(self) -> Dict[str, object]:
        """세계 비율은 정확한 확률로 한 번만 계산한다(통계가 있는 나라의 출생아 기준)."""
        if getattr(self, "_world_cache", None) is None:
            eco = [self.probability(Target(economy=b)) for b in ECONOMIES]
            surv = {s: [self.probability(Target(sex=s, survival=o)) for o in SURVIVALS] for s in SEXES}
            self._world_cache = {
                "economy": ([(b, o.p or 0.0) for b, o in zip(ECONOMIES, eco)], eco[0].coverage),
                "survival": {s: ([(v, o.p or 0.0) for v, o in zip(SURVIVALS, odds)], odds[0].coverage)
                             for s, odds in surv.items()},
            }
        return self._world_cache  # type: ignore[return-value]

    def _headline(self, steps: Tuple[Step, ...]) -> Optional[Headline]:
        values = {s.node: s for s in steps}
        iso3, sex = values["country"].value or "", values["sex"].value or ""
        survival, economy = values["survival"].value, values["economy"].value
        kind = choose_headline(survival, economy)
        if kind is None:
            return None
        world = self._world_tables()
        if kind == "economy":
            probs, coverage = world["economy"]  # type: ignore[index]
            country = self._eco[iso3].probs  # type: ignore[union-attr]
            value, year = economy or "", values["economy"].year
        else:
            probs, coverage = world["survival"][sex]  # type: ignore[index]
            country = self._surv[(iso3, sex)].probs  # type: ignore[union-attr]
            value, year = survival or "", values["survival"].year
        return Headline(node=kind, value=value, country=share_of(kind, country, value),
                        world=share_of(kind, probs, value) if coverage else None,
                        world_coverage=coverage, year=year)

    # ── 역확률 ────────────────────────────────────────────
    def _covered(self, c: Country, target: Target, sexes: Sequence[str]) -> bool:
        if (target.survival or target.adult) and any(self._surv[(c.iso3, s)] is None for s in sexes):
            return False
        if target.economy and self._eco[c.iso3] is None:
            return False
        return True

    def _survival_factor(self, iso3: str, sex: str, target: Target) -> float:
        surv = self._surv[(iso3, sex)]
        if target.adult:  # 어른의 칸을 물으면 다섯 살까지 살아남아야 한다
            if target.survival not in (None, "survived_5"):
                return 0.0
            return surv.p("survived_5")  # type: ignore[union-attr]
        if target.survival:
            return surv.p(target.survival)  # type: ignore[union-attr]
        return 1.0

    def _korea_factor(self, sex: str, target: Target) -> float:
        """P(시도·고용·직업 조건 | 대한민국, 성별, 다섯 살까지 생존)"""
        codes = [target.province] if target.province else self._province_codes
        total = 0.0
        for code in codes:
            p = self._prov[sex].p(code or "")
            if target.occupation:
                if target.employment == "not_employed":
                    return 0.0
                emp, occ = self._emp[(code, sex)], self._occ[(code, sex)]
                p *= (emp.p("employed") if emp else 0.0) * (occ.p(target.occupation) if occ else 0.0)
            elif target.employment:
                emp = self._emp[(code, sex)]
                p *= emp.p(target.employment) if emp else 0.0
            total += p
        return total

    def _f(self, c: Country, target: Target, sexes: Sequence[str]) -> float:
        """P(국가 아래 칸들의 조건 | 국가 c)"""
        total = 0.0
        for s in sexes:
            p = self._sex[c.iso3].p(s) * self._survival_factor(c.iso3, s, target)
            if target.korean:
                p *= self._korea_factor(s, target)
            total += p
        if target.economy:
            total *= self._eco[c.iso3].p(target.economy)  # type: ignore[union-attr]
        return total

    def probability(self, target: Target) -> Odds:
        """조건의 정확한 확률. 통계가 있는 국가의 출생아만을 모집단으로 삼고, 그 비율을 coverage로 알린다."""
        target = self.check_target(target)
        sexes = (target.sex,) if target.sex else SEXES

        if target.korean:
            if not self._korea_on:
                return Odds(target, None, 0.0, reason="한국 상세 통계가 없다")
            if target.country not in (None, KOREA_ISO3):
                return Odds(target, 0.0, 1.0, reason="시도·고용·직업은 대한민국에서 태어났을 때만 있다")
            target = Target(KOREA_ISO3, target.sex, target.survival, target.economy,
                            target.province, target.employment, target.occupation)

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
            return Odds(target, None, covered_mass, reason=f"이 나라에는 {', '.join(missing) or 'survival'} 통계가 없다")
        if covered_mass == 0:
            return Odds(target, None, 0.0, reason="조건에 맞는 통계가 있는 나라가 없다")

        steps = self._explain(target, sexes, covered_mass) if target.country else ()
        return Odds(target, numerator / covered_mass, covered_mass, steps)

    def _explain(self, target: Target, sexes: Sequence[str], covered_mass: float) -> Tuple[Step, ...]:
        """국가가 정해졌을 때 확률을 칸별 조건부 확률의 곱으로 풀어 쓴다.
        한국 칸은 성별과(고용·직업이면) 시도까지 정해졌을 때만 칸별로 풀 수 있다 — 아니면 풀이 없이 확률만."""
        c = self._by_iso3[target.country or ""]
        if target.korean and (not target.sex or (target.adult and not target.province)):
            return ()
        steps = [Step("country", c.iso3, self._country_p[c.iso3] / covered_mass, year=self._year_of("country", c, None))]
        if target.sex:
            steps.append(Step("sex", target.sex, self._sex[c.iso3].p(target.sex), self._sex[c.iso3].assumed,
                              year=self._year_of("sex", c, target.sex)))
        if target.survival or target.adult:
            value = "survived_5" if target.adult else target.survival
            p = sum(self._sex[c.iso3].p(s) * self._survival_factor(c.iso3, s, target) for s in sexes) / sum(
                self._sex[c.iso3].p(s) for s in sexes
            )
            steps.append(Step("survival", value, p, year=self._year_of("survival", c, target.sex or sexes[0])))
        if target.economy:
            steps.append(Step("economy", target.economy, self._eco[c.iso3].p(target.economy),  # type: ignore[union-attr]
                              year=self._year_of("economy", c, None)))
        if target.korean:
            sex = target.sex or ""
            if target.province:
                steps.append(Step("province", target.province, self._prov[sex].p(target.province)))
            if target.adult:
                emp = self._emp[(target.province, sex)]
                value = "employed" if target.occupation else target.employment
                steps.append(Step("employment", value, emp.p(value or "") if emp else 0.0))
            if target.occupation:
                occ = self._occ[(target.province, sex)]
                steps.append(Step("occupation", target.occupation, occ.p(target.occupation) if occ else 0.0))
            elif not target.adult and not target.province:
                return ()
        return tuple(steps)
