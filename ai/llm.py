"""LLM 호출의 유일한 관문. 모든 호출은 LiteLLM을 지난다.

- 구조화 출력: Pydantic 스키마를 도구로 등록하고 tool_choice로 그 도구를 강제한다(5주차 방식 3).
  스키마 검증에 실패하면 오류를 담아 한 번 다시 묻는다.
- 신뢰성: LiteLLM의 재시도(num_retries)와 폴백 체인(fallbacks).
- 지갑: 호출마다 비용을 장부에 쌓고, 상한을 넘으면 더 부르지 않는다(budget guard).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Type, TypeVar

from pydantic import BaseModel, ValidationError

log = logging.getLogger("reborn.llm")
T = TypeVar("T", bound=BaseModel)


class LlmError(Exception):
    """모델 쪽이 실패했다(제공자 장애, 형식을 끝내 못 맞춤)."""


class BudgetExceeded(LlmError):
    """누적 비용이 상한에 닿았다. 더 부르지 않는다."""


@dataclass(frozen=True)
class LlmCall:
    role: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Optional[float]
    ms: int
    ok: bool
    error: Optional[str] = None


class Ledger:
    """프로세스 안의 누적 비용 장부. 요청이 여럿이어도 한 장부를 본다."""

    def __init__(self, limit_usd: float) -> None:
        self.limit_usd = limit_usd
        self.spent_usd = 0.0
        self._lock = threading.Lock()

    def check(self) -> None:
        with self._lock:
            if self.spent_usd >= self.limit_usd:
                raise BudgetExceeded(f"누적 ${self.spent_usd:.4f} ≥ 상한 ${self.limit_usd}")

    def add(self, cost: Optional[float]) -> None:
        with self._lock:
            self.spent_usd += cost or 0.0


def _inline_refs(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Pydantic의 $defs/$ref를 펼친다. 제공자마다 $ref 지원이 달라서 평평한 스키마로 보낸다."""
    defs = schema.get("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            out = {}
            for k, v in node.items():
                if k in ("$defs", "title"):  # 스키마 메타데이터의 title — 필드 이름 title과 다르다
                    continue
                # properties 아래의 키는 필드 이름이다. 이름이 title이어도 지우면 안 된다
                out[k] = {name: resolve(sub) for name, sub in v.items()} if k == "properties" else resolve(v)
            return out
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


def _default_completion(**kwargs: Any) -> Any:
    import litellm  # 무거운 의존성은 실제로 부를 때만

    return litellm.completion(**kwargs)


def _default_cost(response: Any) -> Optional[float]:
    try:
        import litellm

        return float(litellm.completion_cost(response))
    except Exception:  # 단가표에 없는 모델 — 비용을 모른다고 기록한다
        return None


class LlmClient:
    def __init__(
        self,
        model: str,
        fallbacks: Sequence[str] = (),
        ledger: Optional[Ledger] = None,
        timeout: float = 30.0,
        num_retries: int = 2,
        completion_fn: Callable[..., Any] = _default_completion,
        cost_fn: Callable[[Any], Optional[float]] = _default_cost,
    ) -> None:
        self.model = model
        self.fallbacks = list(fallbacks)
        self.ledger = ledger or Ledger(limit_usd=1.0)
        self.timeout = timeout
        self.num_retries = num_retries
        self._completion = completion_fn
        self._cost = cost_fn

    def structured(
        self, role: str, messages: List[Dict[str, Any]], schema: Type[T], tool_name: str, description: str
    ) -> Tuple[T, List[LlmCall]]:
        """schema 모양의 객체를 돌려받는다. 형식이 틀리면 오류를 보여 주고 한 번 더 묻는다."""
        tool = {
            "type": "function",
            "function": {"name": tool_name, "description": description, "parameters": _inline_refs(schema.model_json_schema())},
        }
        calls: List[LlmCall] = []
        msgs = list(messages)
        last_error = ""
        for attempt in range(2):
            self.ledger.check()
            response, call = self._call(role, msgs, tool, tool_name)
            calls.append(call)
            raw = ""
            try:
                raw = response.choices[0].message.tool_calls[0].function.arguments
                return schema.model_validate(json.loads(raw)), calls
            except (ValidationError, json.JSONDecodeError, AttributeError, IndexError, TypeError) as e:
                last_error = str(e)[:800]
                log.info("STRUCTURED RETRY role=%s attempt=%d error=%s", role, attempt + 1, last_error[:200])
                msgs = msgs + [
                    {"role": "assistant", "content": f"(이전 출력) {raw[:2000]}"},
                    {"role": "user", "content": f"출력이 스키마에 맞지 않았다. 오류: {last_error}\n{tool_name}을 다시 호출해 고쳐라."},
                ]
        raise LlmError(f"{role}: 형식을 맞추지 못했다 ({last_error[:200]})")

    def _call(self, role: str, messages: List[Dict[str, Any]], tool: Dict[str, Any], tool_name: str) -> Tuple[Any, LlmCall]:
        start = time.perf_counter()
        try:
            response = self._completion(
                model=self.model,
                messages=messages,
                tools=[tool],
                tool_choice={"type": "function", "function": {"name": tool_name}},
                fallbacks=self.fallbacks or None,
                num_retries=self.num_retries,
                timeout=self.timeout,
            )
        except Exception as e:
            ms = int((time.perf_counter() - start) * 1000)
            log.warning("LLM CALL FAILED role=%s model=%s error=%s", role, self.model, type(e).__name__)
            raise LlmError(f"{role}: 모델 호출 실패 ({type(e).__name__})") from e

        ms = int((time.perf_counter() - start) * 1000)
        usage = getattr(response, "usage", None)
        cost = self._cost(response)
        self.ledger.add(cost)
        call = LlmCall(
            role=role,
            model=str(getattr(response, "model", self.model)),
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            cost_usd=cost,
            ms=ms,
            ok=True,
        )
        log.info(
            "LLM CALL role=%s model=%s in=%d out=%d cost=%s ms=%d",
            role, call.model, call.prompt_tokens, call.completion_tokens, cost, ms,
        )
        return response, call
