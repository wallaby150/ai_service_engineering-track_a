from __future__ import annotations

import pytest

from core.model import DEFAULT_SEX_RATIO, country_dist, economy_dist, sex_dist, survival_dist


def test_country_share_follows_births(snapshot):
    assert dict(country_dist(snapshot).probs) == pytest.approx({"AAA": 0.6, "BBB": 0.3, "CCC": 0.1})


def test_sex_from_ratio(snapshot):
    d = sex_dist(snapshot.get("BBB"))
    assert d.p("male") == pytest.approx(1.1 / 2.1)
    assert d.p("female") == pytest.approx(1 / 2.1)
    assert not d.assumed


def test_missing_sex_ratio_is_assumed_not_zero(snapshot):
    d = sex_dist(snapshot.get("CCC"))
    assert d.assumed
    assert d.p("male") == pytest.approx(DEFAULT_SEX_RATIO / (1 + DEFAULT_SEX_RATIO))


def test_survival_splits_into_three(snapshot):
    d = survival_dist(snapshot.get("AAA"), "male")
    assert dict(d.probs) == pytest.approx({"infant_death": 0.10, "child_death": 0.05, "survived_5": 0.85})
    assert sum(p for _, p in d.probs) == pytest.approx(1)


def test_economy_bands_are_differences_of_cumulative_rates(snapshot):
    d = economy_dist(snapshot.get("AAA"))
    assert dict(d.probs) == pytest.approx(
        {"below_3_00": 0.1, "below_4_20": 0.2, "below_8_30": 0.3, "above_8_30": 0.4}
    )


def test_missing_economy_is_none(snapshot):
    assert economy_dist(snapshot.get("BBB")) is None
