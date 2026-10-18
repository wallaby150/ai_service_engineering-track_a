"""세계 어딘가의 다른 4명(화면 이름, 코드는 same_moment): 결정적이고, 본 인생을 바꾸지 않으며, 통계대로 뽑힌다."""

from __future__ import annotations

from core.engine import MAX_SEED, same_moment_seeds
from tests.helpers import fits

N = 40_000


def test_seeds_are_pinned():
    # 플랫폼·Python 버전이 달라도 같아야 공유 링크가 같은 4명을 보여 준다(CI는 3.9와 3.12)
    assert same_moment_seeds(0) == [1466545855, 1711608148, 232458492, 937080492]


def test_seeds_are_distinct_in_range_and_not_the_main_seed():
    for seed in (0, 1, 12345, MAX_SEED):
        seeds = same_moment_seeds(seed)
        assert len(set(seeds)) == 4 and seed not in seeds
        assert all(0 <= s <= MAX_SEED for s in seeds)


def test_main_life_is_untouched(engine):
    before = engine.sample(42)
    engine.same_moment(42)
    assert engine.sample(42) == before


def test_peers_replay_from_their_own_seeds(engine):
    peers = engine.same_moment(7)
    assert [p.steps for p in peers] == [engine.sample(p.seed).steps for p in peers]


def test_peers_are_drawn_worldwide_by_births(engine):
    countries = [p.value("country") for seed in range(N // 4) for p in engine.same_moment(seed)]
    assert fits(countries, {"AAA": 0.6, "BBB": 0.3, "CCC": 0.1})
