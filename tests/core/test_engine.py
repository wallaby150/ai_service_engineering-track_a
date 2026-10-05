from __future__ import annotations

import math

import pytest

from core.engine import Target, tries_needed
from core.errors import UnknownValue
from tests.helpers import fits

N = 40_000


def test_same_seed_same_life(engine):
    a, b = engine.sample(1234), engine.sample(1234)
    assert a.steps == b.steps


def test_seeds_differ(engine):
    lives = {engine.sample(s).steps for s in range(200)}
    assert len(lives) > 5


def test_fixed_country(engine):
    for s in range(50):
        assert engine.sample(s, country="ccc").value("country") == "CCC"


def test_unknown_country_lists_what_is_allowed(engine):
    with pytest.raises(UnknownValue) as e:
        engine.sample(1, country="ZZZ")
    assert "AAA" in str(e.value)


def test_unknown_value_in_target(engine):
    with pytest.raises(UnknownValue):
        engine.probability(Target(survival="immortal"))


def test_country_frequencies_match_births(engine):
    observed = [engine.sample(s).value("country") for s in range(N)]
    assert fits(observed, {"AAA": 0.6, "BBB": 0.3, "CCC": 0.1})


def test_survival_frequencies_match_exact_probability(engine):
    observed = [engine.sample(s).value("survival") for s in range(N)]
    expected = {v: engine.probability(Target(survival=v)).p for v in ("infant_death", "child_death", "survived_5")}
    assert sum(expected.values()) == pytest.approx(1)
    assert fits(observed, expected)


def test_economy_none_where_data_missing(engine):
    life = engine.sample(7, country="BBB")
    assert life.value("economy") is None
    assert not life.complete


def test_joint_p_is_product_of_steps(engine):
    life = engine.sample(42, country="AAA")
    assert life.joint_p == pytest.approx(math.prod(s.p for s in life.steps))


def test_everything_has_probability_one(engine):
    odds = engine.probability(Target())
    assert odds.p == pytest.approx(1)
    assert odds.coverage == pytest.approx(1)


def test_partition_sums_to_one(engine):
    total = sum(
        engine.probability(Target(sex=s, survival=v)).p
        for s in ("male", "female")
        for v in ("infant_death", "child_death", "survived_5")
    )
    assert total == pytest.approx(1)


def test_exact_value_for_one_path(engine):
    odds = engine.probability(Target(country="AAA", sex="female", survival="survived_5"))
    assert odds.p == pytest.approx(0.6 * 0.5 * 0.92)
    assert math.prod(s.p for s in odds.steps) == pytest.approx(odds.p)


def test_economy_target_counts_only_countries_with_data(engine):
    odds = engine.probability(Target(economy="below_3_00"))
    assert odds.coverage == pytest.approx(0.7)  # BBB(0.3)는 경제 통계가 없다
    assert odds.p == pytest.approx((0.6 * 0.1 + 0.1 * 0.0) / 0.7)


def test_country_without_data_says_so(engine):
    odds = engine.probability(Target(country="BBB", economy="above_8_30"))
    assert odds.p is None
    assert "economy" in odds.reason


def test_monte_carlo_agrees_with_exact(engine):
    target = Target(sex="female", survival="survived_5")
    hits = sum(target.matches({s.node: s.value for s in engine.sample(seed).steps}) for seed in range(N))
    p = engine.probability(target).p
    sigma = math.sqrt(p * (1 - p) / N)
    assert abs(hits / N - p) < 5 * sigma


@pytest.mark.parametrize(
    "p, q, expected",
    [(0.5, 0.5, 1), (0.01, 0.9, 230), (0.0, 0.5, None), (1.0, 0.9, 1), (0.1, 0.5, 7)],
)
def test_tries_needed(p, q, expected):
    assert tries_needed(p, q) == expected


def test_sample_until_finds_a_match(engine):
    target = Target(sex="male", survival="infant_death")
    result = engine.sample_until(target, seed=0, max_tries=10_000)
    assert result.found
    assert result.life.value("sex") == "male"
    assert result.life.value("survival") == "infant_death"
    assert engine.sample(result.life.seed).steps == result.life.steps  # 그 시드로 다시 뽑으면 같은 인생


def test_sample_until_stops_at_the_cap(engine):
    impossible = Target(country="CCC", economy="below_3_00")  # CCC의 극빈율은 0%
    result = engine.sample_until(impossible, seed=0, max_tries=500)
    assert not result.found
    assert result.tries == 500
