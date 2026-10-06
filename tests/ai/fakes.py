"""각본 LLM(6주차): 실제 API 대신 정해 둔 응답을 순서대로 돌려준다. 키도 네트워크도 필요 없다."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List, Union


def response(arguments: Union[Dict[str, Any], str], model: str = "fake/model") -> SimpleNamespace:
    args = arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)
    call = SimpleNamespace(function=SimpleNamespace(arguments=args))
    return SimpleNamespace(
        model=model,
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call], content=None))],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
    )


class ScriptedLLM:
    def __init__(self, responses: List[Any]) -> None:
        self.responses = list(responses)
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
