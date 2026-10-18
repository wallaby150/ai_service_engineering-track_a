"""자연어로 묻는 역확률 — 두 번째 AI 자리 (처음 로드맵의 '후보 B').

"서울에서 일하는 여자로 태어날 확률은?" → LLM이 조건(Target)으로 바꾼다 → 확률은 core가 계산한다.
모델은 허용 목록 안에서 고르기만 한다(13주차: 모델이 고르고 코드가 실행):
- 칸마다 값은 스키마의 enum이다. 목록 밖 값은 스키마에서 걸리고, 마지막으로 Engine.check_target이 거부한다.
- 칸마다 질문의 어느 말에서 왔는지(phrase)를 남겨 화면이 해석을 보여 준다.
- 통계가 없는 조건(키, MBTI …)과 뜻이 하나로 정해지지 않는 말은 지어내지 않고 dropped에 이유와 함께 넣는다.
- 칸 사이 규칙은 코드가 건다: 한국 칸이 있으면 국가는 대한민국. 다른 나라와 한국 칸이 함께 오면 한국 칸을 뺀다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from string import Template
from typing import Annotated, Dict, List, Literal, Optional, Tuple

from pydantic import AfterValidator, BaseModel, Field, create_model

from ai.cache import VersionedCache, data_version, digest
from ai.llm import LlmCall, LlmClient
from core.engine import Engine, Target
from core.errors import UnknownValue
from core.model import KOREA_ISO3, KOREA_NODES, NODE_LABELS, target_choices

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
MAX_QUESTION = 200
CACHE_SIZE = 1024
# 값이 이보다 많은 칸은 enum 대신 문자열로 보내고 코드가 목록과 대조한다.
# Gemini가 국가 217개 enum을 400(INVALID_ARGUMENT)으로 거부했다(2026-10-18 확인)
MAX_ENUM = 50


class DroppedOut(BaseModel):
    phrase: str = Field(max_length=60, description="질문에서 조건으로 바꾸지 못한 말")
    reason: str = Field(max_length=120, description="왜 바꾸지 못했는지 한 줄")


@dataclass(frozen=True)
class Reading:
    field: str
    value: str
    phrase: str  # 질문의 어느 말에서 왔는가


@dataclass
class Parsed:
    target: Target
    readings: List[Reading] = field(default_factory=list)
    dropped: List[Tuple[str, str]] = field(default_factory=list)  # (말, 이유)
    calls: List[LlmCall] = field(default_factory=list)
    cached: bool = False

    @property
    def cost_usd(self) -> float:
        return sum(c.cost_usd or 0.0 for c in self.calls)


def _one_of(node: str, codes: Tuple[str, ...]):
    allowed = set(codes)

    def check(v: Optional[str]) -> Optional[str]:
        if v is not None and v not in allowed:
            raise ValueError(f"{node}={v!r}는 목록에 없다. 목록의 코드만 쓴다")
        return v
    return check


def _schema(choices: Dict[str, Tuple[Tuple[str, str], ...]]) -> type:
    """칸마다 값 enum과 근거 말(phrase)을 가진 평평한 스키마. 한국 칸은 통계가 있을 때만 생긴다."""
    fields: Dict[str, object] = {}
    for node, values in choices.items():
        codes = tuple(v for v, _ in values)
        desc = f"{NODE_LABELS[node]}. 질문에 없으면 null"
        if len(codes) <= MAX_ENUM:
            fields[node] = (Optional[Literal[codes]], Field(default=None, description=desc))
        else:  # 목록 밖 값은 검증 오류 → structured()가 오류를 보여 주고 한 번 더 묻는다
            fields[node] = (Annotated[Optional[str], AfterValidator(_one_of(node, codes))],
                            Field(default=None, description=desc + ". 목록의 코드만"))
        fields[f"{node}_phrase"] = (Optional[str], Field(default=None, max_length=40, description=f"{node} 값의 근거가 된 질문 속 말"))
    fields["dropped"] = (List[DroppedOut], Field(default_factory=list, description="조건으로 바꾸지 못한 말"))
    return create_model("AskTarget", **fields)  # type: ignore[call-overload]


def _choice_lines(choices: Dict[str, Tuple[Tuple[str, str], ...]]) -> str:
    return "\n".join(f"- {node} ({NODE_LABELS[node]}): " + ", ".join(f"{v}={label}" for v, label in values)
                     for node, values in choices.items())


def normalize(question: str) -> str:
    return " ".join(question.split())[:MAX_QUESTION]


class TargetParser:
    name = "llm"

    def __init__(self, client: LlmClient, engine: Engine, cache_size: int = CACHE_SIZE) -> None:
        self.client = client
        self.engine = engine
        self.choices = target_choices(engine.snapshot)
        self._schema = _schema(self.choices)
        self._prompt = Template((PROMPTS_DIR / "parse_target.md").read_text(encoding="utf-8"))
        self._choice_text = _choice_lines(self.choices)
        self.version = {
            "data": data_version(engine.snapshot),
            "prompt": digest(self._prompt.template),
            "model": ",".join([client.model, *client.fallbacks]),
        }
        self._cache: VersionedCache[Parsed] = VersionedCache(cache_size)

    def parse(self, question: str) -> Parsed:
        """LlmError(RateLimited·BudgetExceeded 포함)는 그대로 올린다 — 실패를 어떻게 알릴지는 문(api/)이 정한다."""
        q = normalize(question)
        key = (tuple(self.version.values()), q)
        hit = self._cache.get(key)
        if hit is not None:
            return replace(hit, calls=[], cached=True)
        body = q.replace("<<<", "").replace(">>>", "")  # 경계 마커를 질문 안에서 흉내 내지 못하게
        prompt = self._prompt.substitute(choices=self._choice_text, question=f"<<<QUESTION>>>\n{body}\n<<<END_QUESTION>>>")
        out, calls = self.client.structured("parser", [{"role": "user", "content": prompt}], self._schema,
                                            "emit_target", "질문을 역확률 조건으로 바꾼다")
        parsed = self._settle(out)
        parsed.calls = calls
        self._cache.put(key, parsed)
        return parsed

    def _settle(self, out: BaseModel) -> Parsed:
        """모델 출력 → 코드 규칙 → 검사를 통과한 Target."""
        values = {node: getattr(out, node) for node in self.choices if getattr(out, node) is not None}
        phrase = {node: (getattr(out, f"{node}_phrase") or "").strip() for node in values}
        dropped = [(d.phrase, d.reason) for d in out.dropped]  # type: ignore[attr-defined]
        korean = [n for n in KOREA_NODES if n in values]
        if korean and values.get("country", KOREA_ISO3) != KOREA_ISO3:
            for n in korean:  # 다른 나라와 한국 칸은 함께 성립하지 않는다 — 나라를 따르고 한국 칸을 뺀다
                dropped.append((phrase[n] or n, f"{NODE_LABELS[n]}: 대한민국에서 태어났을 때만 고를 수 있는 조건입니다"))
                del values[n]
        elif korean and "country" not in values:
            values["country"] = KOREA_ISO3
            phrase["country"] = phrase[korean[0]]  # 시도·직업을 말했으니 대한민국이다
        try:
            target = self.engine.check_target(Target(**values))
        except UnknownValue as e:  # 스키마를 지나왔다면 오지 않는다. 그래도 오면 그 칸만 뺀다
            dropped.append((str(e.value), f"{e.field}: 허용 목록에 없는 값"))
            values.pop(e.field, None)
            target = self.engine.check_target(Target(**values))
        readings = [Reading(n, values[n], phrase.get(n, "")) for n in self.choices if n in values]
        return Parsed(target=target, readings=readings, dropped=dropped)
