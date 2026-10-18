"""숫자는 참조로: 근거 목록, 참조 채우기, 문장 단위로 버리기."""

from __future__ import annotations

import pytest

from core.context import region_peers, world_comparison
from core.facts import facts_of, peer_facts
from core.references import (
    Ref, build_catalog, catalog_lines, check_sentence, novel_used, peer_lines, render,
)

R = {
    "R1": Ref("R1", "가나라의 5세 미만 사망률이 세계 평균의 몇 배인지", 1.56, "배", 1, True),
    "R2": Ref("R2", "가나라에서 한 해 태어나는 아이 수", 242917, "명", 0, False),
    "R3": Ref("R3", "가나라 순위", 13, "번째", 0, True),
}


def test_ref_text_formats_value_and_unit():
    assert R["R1"].text() == "1.6배"
    assert R["R2"].text() == "242,917명"
    assert Ref("x", "", 70.0, "세", 1, True).text() == "70세"


def test_render_fills_references_and_drops_double_units():
    out = render(["세계 평균의 {R1}배입니다. 높은 쪽에서 {R3}입니다."], list(R.values()))
    assert out.paragraphs == ["세계 평균의 1.6배입니다. 높은 쪽에서 13번째입니다."]
    assert out.used == ["R1", "R3"] and out.dropped == []


@pytest.mark.parametrize("sentence, reason", [
    ("세계 평균의 {R9}입니다.", "없는 참조"),
    ("1,000명 중 26.7명이 숨집니다.", "숫자를 직접 씀"),
    ("2024년 기준입니다.", "숫자를 직접 씀"),
    ("아쉽게도 {R1}입니다.", "쓰지 않는 말"),
    ("열심히 살아야 합니다.", "쓰지 않는 말"),
])
def test_bad_sentences_are_named(sentence, reason):
    assert reason in check_sentence(sentence, R)


def test_free_numbers_are_allowed():
    assert check_sentence("100명 중 {R1}, 1,000명 중이라면 달라집니다.", R) is None
    assert check_sentence("하루 $3.00 미만의 가정입니다.", R) is None


def test_only_the_bad_sentence_is_dropped():
    out = render(["좋은 문장 {R1}입니다. 나쁜 문장 7.7명입니다.", "다음 문단 {R3}입니다."], list(R.values()))
    assert out.paragraphs == ["좋은 문장 1.6배입니다.", "다음 문단 13번째입니다."]
    assert out.dropped == [("나쁜 문장 7.7명입니다.", "숫자를 직접 씀: 7.7")]


def test_catalog_marks_screen_values_and_carries_meaning(engine, snapshot):
    life = engine.sample(3, country="AAA")
    facts = facts_of(life)
    lookups = [("world_comparison", "u5mr", world_comparison(snapshot, "AAA", "u5mr")),
               ("region_peers", None, region_peers(snapshot, "AAA"))]
    peers = [peer_facts(p) for p in engine.same_moment(3)]
    refs = build_catalog(facts, lookups, peers)
    births = next(r for r in refs if "한 해 태어나는" in r.meaning)
    assert births.meaning.startswith("가나라") and not births.novel
    ratio = next(r for r in refs if "몇 배" in r.meaning)
    assert ratio.novel and ratio.unit == "배"
    assert all(r.meaning for r in refs) and len({r.id for r in refs}) == len(refs)
    assert not any("가나라(나라 평균)" in r.meaning for r in refs)  # 이웃 목록에서 자기 나라는 뺀다
    lines = catalog_lines(refs)
    assert any("(화면에 이미 있음)" in l for l in lines)
    assert peer_lines(peers)[0].startswith("S1: ")


def test_missing_values_never_become_references(engine, snapshot):
    facts = facts_of(engine.sample(1, country="BBB"))  # 경제 통계 없음
    refs = build_catalog(facts, [("world_comparison", "poverty_3_00",
                                   world_comparison(snapshot, "BBB", "poverty_3_00"))], [])
    assert not any("BBB" in r.meaning or r.value is None for r in refs)
    assert not any("나나라의 하루 $3.00" in r.meaning for r in refs)


def test_novel_used_counts_new_references_and_peer_names():
    out = render(["{R1}이고 {R2}입니다. 같은 순간 다나라에서도 태어났습니다."], list(R.values()))
    assert novel_used(out, list(R.values()), ["다나라", "라나라"]) == ["R1", "다나라"]
