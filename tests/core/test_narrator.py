from __future__ import annotations

import pytest

from core.facts import facts_of
from core.narrator import Narrator
from core.narrator_scripted import ScriptedNarrator


@pytest.fixture
def narrator() -> Narrator:
    return ScriptedNarrator()


def test_stand_in_says_who_wrote_it(engine, narrator):
    n = narrator.narrate(engine.sample(1))
    assert n.narrator == "scripted"


def test_uses_only_facts_that_exist(engine, narrator):
    for seed in range(300):
        life = engine.sample(seed)
        facts = facts_of(life)
        n = narrator.narrate(life)
        for key in n.facts_used:
            assert key in facts and facts[key] is not None, (seed, key)


def test_title_names_the_country(engine, narrator):
    n = narrator.narrate(engine.sample(3, country="AAA"))
    assert n.title.startswith("가나라의")


def test_missing_economy_is_said_out_loud(engine, narrator):
    n = narrator.narrate(engine.sample(5, country="BBB"))
    assert any("알 수 없습니다" in p for p in n.paragraphs)
    assert "economy" not in n.facts_used


def test_same_life_same_story(engine, narrator):
    life = engine.sample(77)
    assert narrator.narrate(life) == narrator.narrate(life)


def test_deaths_are_told_with_care(engine, narrator):
    found = 0
    for seed in range(3000):
        life = engine.sample(seed, country="AAA")
        if life.value("survival") in ("infant_death", "child_death"):
            assert "한 사람의 삶" in narrator.narrate(life).paragraphs[-1]
            found += 1
    assert found > 0


def test_korean_life_gets_province_and_adult_paragraphs(korea_engine, narrator):
    seen_job = seen_idle = False
    for seed in range(400):
        life = korea_engine.sample(seed, country="KOR")
        n = narrator.narrate(life)
        facts = facts_of(life)
        assert n.title.startswith("대한민국 ")
        assert all(facts.get(k) is not None for k in n.facts_used)
        text = " ".join(n.paragraphs)
        if life.value("occupation"):
            seen_job = True
            assert facts["occupation"] in text
        elif life.value("employment") == "not_employed":
            seen_idle = True
            assert "일하지 않고" in text
        if life.value("survival") != "survived_5":
            assert "어른이 된" not in text
    assert seen_job and seen_idle


def test_birth_paragraph_says_one_in_n_and_pace(engine, narrator):
    life = engine.sample(3, country="AAA")
    facts = facts_of(life)
    assert facts["country_one_in"] == 2  # 가짜 스냅샷에서 AAA는 출생아의 60%
    first = narrator.narrate(life).paragraphs[0]
    assert "2번에 1번꼴" in first and "분에 1명" in first  # 출생아 600명/년 — 몇 분에 한 명


def test_position_paragraph_follows_the_headline_rule(engine, narrator):
    seen = set()
    for seed in range(600):
        life = engine.sample(seed, country="AAA")
        text = " ".join(narrator.narrate(life).paragraphs)
        assert "같은 해" not in text
        if life.value("survival") in ("infant_death", "child_death"):
            assert "같은 일을 겪습니다" in text
            seen.add("death")
        else:
            assert "당신보다 낮은 소비 구간" in text
            assert text.count("같은 구간") == 2  # 나라 안 한 번, 세계 한 번 — 경제 문단과 겹치지 않는다
            seen.add("economy")
    assert seen == {"death", "economy"}


def test_no_economy_means_survival_position(engine, narrator):
    life = next(engine.sample(s, country="BBB") for s in range(500)
                if engine.sample(s, country="BBB").value("survival") == "survived_5")
    assert "다섯 살을 맞지 못합니다" in narrator.narrate(life).paragraphs[-1] or \
        any("세계로 넓히면" in p for p in narrator.narrate(life).paragraphs)


def test_peer_facts_hold_only_drawn_values(engine):
    from core.facts import peer_facts

    life = engine.sample(5, country="BBB")
    p = peer_facts(life)
    assert p["country"] == "나나라" and "economy" not in p  # BBB는 경제 통계가 없다 — 키를 넣지 않는다
