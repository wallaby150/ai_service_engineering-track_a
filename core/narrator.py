"""AI가 들어갈 자리: 뽑힌 사실로 그 사람의 이야기를 쓴다.

자리는 이 Protocol 하나다. v0.2는 템플릿 각본 대역(ScriptedNarrator)이,
v0.5는 LLM 구현이 같은 시그니처로 들어온다. 어느 쪽이 썼는지는 Narrative.narrator가 말한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Tuple

from core.engine import Life


@dataclass(frozen=True)
class Narrative:
    title: str
    paragraphs: Tuple[str, ...]
    facts_used: Tuple[str, ...]  # core/facts.py의 키 — 이야기가 기댄 사실
    narrator: str  # "scripted" | "llm"
    note: Optional[str] = None  # 폴백 사유 등 화면에 알릴 말


class Narrator(Protocol):
    name: str

    def narrate(self, life: Life) -> Narrative:
        """같은 Life에는 같은 사실만 써야 한다. 숫자를 새로 만들지 않는다."""
        ...
