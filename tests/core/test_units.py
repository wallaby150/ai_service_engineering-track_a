from __future__ import annotations

import pytest

from core.units import MINUTES_PER_YEAR, births_per_minute, minutes_per_birth, one_in


@pytest.mark.parametrize("p, n", [(0.5, 2), (1.0, 1), (0.068, 15), (0.0018, 556), (1 / 3, 3), (0.9, 1)])
def test_one_in_rounds_to_people(p, n):
    assert one_in(p) == n


@pytest.mark.parametrize("p", [None, 0.0, -0.1])
def test_one_in_has_no_answer_without_a_probability(p):
    assert one_in(p) is None


def test_births_per_minute_and_back():
    assert births_per_minute(int(MINUTES_PER_YEAR)) == pytest.approx(1.0, abs=1e-6)
    assert births_per_minute(242_917) == pytest.approx(0.4618, abs=1e-4)  # 한국: 1분에 약 0.46명
    assert minutes_per_birth(242_917) == pytest.approx(2.165, abs=1e-3)   # 약 2.2분에 1명


@pytest.mark.parametrize("births", [None, 0, -5])
def test_rates_need_births(births):
    assert births_per_minute(births) is None and minutes_per_birth(births) is None
