"""AI 해석가(ReWOO): 화면에 없는 것을 말하는가, 숫자는 근거에 있는가, 실패하면 템플릿만 남는가."""

from __future__ import annotations

import pytest

from ai.llm import Ledger, LlmClient
from ai.narrator_llm import HEADLINE_METRIC, MAX_OVERLAP, LlmNarrator
from core.context import world_comparison
from core.narrator_scripted import ScriptedNarrator
from tests.ai.fakes import ScriptedLLM, response

PLAN = {"steps": [  # 계획 상한은 3단계
    {"tool": "world_comparison", "metric": "life_expectancy", "why": "세계와 비교"},
    {"tool": "world_comparison", "metric": "life_expectancy", "why": "중복"},
    {"tool": "region_peers", "metric": "life_expectancy", "why": "이웃 나라 — metric은 쓸모없다"},
]}


def make(engine, responses, limit=1.0):
    llm = ScriptedLLM(responses)
    client = LlmClient("fake/model", ledger=Ledger(limit), completion_fn=llm, cost_fn=lambda r: 0.001)
    return LlmNarrator(client, engine.snapshot, ScriptedNarrator()), llm


def other_names(engine, life):
    return sorted({p.country.name_ko for p in engine.same_moment(life.seed)} - {life.country.name_ko})


@pytest.fixture
def life(engine):
    # 같은 순간 4명 가운데 다른 나라 사람이 둘 이상인 인생 — 대비를 만들 재료가 있다
    return next(engine.sample(s, country="AAA") for s in range(500)
                if engine.sample(s, country="AAA").value("survival") == "survived_5"
                and len(other_names(engine, engine.sample(s, country="AAA"))) >= 2)


def interpretation(engine, life):
    """화면에 없는 근거 둘 이상(같은 순간 다른 나라 이름, 세계 배율)으로 쓴 원고.
    배율은 코드가 늘 넣는 조회(위치 한 줄의 지표)에서 가져온다."""
    names = other_names(engine, life)
    metric = HEADLINE_METRIC[life.headline.node]
    ratio = world_comparison(engine.snapshot, life.country.iso3, metric)["ratio_to_world"]
    return {"title": "같은 순간, 다른 출발",
            "paragraphs": [f"같은 순간 {names[0]}와 {names[1]}에서도 아이가 첫숨을 쉬었습니다.",
                           f"세계 평균과 견주면 이 나라의 그 비율은 {ratio}배입니다."],
            "facts_used": ["country", "not_a_fact"]}


def test_interpreter_gets_screen_and_required_lookups(engine, life):
    narrator, llm = make(engine, [response(PLAN), response(interpretation(engine, life))])
    report = narrator.story(life)
    assert report.narrative.narrator == "llm"
    assert len(llm.calls) == 2  # 계획 1 + 작성 1
    tools = [(s["tool"], s["metric"]) for s in report.plan]
    assert tools[:2] == [("world_comparison", "life_expectancy"), ("region_peers", None)]  # 중복·쓸모없는 인자는 뺐다
    assert ("world_comparison", "poverty_3_00") in tools  # 위치 한 줄(경제)의 지표는 코드가 넣는다
    prompt = llm.calls[1]["messages"][0]["content"]
    assert "[화면에 이미 있는 글]" in prompt and ScriptedNarrator().narrate(life).paragraphs[0] in prompt
    assert "<<<TOOL_RESULT SAME_MOMENT>>>" in prompt
    assert report.narrative.facts_used == ("country",)  # 없는 키는 버린다
    assert report.overlap[0] <= MAX_OVERLAP and len(report.new_evidence[0]) >= 2


def test_repeating_the_screen_is_sent_back(engine, life):
    repeat = {"title": "다시 말하기", "paragraphs": list(ScriptedNarrator().narrate(life).paragraphs)}
    narrator, llm = make(engine, [response(PLAN), response(repeat), response(interpretation(engine, life))])
    report = narrator.story(life)
    assert report.narrative.narrator == "llm" and report.attempts == 2
    assert report.overlap[0] > MAX_OVERLAP
    assert "되풀이" in llm.calls[2]["messages"][0]["content"]


def test_no_new_evidence_is_sent_back(engine, life):
    vague = {"title": "막연한 글", "paragraphs": ["삶은 우연으로 시작됩니다.", "어디서 태어나느냐가 많은 것을 정합니다."]}
    narrator, llm = make(engine, [response(PLAN), response(vague), response(interpretation(engine, life))])
    report = narrator.story(life)
    assert report.narrative.narrator == "llm" and report.new_evidence[0] == []
    assert "근거가 모자란다" in llm.calls[2]["messages"][0]["content"]


def test_invented_number_gets_one_rewrite_then_passes(engine, life):
    bad = interpretation(engine, life)
    bad["paragraphs"].append("1,000명 중 777.7명이 행복합니다.")
    narrator, llm = make(engine, [response(PLAN), response(bad), response(interpretation(engine, life))])
    report = narrator.story(life)
    assert report.narrative.narrator == "llm" and report.violations[0] == [777.7]
    assert "777.7" in llm.calls[2]["messages"][0]["content"]


def test_still_failing_leaves_only_the_template(engine, life):
    repeat = {"title": "다시 말하기", "paragraphs": list(ScriptedNarrator().narrate(life).paragraphs)}
    narrator, _ = make(engine, [response(PLAN), response(repeat), response(repeat)])
    n = narrator.story(life).narrative
    assert n.narrator == "scripted" and "화면에 없는 해석" in n.note


def test_broken_json_is_retried_with_the_error(engine, life):
    narrator, llm = make(engine, [response("{not json"), response(PLAN), response(interpretation(engine, life))])
    assert narrator.story(life).narrative.narrator == "llm"
    assert "스키마에 맞지 않았다" in llm.calls[1]["messages"][-1]["content"]


def test_provider_failure_falls_back(engine, life):
    narrator, _ = make(engine, [RuntimeError("503")])
    n = narrator.story(life).narrative
    assert n.narrator == "scripted" and "쓰지 못해" in n.note


def test_rate_limit_says_try_again_later(engine, life):
    class RateLimitError(Exception):
        pass

    narrator, _ = make(engine, [RateLimitError("429 quota")])
    n = narrator.story(life).narrative
    assert n.narrator == "scripted" and "잠시 후" in n.note


def test_budget_guard_stops_calling(engine, life):
    narrator, llm = make(engine, [response(PLAN), response(interpretation(engine, life))], limit=0.001)
    report = narrator.story(life)  # 계획 한 번($0.001)으로 상한에 닿는다
    assert report.narrative.narrator == "scripted" and "예산" in report.narrative.note
    assert len(llm.calls) == 1


def test_cost_is_recorded(engine, life):
    narrator, _ = make(engine, [response(PLAN), response(interpretation(engine, life))])
    report = narrator.story(life)
    assert report.cost_usd == pytest.approx(0.002)
    assert [c.role for c in report.calls] == ["planner", "solver"]
