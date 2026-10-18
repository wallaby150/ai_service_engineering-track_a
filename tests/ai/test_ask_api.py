"""POST /api/ask: 키가 없으면 503(폼은 그대로), 해석된 조건의 확률은 /api/odds와 똑같다."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ai.llm import Ledger, LlmClient
from ai.target_parser import TargetParser
from api.main import create_app
from tests.ai.fakes import ScriptedLLM, response


def client_with(engine, responses, limit=1.0):
    llm = ScriptedLLM(responses)
    parser = TargetParser(LlmClient("fake/m", ledger=Ledger(limit), completion_fn=llm, cost_fn=lambda r: 0.001), engine)
    return TestClient(create_app(engine=engine, story_narrator=None, target_parser=parser)), llm


def test_without_a_key_ask_is_503_and_the_form_still_works(engine):
    client = TestClient(create_app(engine=engine, story_narrator=None, target_parser=None))
    r = client.post("/api/ask", json={"question": "여자로 태어날 확률"})
    assert r.status_code == 503 and "폼" in r.json()["detail"] and r.json()["request_id"]
    assert client.post("/api/odds", json={"sex": "female"}).status_code == 200


def test_ask_matches_odds_for_the_same_target(korea_engine):
    client, _ = client_with(korea_engine, [response({
        "province": "11", "province_phrase": "서울에서", "employment": "employed", "employment_phrase": "일하는",
        "dropped": [{"phrase": "MBTI", "reason": "이 계산기에 그 통계가 없습니다"}]})])
    r = client.post("/api/ask", json={"question": "서울에서 일하는 MBTI INFP로 태어날 확률"}).json()
    assert r["target"] == {"country": "KOR", "sex": None, "survival": None, "economy": None,
                           "province": "11", "employment": "employed", "occupation": None}
    assert [(x["field_label"], x["value_label"], x["phrase"]) for x in r["readings"]][-1] == ("어른이 되어", "일하고 있다", "일하는")
    assert r["dropped"] == [{"phrase": "MBTI", "reason": "이 계산기에 그 통계가 없습니다"}]
    same = client.post("/api/odds", json=r["target"]).json()
    assert r["odds"] == same  # 숫자는 같은 core 함수가 낸다
    assert r["cost_usd"] == 0.001 and r["cached"] is False


def test_no_condition_found_gives_no_odds(engine):
    client, _ = client_with(engine, [response({"dropped": [{"phrase": "행복하게", "reason": "통계가 없습니다"}]})])
    r = client.post("/api/ask", json={"question": "행복하게 태어날 확률"}).json()
    assert r["odds"] is None and r["readings"] == []


def test_model_failure_and_budget_are_503(engine):
    client, _ = client_with(engine, [RuntimeError("down")])
    assert client.post("/api/ask", json={"question": "여자"}).status_code == 503
    client, llm = client_with(engine, [response({"sex": "female", "sex_phrase": "여자", "dropped": []})], limit=0.0)
    r = client.post("/api/ask", json={"question": "여자"})
    assert r.status_code == 503 and "예산" in r.json()["detail"] and llm.calls == []


def test_question_length_is_limited(engine):
    client, _ = client_with(engine, [])
    assert client.post("/api/ask", json={"question": "가" * 201}).status_code == 422
    assert client.post("/api/ask", json={"question": ""}).status_code == 422
