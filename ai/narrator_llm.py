"""AI 인생 서사 — ReWOO (6주차).

① 계획자(LLM 1회): 어떤 맥락 조회를 할지 고른다. 결과 자리를 #E1, #E2 … 로 비워 둔다
② 실행(LLM 0회): 조회는 core/context.py의 결정적 코드가 한다. 나라는 코드가 넣는다
③ 해석가(LLM 1회): 화면 글 + 근거 목록(core/references.py)으로 화면에 없는 해석을 쓴다.
   숫자는 직접 쓰지 않고 "{R3}"처럼 근거 id로 가리킨다 — 값과 단위는 코드가 채운다(13주차 "숫자는 참조로")
④ 검증(코드): 문장 하나 단위로 없는 참조·직접 친 숫자·쓰지 않는 말을 버리고, 남은 글이 화면을 되풀이하지
   않는지·새 근거를 둘 이상 쓰는지 본다. 모자라면 한 번 더 쓰게 하고, 그래도 모자라거나 모델이 실패하면
   해석 없이 템플릿만 남는다(정직한 실패)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from string import Template
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from ai.cache import VersionedCache, data_version, digest
from ai.llm import BudgetExceeded, LlmCall, LlmClient, LlmError, RateLimited
from core.context import METRICS, TOOLS, run_tool
from core.engine import Engine, Life
from core.facts import facts_of, peer_facts
from core.narrator import Narrative, Narrator
from core.stats import Snapshot
from core.references import build_catalog, catalog_lines, novel_used, peer_lines, render
from core.verify import overlap_ratio

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
MAX_STEPS = 3
MAX_OVERLAP = 0.35  # 해석 글자의 35%를 넘게 화면 글과 겹치면 '다시 말하기'로 본다
MIN_NEW_EVIDENCE = 2  # 화면에 없는 근거(새 참조·다른 사람들의 나라 이름)를 적어도 둘
DEFAULT_TITLE = "화면 밖의 맥락"  # 제목 문장이 검사에 걸리면 이 제목을 쓴다
CACHE_SIZE = 512  # 기억해 둘 해석 수. 넘치면 가장 오래 안 쓴 것부터 버린다
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
    title: str = Field(max_length=60, description="숫자 없이 20자 안팎")
    paragraphs: List[str] = Field(min_length=2, max_length=5, description="숫자는 {R3}처럼 근거 id로만")
    facts_used: List[str] = Field(default_factory=list)


@dataclass
class StoryReport:
    """화면·평가에 쓰는 기록. 무엇을 조회했고, 몇 번 썼고, 무엇이 걸렸는지."""

    narrative: Narrative
    calls: List[LlmCall] = field(default_factory=list)
    plan: List[Dict[str, Optional[str]]] = field(default_factory=list)
    attempts: int = 0
    dropped: List[List[Tuple[str, str]]] = field(default_factory=list)  # 시도마다 버린 (문장, 이유)
    overlap: List[float] = field(default_factory=list)  # 시도마다 화면 글과 겹친 비율
    new_evidence: List[List[str]] = field(default_factory=list)  # 시도마다 살아남은 글이 쓴 화면 밖 근거
    cached: bool = False  # 같은 버전으로 전에 만든 해석을 다시 꺼냈는가(모델 호출 0회)

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

    def __init__(self, client: LlmClient, snapshot: Snapshot, fallback: Narrator, max_solver_attempts: int = 2,
                 cache_size: int = CACHE_SIZE) -> None:
        self.client = client
        self.snapshot = snapshot
        self.fallback = fallback
        self.max_solver_attempts = max_solver_attempts
        self._planner = _load("planner.md")
        self._solver = _load("solver.md")
        self._engine: Optional[Engine] = None  # 세계 어딘가의 다른 4명을 뽑을 때만 만든다
        # 캐시 키의 버전(13주차): 데이터·프롬프트·모델 중 하나라도 바뀌면 예전 해석은 쓰지 않는다. 시간(TTL)으로는 버리지 않는다
        self.version = {
            "data": data_version(snapshot),
            "prompt": digest(self._planner.template + self._solver.template + json.dumps(
                {n: d for n, (d, _) in TOOLS.items()}, ensure_ascii=False)),
            "model": ",".join([client.model, *client.fallbacks]),
        }
        self._cache: VersionedCache[StoryReport] = VersionedCache(cache_size)

    def _peers(self, life: Life) -> List[Dict[str, object]]:
        if self._engine is None:
            self._engine = Engine(self.snapshot)
        return [peer_facts(p) for p in self._engine.same_moment(life.seed)]

    def narrate(self, life: Life) -> Narrative:
        return self.story(life).narrative

    def _key(self, life: Life) -> tuple:
        return (tuple(self.version.values()), life.seed, tuple((st.node, st.value) for st in life.steps))

    def story(self, life: Life) -> StoryReport:
        key = self._key(life)
        hit = self._cache.get(key)
        if hit is not None:
            return replace(hit, calls=[], cached=True)  # 다시 꺼낸 해석은 모델을 부르지 않았다 — 비용 0
        report = self._story(life)
        if report.narrative.narrator == "llm":  # 실패(템플릿)는 기억하지 않는다 — 다음엔 다시 해 본다
            self._cache.put(key, report)
        return report

    def _story(self, life: Life) -> StoryReport:
        report = StoryReport(narrative=self.fallback.narrate(life))
        facts = facts_of(life)
        try:
            steps = self._plan(facts, report)
            steps = self._with_required(life, steps, report)
            lookups = self._execute(life, steps)
            return self._write(life, facts, lookups, self._peers(life), report)
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
    def _execute(self, life: Life, steps: List[PlanStep]) -> List[Tuple[str, Optional[str], Dict[str, object]]]:
        return [(s.tool, s.metric, run_tool(self.snapshot, s.tool, life.country.iso3, s.metric)) for s in steps]

    # ③ 작성 + ④ 검증
    def _write(self, life: Life, facts: Dict[str, object],
               lookups: List[Tuple[str, Optional[str], Dict[str, object]]],
               peers: List[Dict[str, object]], report: StoryReport) -> StoryReport:
        screen = " ".join(self.fallback.narrate(life).paragraphs)  # 화면에 이미 있는 글 = 템플릿
        refs = build_catalog(facts, lookups, peers)
        names = sorted({str(p["country"]) for p in peers} - {str(facts.get("country"))})
        words = {k: v for k, v in facts.items() if isinstance(v, str)}  # 글로 된 사실만. 숫자는 근거 목록으로
        feedback = ""
        for attempt in range(1, self.max_solver_attempts + 1):
            report.attempts = attempt
            prompt = self._solver.substitute(
                screen=screen, facts=json.dumps(words, ensure_ascii=False, indent=1),
                refs=_wrap("REFERENCES", catalog_lines(refs)), peers=_wrap("SAME_MOMENT", peer_lines(peers)),
                feedback=feedback,
            )
            story, calls = self.client.structured(
                "solver", [{"role": "user", "content": prompt}], Story, "emit_story", "해석을 낸다"
            )
            report.calls += calls
            body = render(story.paragraphs, refs)
            title = render([story.title], refs)
            text = " ".join(body.paragraphs)
            overlap = overlap_ratio(text, screen)
            hits = novel_used(body, refs, names)
            report.dropped.append(body.dropped + title.dropped)
            report.overlap.append(round(overlap, 3))
            report.new_evidence.append(hits)
            if body.paragraphs and overlap <= MAX_OVERLAP and len(hits) >= MIN_NEW_EVIDENCE:
                report.narrative = Narrative(
                    title=title.paragraphs[0] if title.paragraphs else DEFAULT_TITLE,
                    paragraphs=tuple(body.paragraphs),
                    facts_used=tuple(k for k in story.facts_used if k in facts),
                    narrator="llm",
                )
                return report
            log.info("NARRATOR REJECT attempt=%d dropped=%d overlap=%.2f new=%s", attempt, len(body.dropped), overlap, hits)
            problems = [f"버린 문장: \"{s}\" — {why}" for s, why in body.dropped]
            if overlap > MAX_OVERLAP:
                problems.append(f"화면에 이미 있는 글을 되풀이했다(겹침 {overlap:.0%}). 화면이 말하지 않은 것만 써라.")
            if len(hits) < MIN_NEW_EVIDENCE:
                problems.append("화면에 없는 근거가 모자란다. '(화면에 이미 있음)' 표시가 없는 근거 id나 세계 어딘가의 "
                                "다른 사람을 적어도 두 가지 써라.")
            feedback = "\n[직전 원고의 문제]\n" + "\n".join(problems) + "\n고쳐서 다시 써라."
        return self._fall_back(life, report, "AI가 화면에 없는 해석을 만들지 못해 템플릿 서사만 보여 드립니다.")

    def _fall_back(self, life: Life, report: StoryReport, note: str) -> StoryReport:
        n = self.fallback.narrate(life)
        report.narrative = Narrative(n.title, n.paragraphs, n.facts_used, n.narrator, note=note)
        return report

