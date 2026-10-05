# AGENTS.md

## 개발 명령
- 실행: `docker compose up --build` (개발: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up`)
- 테스트: `pytest`
- 데이터 재생성: `python scripts/fetch_worldbank.py && python scripts/prepare_data.py`

## 커밋 전 검증
- `pytest`가 키 없이 통과해야 한다
- 작업 단위마다 커밋한다. 한 커밋에 한 주제
- 코드를 바꾸면 같은 커밋에서 관련 문서(`docs/`)도 고친다

## 규칙
- `develop`에서 `feature/*`로 분기. `master`에 직접 커밋 금지
- 커밋 메시지 제목은 영어 명령형 한 줄, 이유는 본문에
- `.env`와 키는 절대 커밋하지 않는다. `data/raw/`도 커밋하지 않는다
- 의존성을 새로 추가하기 전에 물어본다
- 태그는 사람이 찍는다

## 설계 규칙
- 확률·숫자는 `core/`의 순수 함수가 낸다. LLM이 숫자를 만들게 하지 않는다
- `core/`는 FastAPI·LiteLLM을 import하지 않는다
- 통계가 없으면 0이 아니라 None(데이터 없음)이다
- AI 자리는 `core/narrator.py`의 `Narrator` 하나. 시그니처를 바꿔야 하면 먼저 말한다
- Python 3.9에서도 돌아야 한다 (`Optional[...]`, `from __future__ import annotations`)
