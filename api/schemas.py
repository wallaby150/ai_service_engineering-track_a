"""HTTP 계약. 요청 검증(422)과 /docs 문서가 이 한 파일에서 나온다.

Python 3.9에서도 돌아야 하므로 `X | None` 대신 Optional을 쓴다(pydantic이 런타임에 읽는다).
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from core.engine import MAX_SEED

Sex = Literal["male", "female"]
SurvivalValue = Literal["infant_death", "child_death", "survived_5"]
EconomyValue = Literal["below_3_00", "below_4_20", "below_8_30", "above_8_30"]
CountryCode = Optional[str]


# ── 요청 ──────────────────────────────────────────────────
class SimulateRequest(BaseModel):
    seed: Optional[int] = Field(default=None, ge=0, le=MAX_SEED, description="같은 시드 = 같은 인생. 비우면 무작위")
    country: CountryCode = Field(default=None, min_length=3, max_length=3, description="ISO3 코드. 비우면 통계에 맡긴다")


class TargetIn(BaseModel):
    country: CountryCode = Field(default=None, min_length=3, max_length=3)
    sex: Optional[Sex] = None
    survival: Optional[SurvivalValue] = None
    economy: Optional[EconomyValue] = None


class UntilRequest(BaseModel):
    target: TargetIn
    seed: Optional[int] = Field(default=None, ge=0, le=MAX_SEED)
    max_tries: int = Field(default=100_000, ge=1, le=200_000, description="상한. 넘으면 멈춘다")


# ── 응답 ──────────────────────────────────────────────────
class StepOut(BaseModel):
    node: str
    node_label: str
    value: Optional[str] = Field(description="None이면 그 나라에 통계가 없다")
    value_label: Optional[str]
    p: Optional[float] = Field(description="앞 칸이 정해졌을 때 이 값이 나올 조건부 확률")
    assumed: bool
    source: str


class CountryOut(BaseModel):
    iso3: str
    name_ko: str
    name_en: str
    region: str
    income_level: str


class NarrativeOut(BaseModel):
    title: str
    paragraphs: List[str]
    narrator: str = Field(description="scripted(템플릿) | llm")
    facts_used: List[str]
    note: Optional[str] = None


class LifeOut(BaseModel):
    seed: int
    country: CountryOut
    steps: List[StepOut]
    joint_p: float = Field(description="이 조합 그대로 태어날 확률(통계 있는 칸의 곱)")
    one_in: Optional[int]
    complete: bool = Field(description="모든 칸에 통계가 있었는가")
    life_expectancy: Optional[float]
    narrative: NarrativeOut


class OddsOut(BaseModel):
    target: TargetIn
    p: Optional[float]
    one_in: Optional[float]
    coverage: float = Field(description="통계가 있어 계산에 들어간 출생아의 비율")
    expected_tries: Optional[float]
    tries_50: Optional[int]
    tries_90: Optional[int]
    steps: List[StepOut]
    reason: Optional[str] = None


class UntilOut(BaseModel):
    found: bool
    tries: int
    max_tries: int
    odds: OddsOut
    life: Optional[LifeOut] = None


class ValueMeta(BaseModel):
    value: str
    label: str


class NodeMeta(BaseModel):
    label: str
    values: List[ValueMeta]
    source: str


class CountryMeta(BaseModel):
    iso3: str
    name_ko: str
    share: float


class MetaOut(BaseModel):
    nodes: Dict[str, NodeMeta]
    countries: List[CountryMeta]
    sources: Dict[str, str]
    snapshot: Dict[str, object]


class ConfigOut(BaseModel):
    version: str
    mode: str = Field(description="offline: AI 없이 동작 | live: 모델 사용")
    narrator: str


class StoryRequest(BaseModel):
    seed: int = Field(ge=0, le=MAX_SEED, description="/api/simulate가 돌려준 시드")
    country: CountryCode = Field(default=None, min_length=3, max_length=3, description="그 뽑기에서 국가를 고정했다면 같은 값")


class LlmCallOut(BaseModel):
    role: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Optional[float]
    ms: int


class PlanStepOut(BaseModel):
    id: str
    tool: str
    metric: Optional[str]
    why: str


class StoryOut(BaseModel):
    seed: int
    narrative: NarrativeOut
    plan: List[PlanStepOut] = Field(description="ReWOO 계획자가 고른 조회")
    attempts: int = Field(description="작성자가 쓴 횟수(검증에 걸리면 다시 쓴다)")
    violations: List[List[float]] = Field(description="시도마다 근거에 없거나 빠진 숫자")
    llm_calls: List[LlmCallOut]
    cost_usd: float
