"""한국 칸(v0.3): 시도 → 어른이 되어 일하는가 → 직업. 대한민국에서 태어났을 때만 열린다."""

from __future__ import annotations

import math

import pytest

from core.engine import Target
from core.errors import UnknownValue
from tests.helpers import fits

N = 40_000


def test_only_korea_opens_korean_nodes(korea_engine):
    for seed in range(300):
        life = korea_engine.sample(seed)
        has_province = life.value("province") is not None
        assert has_province == (life.value("country") == "KOR")


def test_children_who_died_have_no_adult_nodes(korea_engine):
    for seed in range(2000):
        life = korea_engine.sample(seed, country="KOR")
        nodes = [s.node for s in life.steps]
        if life.value("survival") != "survived_5":
            assert "employment" not in nodes and "occupation" not in nodes
        elif life.value("employment") == "not_employed":
            assert "occupation" not in nodes
        assert life.complete  # 열리지 않은 칸은 '통계 없음'이 아니다


def test_province_follows_births_of_the_same_sex(korea_engine):
    girls = [l.value("province") for l in (korea_engine.sample(s, country="KOR") for s in range(N))
             if l.value("sex") == "female"]
    assert fits(girls, {"11": 0.25, "39": 0.75})


def test_exact_value_for_a_full_korean_path(korea_engine):
    t = Target(country="KOR", sex="male", province="11", employment="employed", occupation="02")
    odds = korea_engine.probability(t)
    # KOR 0.4 × 남 0.5 × 생존 0.8 × 서울|남 0.75 × 고용 0.8 × 전문가 0.75
    assert odds.p == pytest.approx(0.4 * 0.5 * 0.8 * 0.75 * 0.8 * 0.75)
    assert math.prod(s.p for s in odds.steps) == pytest.approx(odds.p)


def test_korean_fields_imply_korea(korea_engine):
    assert korea_engine.probability(Target(province="39")).p == pytest.approx(
        korea_engine.probability(Target(country="KOR", province="39")).p
    )


def test_korean_fields_with_another_country_are_impossible(korea_engine):
    odds = korea_engine.probability(Target(country="AAA", province="11"))
    assert odds.p == 0.0 and "대한민국" in odds.reason


def test_adults_partition_the_survivors(korea_engine):
    survived = korea_engine.probability(Target(country="KOR", survival="survived_5")).p
    employed = korea_engine.probability(Target(employment="employed")).p
    not_employed = korea_engine.probability(Target(employment="not_employed")).p
    by_job = sum(korea_engine.probability(Target(occupation=o)).p for o in ("01", "02"))
    assert employed + not_employed == pytest.approx(survived)
    assert by_job == pytest.approx(employed)


def test_adult_target_with_a_death_is_impossible(korea_engine):
    assert korea_engine.probability(Target(survival="infant_death", employment="employed")).p == 0.0


def test_monte_carlo_agrees_on_occupation(korea_engine):
    target = Target(sex="female", occupation="02")
    hits = sum(target.matches({s.node: s.value for s in korea_engine.sample(seed).steps}) for seed in range(N))
    p = korea_engine.probability(target).p
    assert abs(hits / N - p) < 5 * math.sqrt(p * (1 - p) / N)


def test_unknown_province_lists_codes(korea_engine):
    with pytest.raises(UnknownValue) as e:
        korea_engine.probability(Target(province="99"))
    assert "39" in str(e.value)


def test_engine_without_korea_data_still_runs(engine):
    assert engine.probability(Target(province="11")).p is None
