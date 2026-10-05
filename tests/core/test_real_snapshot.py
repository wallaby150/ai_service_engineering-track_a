"""커밋된 실제 스냅샷이 엔진의 전제를 지키는지."""

from __future__ import annotations

import pytest

from core.engine import Engine, Target
from core.model import SEXES, economy_dist, survival_dist
from core.stats import load_snapshot


@pytest.fixture(scope="module")
def real():
    return load_snapshot()


def test_snapshot_has_the_world(real):
    assert len(real.countries) > 200
    assert real.get("KOR").name_ko == "대한민국"
    assert 100_000_000 < real.total_births < 170_000_000


def test_every_distribution_is_a_distribution(real):
    for c in real.countries:
        for s in SEXES:
            d = survival_dist(c, s)
            if d:
                assert all(p >= 0 for _, p in d.probs), c.iso3
                assert sum(p for _, p in d.probs) == pytest.approx(1)
        e = economy_dist(c)
        if e:
            assert all(p >= -1e-12 for _, p in e.probs), c.iso3
            assert sum(p for _, p in e.probs) == pytest.approx(1)


def test_engine_runs_on_real_data(real):
    engine = Engine(real)
    assert engine.probability(Target()).p == pytest.approx(1)
    korea = engine.probability(Target(country="KOR"))
    assert 0.001 < korea.p < 0.003
