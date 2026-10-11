from __future__ import annotations

import pytest

from core.context import country_profile, region_peers, run_tool, world_comparison


def test_profile_carries_the_numbers(snapshot):
    p = country_profile(snapshot, "AAA")
    assert p["country"] == "가나라"
    assert p["share_of_world_births_pct"] == 60.0
    assert p["u5mr_female_per_1000"] == 80.0


def test_world_comparison_is_birth_weighted_and_precomputes_ratio(snapshot):
    w = world_comparison(snapshot, "AAA", "u5mr")
    # AAA (150+80)/2=115 ×600, BBB (6+5)/2=5.5 ×300, CCC 30 ×100 → 가중 평균 73.65
    assert w["world_average"] == pytest.approx(73.65, abs=0.051)
    assert w["ratio_to_world"] == pytest.approx(round(115 / 73.65, 1))
    assert w["rank_high_to_low"] == 1


def test_missing_data_is_left_out_not_zeroed(snapshot):
    w = world_comparison(snapshot, "BBB", "poverty_3_00")
    assert w["country_value"] is None and w["countries_with_data"] == 2


def test_region_peers_has_rows(snapshot):
    assert region_peers(snapshot, "AAA")["peers"][0]["country"] == "가나라"


def test_run_tool_explains_bad_requests(snapshot):
    assert "가능한 조회" in run_tool(snapshot, "delete_everything", "AAA")["error"]
    assert "가능한 값" in run_tool(snapshot, "world_comparison", "AAA", "height")["error"]


def test_comparison_profile_matches_the_snapshot(snapshot):
    from core.context import comparison_profile

    p = comparison_profile(snapshot, "AAA")
    assert p["by_sex"]["female"]["u5mr_per_1000"] == 80.0
    assert p["by_sex"]["male"]["life_expectancy"] == 60.0
    assert p["pct_below_3_00"] == 10.0 and p["economy_year"] == 2022
    assert p["share_of_world_births_pct"] == 60.0


def test_comparison_profile_keeps_missing_as_none(snapshot):
    from core.context import comparison_profile

    p = comparison_profile(snapshot, "BBB")
    assert p["pct_below_3_00"] is None and p["economy_year"] is None
    assert comparison_profile(snapshot, "CCC")["by_sex"]["male"]["life_expectancy"] is None


def test_all_profiles_cover_every_country_and_hold_no_differences(snapshot):
    from core.context import all_profiles

    profiles = all_profiles(snapshot)
    assert {p["iso3"] for p in profiles} == {"AAA", "BBB", "CCC"}
    assert not any("diff" in k or "ratio" in k for p in profiles for k in p)
