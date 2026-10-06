from __future__ import annotations

import pytest

from ai.llm import Ledger, LlmClient
from ai.narrator_llm import LlmNarrator
from core.facts import facts_of
from core.narrator_scripted import ScriptedNarrator
from tests.ai.fakes import ScriptedLLM, response

PLAN = {"steps": [  # 계획 상한은 3단계
    {"tool": "world_comparison", "metric": "u5mr", "why": "세계와 비교"},
    {"tool": "world_comparison", "metric": "u5mr", "why": "중복"},
    {"tool": "region_peers", "metric": "life_expectancy", "why": "이웃 나라 — metric은 쓸모없다"},
]}


def make(engine, responses, limit=1.0):
    llm = ScriptedLLM(responses)
    client = LlmClient("fake/model", ledger=Ledger(limit), completion_fn=llm, cost_fn=lambda r: 0.001)
    return LlmNarrator(client, engine.snapshot, ScriptedNarrator()), llm


@pytest.fixture
def life(engine):
    return engine.sample(3, country="AAA")


def good_story(life):
    f = facts_of(life)
    return {"title": f"{f['country']}에서 온 이야기",
            "paragraphs": [f"당신은 {f['country']}에서 태어났습니다.", f"세계 아이 100명 중 {f['country_share_pct']}명이 이 나라에서 태어납니다."],
            "facts_used": ["country", "country_share_pct", "not_a_fact"]}


def test_rewoo_plans_once_executes_in_code_and_writes_once(engine, life):
    narrator, llm = make(engine, [response(PLAN), response(good_story(life))])
    report = narrator.story(life)
    assert report.narrative.narrator == "llm"
    assert len(llm.calls) == 2                           # 계획 1 + 작성 1
    assert [(s["tool"], s["metric"]) for s in report.plan] == [
        ("world_comparison", "u5mr"), ("region_peers", None)]  # 중복·쓸모없는 인자는 코드가 뺐다
    assert report.narrative.facts_used == ("country", "country_share_pct")             # 없는 키는 버린다
    assert llm.calls[1]["tool_choice"]["function"]["name"] == "emit_story"
    assert "<<<TOOL_RESULT E1>>>" in llm.calls[1]["messages"][0]["content"]             # 경계 마커


def test_invented_number_gets_one_rewrite_then_passes(engine, life):
    bad = good_story(life)
    bad["paragraphs"].append("1,000명 중 777.7명이 행복합니다.")
    narrator, llm = make(engine, [response(PLAN), response(bad), response(good_story(life))])
    report = narrator.story(life)
    assert report.narrative.narrator == "llm"
    assert report.attempts == 2 and report.violations[0] == [777.7]
    assert "777.7" in llm.calls[2]["messages"][0]["content"]                            # 위반이 다시 쓰기 지시에 실린다


def test_still_wrong_falls_back_to_template(engine, life):
    bad = good_story(life)
    bad["paragraphs"].append("평균 12345.6명입니다.")
    narrator, _ = make(engine, [response(PLAN), response(bad), response(bad)])
    report = narrator.story(life)
    assert report.narrative.narrator == "scripted"
    assert "근거에 없는 숫자" in report.narrative.note


def test_broken_json_is_retried_with_the_error(engine, life):
    narrator, llm = make(engine, [response("{not json"), response(PLAN), response(good_story(life))])
    assert narrator.story(life).narrative.narrator == "llm"
    assert "스키마에 맞지 않았다" in llm.calls[1]["messages"][-1]["content"]


def test_provider_failure_falls_back(engine, life):
    narrator, _ = make(engine, [RuntimeError("503")])
    n = narrator.story(life).narrative
    assert n.narrator == "scripted" and "쓰지 못해" in n.note


def test_budget_guard_stops_calling(engine, life):
    narrator, llm = make(engine, [response(PLAN), response(good_story(life))], limit=0.001)
    report = narrator.story(life)                       # 계획 한 번($0.001)으로 상한에 닿는다
    assert report.narrative.narrator == "scripted" and "예산" in report.narrative.note
    assert len(llm.calls) == 1


def test_cost_is_recorded(engine, life):
    narrator, _ = make(engine, [response(PLAN), response(good_story(life))])
    report = narrator.story(life)
    assert report.cost_usd == pytest.approx(0.002)
    assert [c.role for c in report.calls] == ["planner", "solver"]


def test_death_story_must_say_how_many_children_share_it(engine):
    life = next(engine.sample(s, country="AAA") for s in range(5000)
                if engine.sample(s, country="AAA").value("survival") == "infant_death")
    silent = {"title": "짧은 삶", "paragraphs": ["당신은 첫돌을 맞지 못했습니다.", "이 삶은 짧았습니다."],
              "facts_used": ["survival"]}                       # 사망률을 말하지 않은 원고
    told = good_story(life)
    imr = facts_of(life)["imr_per_1000"]
    told["paragraphs"].append(f"1,000명 중 {imr:g}명의 아기가 첫돌을 맞지 못합니다.")
    narrator, llm = make(engine, [response(PLAN), response(silent), response(told)])
    report = narrator.story(life)
    assert report.narrative.narrator == "llm" and report.attempts == 2
    assert report.violations[0] == [imr]
    assert "아이들의 수가 빠졌다" in llm.calls[2]["messages"][0]["content"]
