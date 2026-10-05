"""FastAPI 문. 계약 검증 → 코어 호출 → 응답 번역. 계산은 하지 않는다.

핸들러는 전부 `def`다. 코어가 동기 코드라 FastAPI가 워커 스레드로 보낸다
(`async def` 안에서 동기 호출을 하면 동시 요청이 줄을 선다 — 8주차).

    uvicorn api.main:app --reload
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api import __version__
from api.presenters import life_out, odds_out
from api.schemas import (
    ConfigOut,
    CountryMeta,
    LifeOut,
    MetaOut,
    NodeMeta,
    OddsOut,
    SimulateRequest,
    TargetIn,
    UntilOut,
    UntilRequest,
    ValueMeta,
)
from core.engine import Engine, Target, new_seed
from core.errors import UnknownValue
from core.model import LABELS, NODE_LABELS
from core.narrator import Narrator
from core.narrator_scripted import ScriptedNarrator
from core.stats import load_manifest, load_snapshot

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
log = logging.getLogger("reborn.api")


def _target(t: TargetIn) -> Target:
    return Target(country=t.country, sex=t.sex, survival=t.survival, economy=t.economy)


def create_app(engine: Optional[Engine] = None, narrator: Optional[Narrator] = None) -> FastAPI:
    engine = engine or Engine(load_snapshot())
    narrator = narrator or ScriptedNarrator()
    snapshot = engine.snapshot
    manifest = load_manifest()

    app = FastAPI(
        title="다시 태어난다면",
        version=__version__,
        description="공공 통계 기반 인생 시뮬레이터. 확률은 전부 코드가 계산한다.",
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = uuid.uuid4().hex[:12]
        request.state.request_id = rid
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        ms = (time.perf_counter() - start) * 1000
        log.info("%s %s -> %s %.0fms request_id=%s", request.method, request.url.path, response.status_code, ms, rid)
        return response

    @app.exception_handler(UnknownValue)
    def unknown_value(request: Request, exc: UnknownValue) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "UnknownValue",
                "detail": str(exc),
                "field": exc.field,
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/config", response_model=ConfigOut)
    def config() -> ConfigOut:
        mode = "offline" if narrator.name == "scripted" else "live"
        return ConfigOut(version=__version__, mode=mode, narrator=narrator.name)

    @app.get("/api/meta", response_model=MetaOut)
    def meta() -> MetaOut:
        total = snapshot.total_births
        nodes = {
            node: NodeMeta(
                label=NODE_LABELS[node],
                values=[ValueMeta(value=v, label=label) for v, label in LABELS[node].items()],
                source=snapshot.sources.get(key, ""),
            )
            for node, key in (("sex", "sex_ratio"), ("survival", "survival"), ("economy", "economy"))
        }
        countries = sorted(
            (CountryMeta(iso3=c.iso3, name_ko=c.name_ko, share=c.births / total) for c in snapshot.countries),
            key=lambda c: c.name_ko,
        )
        return MetaOut(
            nodes=nodes,
            countries=countries,
            sources=snapshot.sources,
            snapshot={k: manifest.get(k) for k in ("fetched_at", "birth_coverage", "license")},
        )

    @app.post("/api/simulate", response_model=LifeOut)
    def simulate(req: SimulateRequest) -> LifeOut:
        seed = req.seed if req.seed is not None else new_seed()
        life = engine.sample(seed, country=req.country)
        return life_out(life, narrator.narrate(life), snapshot)

    @app.post("/api/odds", response_model=OddsOut)
    def odds(req: TargetIn) -> OddsOut:
        return odds_out(engine.probability(_target(req)), snapshot)

    @app.post("/api/until", response_model=UntilOut)
    def until(req: UntilRequest) -> UntilOut:
        target = _target(req.target)
        o = engine.probability(target)
        if not o.p:  # 확률이 0이거나 계산할 수 없으면 돌려 보지도 않는다
            return UntilOut(found=False, tries=0, max_tries=req.max_tries, odds=odds_out(o, snapshot))
        seed = req.seed if req.seed is not None else new_seed()
        r = engine.sample_until(target, seed=seed, max_tries=req.max_tries)
        life = life_out(r.life, narrator.narrate(r.life), snapshot) if r.life else None
        return UntilOut(found=r.found, tries=r.tries, max_tries=r.max_tries, odds=odds_out(o, snapshot), life=life)

    if WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
app = create_app()
