# 아키텍처

## 층 그림

```mermaid
graph LR
  B[브라우저] -->|HTTP| W[web/<br/>정적 화면]
  W -->|fetch JSON| API[api/<br/>FastAPI · 계약 · 에러 번역]
  API --> CORE[core/<br/>확률 엔진 · 서사 자리]
  CORE --> DATA[(data/snapshot/<br/>정제된 확률표)]
  S[scripts/<br/>수집 · 정제] -->|만든다| DATA
  CORE -.AI 자리 · 미정.-> LLM[LLM]
```

## 층별 책임

| 층 | 한다 | 안 한다 |
|---|---|---|
| `web/` | 입력 받기, 결과 그리기, 진행·에러 표시 | 확률 계산, 데이터 해석 |
| `api/` | 요청 검증(Pydantic), 코어 호출, 에러를 HTTP 상태로 번역 | 확률 계산, 통계 보관 |
| `core/` | 조건부 확률 체인, 뽑기, 역확률, 목표 달성 횟수, 서사 자리 | HTTP, 파일 경로 하드코딩, 모델 SDK 직접 호출 |
| `data/snapshot/` | 정제된 확률표와 출처·연도 기록 | 원본(raw)은 두지 않는다 |
| `scripts/` | 원본 수집, 정제, 리포트 | 서비스 실행 중에는 돌지 않는다 |

## 경계 두 개

1. **숫자는 `core/`만 낸다.** 화면도, API도, 나중에 붙을 LLM도 확률을 계산하지 않는다.
   모든 숫자의 출처는 `data/snapshot/`의 표와 `core/`의 순수 함수 하나다.
2. **`core/`는 문을 모른다.** `core/`는 FastAPI를 import하지 않는다. 그래서 HTTP 외에 MCP 같은
   문을 더 달아도 `core/`는 고치지 않는다.

## AI가 들어갈 자리

**자리는 하나: 뽑힌 사실로 그 사람의 이야기를 쓴다.**

```python
# core/narrator.py
class Narrator(Protocol):
    name: str
    def narrate(self, life: Life) -> Narrative: ...
```

| 구현 | 언제 | 무엇을 하나 |
|---|---|---|
| `ScriptedNarrator` (`core/narrator_scripted.py`) | v0.2~, 키가 없거나 LLM이 실패할 때 | 사실 목록을 정해진 문장에 끼워 넣는다. 화면에 "템플릿 서사"로 표시 |
| LLM 구현 | v0.5 | ReWOO로 맥락을 조회해 이야기를 쓴다. 같은 시그니처 |

- 서사가 기댈 수 있는 사실은 `core/facts.py`의 `facts_of(life)`가 전부다. `Narrative.facts_used`는 그 키 목록이다.
- v0.5에서 LLM 서사에 나온 숫자를 이 사실 목록과 코드로 대조한다. 목록에 없는 숫자는 지어낸 것이다.
- AI가 없어도 뽑기·역확률은 전부 동작한다.
