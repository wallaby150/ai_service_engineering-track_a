"""출생 코호트 안의 위치 한 줄: 무엇을 요약할지 고르는 규칙과 비율."""

from __future__ import annotations

import pytest

from core.engine import Target
from core.position import choose_headline, share_of
from tests.helpers import fits

N = 40_000


@pytest.mark.parametrize("survival, economy, expected", [
    ("infant_death", "above_8_30", "survival"),   # 사망이 경제보다 무겁다
    ("child_death", None, "survival"),
    ("survived_5", "below_3_00", "economy"),
    ("survived_5", None, "survival"),             # 경제 통계가 없으면 생존
    (None, "below_4_20", "economy"),
    (None, None, None),                           # 말할 것이 없으면 말하지 않는다
])
def test_choose_headline_rule(survival, economy, expected):
    assert choose_headline(survival, economy) == expected


def test_share_splits_below_same_above():
    probs = [("below_3_00", 0.1), ("below_4_20", 0.2), ("below_8_30", 0.3), ("above_8_30", 0.4)]
    s = share_of("economy", probs, "below_8_30")
    assert (s.below, s.same, s.above) == pytest.approx((0.3, 0.3, 0.4))
    edge = share_of("economy", probs, "below_3_00")
    assert edge.below == 0 and edge.same == pytest.approx(0.1)


def test_survival_order_puts_deaths_below():
    s = share_of("survival", [("infant_death", 0.1), ("child_death", 0.05), ("survived_5", 0.85)], "survived_5")
    assert (s.below, s.same, s.above) == pytest.approx((0.15, 0.85, 0.0))


def test_life_headline_matches_country_distribution(engine):
    life = engine.sample(3, country="AAA")
    h = life.headline
    assert h.node == "economy" and h.year == "2022년"
    assert h.country.below + h.country.same + h.country.above == pytest.approx(1)


def test_world_share_equals_exact_probability(engine):
    life = next(engine.sample(s, country="AAA") for s in range(100)
                if engine.sample(s, country="AAA").value("economy") == "below_4_20")
    exact = engine.probability(Target(economy="below_4_20"))
    assert life.headline.world.same == pytest.approx(exact.p)
    assert life.headline.world_coverage == pytest.approx(0.7)  # BBB는 경제 통계가 없다


def test_world_share_matches_what_sampling_produces(engine):
    bands = [l.value("economy") for l in (engine.sample(s) for s in range(N)) if l.value("economy")]
    expected = {b: engine.probability(Target(economy=b)).p for b in
                ("below_3_00", "below_4_20", "below_8_30", "above_8_30")}
    assert fits(bands, expected)


def test_missing_economy_falls_back_to_survival(engine):
    h = engine.sample(2, country="BBB").headline
    assert h.node == "survival"


def test_headline_does_not_change_equality(engine):
    assert engine.sample(9) == engine.sample(9)
