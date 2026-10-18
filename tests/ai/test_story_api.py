from __future__ import annotations

from fastapi.testclient import TestClient

from ai.llm import Ledger, LlmClient
from ai.narrator_llm import LlmNarrator
from api.main import create_app
from core.narrator_scripted import ScriptedNarrator
from tests.ai.fakes import ScriptedLLM, response
from tests.ai.test_narrator_llm import interpretation, other_names


def test_story_endpoint_reports_plan_calls_and_cost(engine):
    seed = next(s for s in range(1000) if engine.sample(s, country="AAA").value("survival") == "survived_5"
                and len(other_names(engine, engine.sample(s, country="AAA"))) >= 2)
    life = engine.sample(seed, country="AAA")
    llm = ScriptedLLM([
        response({"steps": [{"tool": "country_profile", "why": "기본"}]}),
        response(interpretation(engine, life)),
    ])
    story = LlmNarrator(LlmClient("fake/m", ledger=Ledger(1), completion_fn=llm, cost_fn=lambda r: 0.002),
                        engine.snapshot, ScriptedNarrator())
    client = TestClient(create_app(engine=engine, story_narrator=story))

    assert client.get("/api/config").json()["mode"] == "live"
    r = client.post("/api/story", json={"seed": seed, "country": "AAA"}).json()
    assert r["narrative"]["narrator"] == "llm"
    assert [p["tool"] for p in r["plan"]] == ["country_profile", "world_comparison", "region_peers"]
    assert [c["role"] for c in r["llm_calls"]] == ["planner", "solver"]
    assert r["cost_usd"] == 0.004 and r["attempts"] == 1 and r["cached"] is False
    again = client.post("/api/story", json={"seed": seed, "country": "AAA"}).json()
    assert again["cached"] is True and again["llm_calls"] == [] and again["narrative"] == r["narrative"]


def test_story_keeps_simulate_fast_and_offline(engine):
    llm = ScriptedLLM([])  # 불리면 pop에서 터진다
    story = LlmNarrator(LlmClient("fake/m", completion_fn=llm), engine.snapshot, ScriptedNarrator())
    client = TestClient(create_app(engine=engine, story_narrator=story))
    assert client.post("/api/simulate", json={"seed": 1}).json()["narrative"]["narrator"] == "scripted"
    assert llm.calls == []
