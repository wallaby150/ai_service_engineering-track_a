"""AI 인생 서사 — ReWOO (6주차).

① 계획자(LLM 1회): 어떤 맥락 조회를 할지 고른다. 결과 자리를 #E1, #E2 … 로 비워 둔다
② 실행(LLM 0회): 조회는 core/context.py의 결정적 코드가 한다. 나라는 코드가 넣는다
③ 작성자(LLM 1회): 사실 + 조회 결과로 이야기를 쓴다
④ 검증(코드): 이야기 속 숫자가 근거에 있는지 대조한다. 어긋나면 위반을 알려 한 번 더 쓰게 하고,
   그래도 어긋나거나 모델이 실패하면 템플릿 서사로 떨어진다(정직한 실패)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from ai.llm import BudgetExceeded, LlmCall, LlmClient, LlmError, RateLimited
from core.context import METRICS, TOOLS, run_tool
from core.engine import Engine, Life
from core.facts import facts_of, peer_facts
from core.narrator import Narrative, Narrator
from core.stats import Snapshot
from core.verify import allowed_numbers, allowed_years, new_evidence, overlap_ratio, unsupported_numbers

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
MAX_STEPS = 3
MAX_OVERLAP = 0.35  # 해석 글자의 35%를 넘게 화면 글과 겹치면 '다시 말하기'로 본다
MIN_NEW_EVIDENCE = 2  # 화면에 없는 근거(새 숫자·다른 나라 이름)를 적어도 둘
# 위치 한 줄이 고른 칸 → 세계와 견줄 지표. 해석가가 늘 받는 조회(계획자가 고르지 않아도 코드가 넣는다)
HEADLINE_METRIC = {"economy": "poverty_3_00", "survival": "u5mr"}
log = logging.getLogger("reborn.narrator")


# ── 계약 ──────────────────────────────────────────────────
class PlanStep(BaseModel):
    tool: Literal["country_profile", "world_comparison", "region_peers"]
    metric: Optional[Literal["u5mr", "life_expectancy", "poverty_3_00"]] = Field(
        default=None, description="world_comparison일 때만"
    )
    why: str = Field(max_length=120, description="이 조회가 왜 필요한지 한 줄")


class Plan(BaseModel):
    steps: List[PlanStep] = Field(min_length=1, max_length=MAX_STEPS)


class Story(BaseModel):
    title: str = Field(max_length=60)
    paragraphs: List[str] = Field(min_length=2, max_length=5)
    facts_used: List[str] = Field(default_factory=list)


@dataclass
class StoryReport:
    """화면·평가에 쓰는 기록. 무엇을 조회했고, 몇 번 썼고, 무엇이 걸렸는지."""

    narrative: Narrative
    calls: List[LlmCall] = field(default_factory=list)
    plan: List[Dict[str, Optional[str]]] = field(default_factory=list)
    attempts: int = 0
    violations: List[List[float]] = field(default_factory=list)
    overlap: List[float] = field(default_factory=list)  # 시도마다 화면 글과 겹친 비율
    new_evidence: List[List[str]] = field(default_factory=list)  # 시도마다 화면에 없던 근거

    @property
    def cost_usd(self) -> float:
        return sum(c.cost_usd or 0.0 for c in self.calls)


def _load(name: str) -> Template:
    return Template((PROMPTS_DIR / name).read_text(encoding="utf-8"))


def _wrap(name: str, payload: object) -> str:
    """조회 결과를 경계 마커로 감싼다. 결과 안의 마커 문자열은 먼저 지운다(6주차)."""
    body = json.dumps(payload, ensure_ascii=False).replace("<<<", "").replace(">>>", "")
    return f"<<<TOOL_RESULT {name}>>>\n{body}\n<<<END_TOOL_RESULT>>>"


class LlmNarrator:
    name = "llm"

    def __init__(self, client: LlmClient, snapshot: Snapshot, fallback: Narrator, max_solver_attempts: int = 2) -> None:
        self.client = client
        self.snapshot = snapshot
        self.fallback = fallback
        self.max_solver_attempts = max_solver_attempts
        self._planner = _load("planner.md")
        self._solver = _load("solver.md")
        self._engine: Optional[Engine] = None  # 같은 순간 4명을 뽑을 때만 만든다

    def _peers(self, life: Life) -> List[Dict[str, object]]:
        if self._engine is None:
            self._engine = Engine(self.snapshot)
        return [peer_facts(p) for p in self._engine.same_moment(life.seed)]

    def narrate(self, life: Life) -> Narrative:
        return self.story(life).narrative

    def story(self, life: Life) -> StoryReport:
        report = StoryReport(narrative=self.fallback.narrate(life))
        facts = facts_of(life)
        try:
            steps = self._plan(facts, report)
            steps = self._with_required(life, steps, report)
            evidence = self._execute(life, steps)
            return self._write(life, facts, evidence, self._peers(life), report)
        except BudgetExceeded:
            return self._fall_back(life, report, "AI 서사 예산을 다 써서 템플릿 서사로 보여 드립니다.")
        except RateLimited:
            return self._fall_back(life, report, "AI 요청 한도에 걸려 템플릿 서사로 보여 드립니다. 잠시 후 다시 눌러 보세요.")
        except LlmError as e:
            log.warning("NARRATOR FALLBACK %s", e)
            return self._fall_back(life, report, "AI가 이야기를 쓰지 못해 템플릿 서사로 보여 드립니다.")

    # ① 계획
    def _plan(self, facts: Dict[str, object], report: StoryReport) -> List[PlanStep]:
        tools = "\n".join(f"- {n}: {desc}" for n, (desc, _) in TOOLS.items()) + f"\n  (metric: {', '.join(METRICS)})"
        prompt = self._planner.substitute(tools=tools, facts=json.dumps(facts, ensure_ascii=False))
        plan, calls = self.client.structured(
            "planner", [{"role": "user", "content": prompt}], Plan, "emit_plan", "조회 계획을 낸다"
        )
        report.calls += calls
        unique: List[PlanStep] = []
        for s in plan.steps:  # 중복 조회와 쓸모없는 인자는 코드가 걸러 낸다
            if s.tool == "world_comparison" and s.metric is None:
                continue
            if s.tool != "world_comparison":
                s = s.model_copy(update={"metric": None})
            if all((u.tool, u.metric) != (s.tool, s.metric) for u in unique):
                unique.append(s)
        report.plan = [{"id": f"E{i + 1}", "tool": s.tool, "metric": s.metric, "why": s.why} for i, s in enumerate(unique)]
        return unique

    def _with_required(self, life: Life, steps: List[PlanStep], report: StoryReport) -> List[PlanStep]:
        """해석에 늘 필요한 조회는 계획자가 빠뜨려도 코드가 넣는다: 위치 한 줄의 지표를 세계와 견주기, 이웃 나라."""
        metric = HEADLINE_METRIC.get(life.headline.node if life.headline else "", "life_expectancy")
        required = [PlanStep(tool="world_comparison", metric=metric, why="위치 한 줄의 지표를 세계와 견준다(코드가 넣음)"),
                    PlanStep(tool="region_peers", why="같은 지역 나라들(코드가 넣음)")]
        out = list(steps)
        for r in required:
            if all((u.tool, u.metric) != (r.tool, r.metric) for u in out):
                out.append(r)
        report.plan = [{"id": f"E{i + 1}", "tool": s.tool, "metric": s.metric, "why": s.why} for i, s in enumerate(out)]
        return out

    # ② 실행 — LLM 없이
    def _execute(self, life: Life, steps: List[PlanStep]) -> Dict[str, object]:
        return {f"E{i + 1}": run_tool(self.snapshot, s.tool, life.country.iso3, s.metric) for i, s in enumerate(steps)}

    # ③ 작성 + ④ 검증
    def _write(self, life: Life, facts: Dict[str, object], evidence: Dict[str, object],
               peers: List[Dict[str, object]], report: StoryReport) -> StoryReport:
        screen = " ".join(self.fallback.narrate(life).paragraphs)  # 화면에 이미 있는 글 = 템플릿
        allowed = allowed_numbers(facts, evidence, peers)
        years = allowed_years(facts, evidence)
        novel = allowed_numbers(evidence, peers) - allowed_numbers(facts)
        names = {str(p["country"]) for p in peers} | {
            str(x["country"]) for e in evidence.values() if isinstance(e, dict) for x in e.get("peers", [])}  # type: ignore[union-attr]
        names.discard(str(facts.get("country")))
        evidence_text = "\n".join(_wrap(k, v) for k, v in evidence.items())
        peers_text = _wrap("SAME_MOMENT", peers)
        feedback = ""
        for attempt in range(1, self.max_solver_attempts + 1):
            report.attempts = attempt
            prompt = self._solver.substitute(
                screen=screen, facts=json.dumps(facts, ensure_ascii=False, indent=1),
                evidence=evidence_text, peers=peers_text, feedback=feedback,
            )
            story, calls = self.client.structured(
                "solver", [{"role": "user", "content": prompt}], Story, "emit_story", "해석을 낸다"
            )
            report.calls += calls
            text = " ".join([story.title, *story.paragraphs])
            bad = unsupported_numbers(text, allowed, years)
            overlap = overlap_ratio(text, screen)
            hits = new_evidence(text, novel, names)
            report.violations.append(bad)
            report.overlap.append(round(overlap, 3))
            report.new_evidence.append(hits)
            if not bad and overlap <= MAX_OVERLAP and len(hits) >= MIN_NEW_EVIDENCE:
                report.narrative = Narrative(
                    title=story.title,
                    paragraphs=tuple(story.paragraphs),
                    facts_used=tuple(k for k in story.facts_used if k in facts),
                    narrator="llm",
                )
                return report
            log.info("NARRATOR REJECT attempt=%d unsupported=%s overlap=%.2f new=%s", attempt, bad, overlap, hits)
            problems = []
            if bad:
                problems.append("근거에 없는 숫자를 썼다: " + ", ".join(f"{n:g}" for n in bad) + ". 빼거나 근거에 있는 값으로 바꿔라.")
            if overlap > MAX_OVERLAP:
                problems.append(f"화면에 이미 있는 글을 되풀이했다(겹침 {overlap:.0%}). 화면이 말하지 않은 것만 써라.")
            if len(hits) < MIN_NEW_EVIDENCE:
                problems.append("화면에 없는 근거가 모자란다. 조회 결과(세계 배율·순위, 이웃 나라)나 같은 순간 태어난 사람을 "
                                "적어도 두 가지 써라.")
            feedback = "\n[직전 원고의 문제]\n" + "\n".join(problems) + "\n고쳐서 다시 써라."
        return self._fall_back(life, report, "AI가 화면에 없는 해석을 만들지 못해 템플릿 서사만 보여 드립니다.")

    def _fall_back(self, life: Life, report: StoryReport, note: str) -> StoryReport:
        n = self.fallback.narrate(life)
        report.narrative = Narrative(n.title, n.paragraphs, n.facts_used, n.narrator, note=note)
        return report

