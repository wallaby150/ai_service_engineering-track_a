"""코어 객체 → 응답 스키마. 번역만 하고 계산하지 않는다(1/p 같은 표기 변환은 예외)."""

from __future__ import annotations

from typing import Optional

from api.schemas import CountryOut, LifeOut, NarrativeOut, OddsOut, StepOut, TargetIn
from core.engine import Life, Odds, Step
from core.model import LABELS, NODE_LABELS
from core.narrator import Narrative
from core.stats import Snapshot

NODE_SOURCE = {"country": "births", "sex": "sex_ratio", "survival": "survival", "economy": "economy"}


def step_out(step: Step, snapshot: Snapshot) -> StepOut:
    if step.node == "country":
        country = snapshot.get(step.value or "")
        value_label: Optional[str] = country.name_ko if country else None
    else:
        value_label = LABELS[step.node].get(step.value or "")
    return StepOut(
        node=step.node,
        node_label=NODE_LABELS[step.node],
        value=step.value,
        value_label=value_label,
        p=step.p,
        assumed=step.assumed,
        source=snapshot.sources.get(NODE_SOURCE[step.node], ""),
    )


def narrative_out(n: Narrative) -> NarrativeOut:
    return NarrativeOut(
        title=n.title, paragraphs=list(n.paragraphs), narrator=n.narrator, facts_used=list(n.facts_used), note=n.note
    )


def life_out(life: Life, narrative: Narrative, snapshot: Snapshot) -> LifeOut:
    c = life.country
    return LifeOut(
        seed=life.seed,
        country=CountryOut(
            iso3=c.iso3, name_ko=c.name_ko, name_en=c.name_en, region=c.region, income_level=c.income_level
        ),
        steps=[step_out(s, snapshot) for s in life.steps],
        joint_p=life.joint_p,
        one_in=round(1 / life.joint_p) if life.joint_p > 0 else None,
        complete=life.complete,
        life_expectancy=life.life_expectancy,
        narrative=narrative_out(narrative),
    )


def odds_out(odds: Odds, snapshot: Snapshot) -> OddsOut:
    t = odds.target
    return OddsOut(
        target=TargetIn(country=t.country, sex=t.sex, survival=t.survival, economy=t.economy),
        p=odds.p,
        one_in=(1 / odds.p) if odds.p else None,
        coverage=odds.coverage,
        expected_tries=odds.expected_tries,
        tries_50=odds.tries(0.5),
        tries_90=odds.tries(0.9),
        steps=[step_out(s, snapshot) for s in odds.steps],
        reason=odds.reason,
    )
