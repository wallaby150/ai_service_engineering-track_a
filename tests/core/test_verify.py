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
