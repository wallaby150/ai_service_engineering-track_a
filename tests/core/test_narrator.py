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
    assert "2명 중 1명꼴" in first and "분에 1명" in first  # 출생아 600명/년 — 몇 분에 한 명
