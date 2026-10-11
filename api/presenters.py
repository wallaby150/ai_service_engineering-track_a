"""코어 객체 → 응답 스키마. 번역만 하고 계산하지 않는다(1/p 같은 표기 변환은 예외)."""

from __future__ import annotations

from typing import Optional

from api.schemas import CountryOut, HeadlineOut, LifeOut, NarrativeOut, OddsOut, ShareOut, StepOut, TargetIn
from core.engine import Life, Odds, Step
from core.model import NODE_ASSUMPTIONS, NODE_LABELS, label_of
from core.narrator import Narrative
from core.units import births_per_minute, minutes_per_birth, one_in
from core.stats import Snapshot

NODE_SOURCE = {"country": "births", "sex": "sex_ratio", "survival": "survival", "economy": "economy"}
KOREA_SOURCE = {"province": "region", "employment": "employment", "occupation": "occupation"}


def source_of(node: str, snapshot: Snapshot) -> str:
    if node in KOREA_SOURCE:
        return snapshot.korea.sources.get(KOREA_SOURCE[node], "") if snapshot.korea else ""
    return snapshot.sources.get(NODE_SOURCE[node], "")


def step_out(step: Step, snapshot: Snapshot) -> StepOut:
    value_label: Optional[str] = step.label or label_of(snapshot, step.node, step.value)
    return StepOut(
        node=step.node,
        node_label=NODE_LABELS[step.node],
        value=step.value,
        value_label=value_label,
        p=step.p,
        assumed=step.assumed,
        source=source_of(step.node, snapshot),
        year=step.year,
        one_in=one_in(step.p),
        assumption=NODE_ASSUMPTIONS.get(step.node, ""),
    )


def headline_out(life: Life, snapshot: Snapshot) -> Optional[HeadlineOut]:
    h = life.headline
    if h is None:
        return None

    def share(x):  # type: ignore[no-untyped-def]
        return ShareOut(below=x.below, same=x.same, above=x.above) if x else None

    return HeadlineOut(node=h.node, node_label=NODE_LABELS[h.node], value=h.value,
                       value_label=label_of(snapshot, h.node, h.value), year=h.year,
                       country=share(h.country), world=share(h.world), world_coverage=h.world_coverage)


def narrative_out(n: Narrative) -> NarrativeOut:
    return NarrativeOut(
        title=n.title, paragraphs=list(n.paragraphs), narrator=n.narrator, facts_used=list(n.facts_used), note=n.note
    )


def life_out(life: Life, narrative: Narrative, snapshot: Snapshot) -> LifeOut:
    c = life.country
    return LifeOut(
        seed=life.seed,
        country=CountryOut(
            iso3=c.iso3, name_ko=c.name_ko, name_en=c.name_en, region=c.region, income_level=c.income_level,
            births_per_year=c.births, births_per_minute=births_per_minute(c.births),
            minutes_per_birth=minutes_per_birth(c.births),
        ),
        steps=[step_out(s, snapshot) for s in life.steps],
        joint_p=life.joint_p,
        one_in=round(1 / life.joint_p) if life.joint_p > 0 else None,
        complete=life.complete,
        life_expectancy=life.life_expectancy,
        headline=headline_out(life, snapshot),
        narrative=narrative_out(narrative),
    )


def odds_out(odds: Odds, snapshot: Snapshot) -> OddsOut:
    t = odds.target
    return OddsOut(
        target=TargetIn(country=t.country, sex=t.sex, survival=t.survival, economy=t.economy,
                        province=t.province, employment=t.employment, occupation=t.occupation),
        p=odds.p,
        one_in=(1 / odds.p) if odds.p else None,
        coverage=odds.coverage,
        expected_tries=odds.expected_tries,
        tries_50=odds.tries(0.5),
        tries_90=odds.tries(0.9),
        steps=[step_out(s, snapshot) for s in odds.steps],
        reason=odds.reason,
    )
