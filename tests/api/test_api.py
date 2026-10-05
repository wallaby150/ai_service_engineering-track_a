from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core.engine import MAX_SEED, Target


@pytest.fixture
def client(engine):
    return TestClient(create_app(engine=engine))


def test_health_and_config(client):
    assert client.get("/api/health").json() == {"ok": True}
    cfg = client.get("/api/config").json()
    assert cfg["mode"] == "offline" and cfg["narrator"] == "scripted"


def test_meta_lists_countries_and_values(client):
    meta = client.get("/api/meta").json()
    assert {c["iso3"] for c in meta["countries"]} == {"AAA", "BBB", "CCC"}
    assert [v["value"] for v in meta["nodes"]["sex"]["values"]] == ["male", "female"]


def test_simulate_is_reproducible_by_seed(client):
    a = client.post("/api/simulate", json={"seed": 5}).json()
    b = client.post("/api/simulate", json={"seed": 5}).json()
    assert a == b
    assert [s["node"] for s in a["steps"]] == ["country", "sex", "survival", "economy"]
    assert a["narrative"]["narrator"] == "scripted"


def test_simulate_without_seed_returns_one(client):
    r = client.post("/api/simulate", json={}).json()
    assert 0 <= r["seed"] <= MAX_SEED


def test_fixed_country(client):
    r = client.post("/api/simulate", json={"seed": 1, "country": "bbb"}).json()
    assert r["country"]["iso3"] == "BBB"
    assert r["steps"][3]["value"] is None and r["complete"] is False


def test_unknown_country_is_422_with_request_id(client):
    r = client.post("/api/simulate", json={"country": "ZZZ"})
    assert r.status_code == 422
    body = r.json()
    assert body["field"] == "country" and body["request_id"] == r.headers["X-Request-ID"]


@pytest.mark.parametrize("payload", [{"seed": -1}, {"seed": MAX_SEED + 1}, {"country": "KOREA"}])
def test_contract_rejects_bad_input(client, payload):
    assert client.post("/api/simulate", json=payload).status_code == 422


def test_bad_enum_is_rejected_before_core(client):
    assert client.post("/api/odds", json={"sex": "robot"}).status_code == 422


def test_odds_matches_engine(client, engine):
    r = client.post("/api/odds", json={"country": "AAA", "sex": "female", "survival": "survived_5"}).json()
    assert r["p"] == pytest.approx(engine.probability(Target("AAA", "female", "survived_5")).p)
    assert r["tries_90"] >= r["tries_50"] >= 1
    assert len(r["steps"]) == 3


def test_odds_without_data_explains(client):
    r = client.post("/api/odds", json={"country": "BBB", "economy": "above_8_30"}).json()
    assert r["p"] is None and r["reason"]


def test_until_finds_and_life_matches(client):
    r = client.post("/api/until", json={"target": {"sex": "male"}, "seed": 0}).json()
    assert r["found"] and r["life"]["steps"][1]["value"] == "male"


def test_until_does_not_loop_on_impossible_target(client):
    r = client.post("/api/until", json={"target": {"country": "CCC", "economy": "below_3_00"}}).json()
    assert r["found"] is False and r["tries"] == 0


def test_until_seed_wraps_inside_range(engine):
    r = engine.sample_until(Target(sex="female"), seed=MAX_SEED, max_tries=50)
    assert 0 <= r.life.seed <= MAX_SEED
