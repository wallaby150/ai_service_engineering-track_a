from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client(korea_engine):
    return TestClient(create_app(engine=korea_engine, story_narrator=None))


def test_meta_offers_korean_nodes(client):
    meta = client.get("/api/meta").json()
    assert [v["value"] for v in meta["nodes"]["province"]["values"]] == ["11", "39"]
    assert meta["nodes"]["occupation"]["values"][1]["label"] == "전문가"
    assert "korea_region" in meta["sources"]


def test_korean_life_shows_labels_and_sources(client):
    life = client.post("/api/simulate", json={"seed": 4, "country": "KOR"}).json()
    province = next(s for s in life["steps"] if s["node"] == "province")
    assert province["value_label"] in ("서울특별시", "제주특별자치도")
    assert province["node_label"] == "태어난 시도" and province["source"] == "test"


def test_odds_with_korean_target(client):
    r = client.post("/api/odds", json={"sex": "female", "province": "39", "occupation": "02"}).json()
    assert r["target"]["country"] == "KOR"
    assert r["p"] == pytest.approx(0.4 * 0.5 * 0.9 * 0.75 * 0.4 * 0.8)
    # 성별과 시도가 정해졌으니 칸별로 풀어 쓸 수 있다: 국가·성별·생존·시도·고용·직업
    assert [s["node"] for s in r["steps"]] == ["country", "sex", "survival", "province", "employment", "occupation"]
    assert math.prod(s["p"] for s in r["steps"]) == pytest.approx(r["p"])


def test_bad_korean_values_are_rejected(client):
    assert client.post("/api/odds", json={"province": "99"}).status_code == 422
    assert client.post("/api/odds", json={"employment": "retired"}).status_code == 422


def test_until_reaches_a_korean_job(client):
    r = client.post("/api/until", json={"target": {"occupation": "01"}, "seed": 0}).json()
    assert r["found"]
    assert any(s["node"] == "occupation" and s["value"] == "01" for s in r["life"]["steps"])
