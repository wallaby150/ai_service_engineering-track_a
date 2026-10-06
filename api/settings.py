"""환경변수에서 AI 서사를 조립한다. 키가 없으면 None — 서비스는 템플릿 서사로 그대로 돈다.

| 변수 | 기본값 | 뜻 |
|---|---|---|
| NARRATOR_MODEL | (없음) | LiteLLM 모델 문자열. 예: gemini/gemini-3.5-flash-lite |
| NARRATOR_FALLBACKS | (없음) | 쉼표로 구분한 폴백 모델들 |
| STORY_BUDGET_USD | 0.50 | 이 프로세스가 서사에 쓸 수 있는 누적 비용 상한 |
| GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY | | 제공자 키. 하나만 있으면 된다 |
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from core.narrator import Narrator
from core.stats import Snapshot

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_KEYS = ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """.env를 읽어 환경변수에 넣는다. 이미 있는 값(compose가 넣은 값 등)은 덮어쓰지 않는다."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if value.strip():
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def story_model() -> Optional[str]:
    model = os.environ.get("NARRATOR_MODEL", "").strip()
    has_key = any(os.environ.get(k, "").strip() for k in PROVIDER_KEYS)
    return model if model and has_key else None


def build_story_narrator(snapshot: Snapshot, fallback: Narrator):  # -> Optional[LlmNarrator]
    model = story_model()
    if model is None:
        return None
    from ai.llm import Ledger, LlmClient  # 키가 없으면 LiteLLM을 import하지도 않는다
    from ai.narrator_llm import LlmNarrator

    fallbacks = [m.strip() for m in os.environ.get("NARRATOR_FALLBACKS", "").split(",") if m.strip()]
    ledger = Ledger(limit_usd=float(os.environ.get("STORY_BUDGET_USD", "0.50")))
    return LlmNarrator(LlmClient(model, fallbacks=fallbacks, ledger=ledger), snapshot, fallback)
