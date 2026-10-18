from __future__ import annotations

from core.verify import allowed_numbers, numbers_in, unsupported_numbers


def test_numbers_in_reads_commas_and_decimals():
    assert numbers_in("한 해 약 4,263,170명, 1,000명 중 38.5명, $3.00") == [4263170.0, 1000.0, 38.5, 3.0]


def test_supported_story_passes():
    facts = {"u5mr_per_1000": 2.5, "births_per_year": 242917, "life_expectancy": 86.6}
    text = "1,000명 중 2.5명은 다섯 살을 맞지 못합니다. 997.5명 가운데 한 명입니다. 기대수명 86.6세, 한 해 약 24만 명."
    assert unsupported_numbers(text, allowed_numbers(facts)) == []


def test_invented_number_is_caught():
    facts = {"u5mr_per_1000": 2.5}
    assert unsupported_numbers("1,000명 중 3.7명이 사망합니다.", allowed_numbers(facts)) == [3.7]


def test_rounding_is_tolerated():
    assert unsupported_numbers("기대수명은 약 87세입니다", allowed_numbers({"le": 86.6})) == []


def test_missing_required_number():
    from core.verify import missing_required

    assert missing_required("1,000명 중 23명이 첫돌을 맞지 못합니다", [23.3]) == []
    assert missing_required("첫돌을 맞지 못했습니다", [23.3]) == [23.3]


def test_year_used_as_a_count_is_caught():
    from core.verify import allowed_years

    facts = {"province_births_year": 2025, "employment_period": "2025년 하반기", "births_per_year": 242917}
    allowed, years = allowed_numbers(facts), allowed_years(facts)
    assert unsupported_numbers("전북에서는 2,025명이 태어났다", allowed, years) == [2025.0]
    assert unsupported_numbers("2025년 하반기 기준, 한 해 242,917명", allowed, years) == []
    assert unsupported_numbers("2019년에는", allowed, years) == [2019.0]


def test_overlap_ratio_measures_repetition():
    from core.verify import overlap_ratio

    screen = "대한민국에서 여자아이로 태어났습니다. 이 나라 여성의 기대수명은 86.6세입니다."
    assert overlap_ratio("대한민국에서 여자아이로 태어났습니다.", screen) == 1.0
    assert overlap_ratio("같은 순간 콩고민주공화국의 남자아이는 첫돌을 맞지 못했습니다.", screen) < 0.2
    assert overlap_ratio("", screen) == 0.0


def test_new_evidence_counts_only_what_the_screen_lacks():
    from core.verify import new_evidence

    novel = allowed_numbers({"ratio_to_world": 1.2, "rank_high_to_low": 13}) - allowed_numbers({"le": 86.6})
    text = "기대수명은 세계 평균의 1.2배, 높은 쪽에서 13번째입니다. 같은 순간 이집트에서도 아이가 태어났습니다. 86.6세."
    assert new_evidence(text, novel, ["이집트", "브라질"]) == ["1.2", "13", "이집트"]
