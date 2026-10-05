# 다시 태어난다면 — 공공 통계 기반 인생 시뮬레이터

"어디서 태어나느냐가 삶을 얼마나 바꾸는가"는 막연하게만 알려져 있다. 출생아 수, 출생 성비,
영아사망률, 빈곤율 같은 통계는 UN·World Bank·통계청에 흩어져 있고, 표마다 단위와 분류가 달라서
**한 사람의 삶으로 이어 볼 방법이 없다.**

이 서비스는 흩어진 공공 통계를 **하나의 조건부 확률 모델**로 묶는다. 버튼 한 번이 실제 통계에
비례해 뽑힌 한 사람의 출생 조건이 되고(국가 → 성별 → 다섯 살까지의 생존 → 가정의 경제 수준),
반대로 "내가 원하는 조건으로 태어날 확률"이 얼마나 되는지, 그 조건이 나올 때까지 몇 번을 다시
태어나야 하는지도 숫자로 보여 준다.

확률과 숫자는 전부 **코드가 계산**한다. AI(LLM)는 뽑힌 사실을 근거로 그 삶의 이야기를 쓰는
자리에만 들어가고, AI가 없어도 서비스는 그대로 동작한다. 목표는 재미있는 뽑기가 아니라
**출생의 우연과 불평등을 숫자로 체감**하게 하는 것이다.

## 현재 상태

| 버전 | 내용 | 상태 |
|---|---|---|
| v0.1 | 문서, 확률 모델 설계, 동작하지 않는 샘플 화면 | 완료 |
| v0.2 | AI 없이 도는 뽑기·역확률 + 목 UI + 테스트 | 완료 |
| v0.3 | 한국 상세(시도·직업·소득 분위) | 예정 |
| v0.5 | AI 인생 서사(ReWOO) | 예정 |

## 실행 방법

API 키가 하나도 없어도 전부 돈다. 이야기는 템플릿(각본 대역)이 쓴다.

```bash
docker compose up --build        # → http://localhost:8000  (API 문서: /docs)
docker compose exec app pytest   # 테스트
```

개발할 때는 소스를 마운트하고 고치면 바로 다시 뜬다.

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Docker 없이:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn api.main:app --reload
```

### 할 수 있는 것

| 화면 | API | 하는 일 |
|---|---|---|
| 다시 태어나기 | `POST /api/simulate` | 통계에 비례해 국가 → 성별 → 다섯 살까지의 생존 → 경제 수준을 뽑는다. 국가를 고정할 수 있고, 같은 시드는 같은 인생(공유 링크) |
| 이렇게 태어날 확률 | `POST /api/odds` | 고른 조건의 정확한 확률, 평균 시도 횟수, 50%·90% 확률로 나오는 횟수 |
| 될 때까지 다시 태어나기 | `POST /api/until` | 조건이 나올 때까지 실제로 뽑는다(상한 10만 번) |

### 데이터 다시 만들기

```bash
python scripts/fetch_worldbank.py   # 원본 → data/raw/ (커밋하지 않음)
python scripts/prepare_data.py      # → data/snapshot/ + reports/prepare_report.txt
```

## 데이터 출처

| 데이터 | 출처 | 쓰는 곳 |
|---|---|---|
| 조출생률, 총인구 → 국가별 출생아 수 | World Bank WDI (`SP.DYN.CBRT.IN`, `SP.POP.TOTL`) | 국가 |
| 출생 성비 | World Bank WDI (`SP.POP.BRTH.MF`) | 성별 |
| 영아·5세 미만 사망률(성별) | World Bank WDI / UN IGME (`SP.DYN.IMRT.*`, `SH.DYN.MORT.*`) | 생존 |
| 기대수명(성별) | World Bank WDI (`SP.DYN.LE00.*`) | 맥락 정보 |
| 하루 $3.00 / $4.20 / $8.30 빈곤율(2021 PPP) | World Bank PIP (`SI.POV.DDAY`, `SI.POV.LMIC`, `SI.POV.UMIC`) | 경제 수준 |

통계마다 가정과 한계가 있다. 무엇을 어떻게 이어 붙였는지는 [docs/probability-model.md](docs/probability-model.md)에 있다.

## 문서

- [docs/architecture.md](docs/architecture.md) — 층 구조와 책임
- [docs/probability-model.md](docs/probability-model.md) — 조건부 확률 체인, 출처, 가정
- [docs/decisions.md](docs/decisions.md) — 정한 것, 미룬 것, 뺀 것
- [docs/git-workflow.md](docs/git-workflow.md) — 브랜치와 커밋 규칙
- [AGENTS.md](AGENTS.md) — 코딩 에이전트용 작업 규칙

## 라이선스

코드는 [MIT](LICENSE). 데이터는 각 출처의 이용 조건을 따른다(World Bank 데이터는 CC BY 4.0).

---

## 학습 기록 (AI 서비스 엔지니어링 Track A)

- 현재 상태 :
  <br>Mac OS로 개발을 처음 도전해보고 있는데 아직은 많이 낯섭니다. 그래도 이번 기회에 다양한 개발 환경에서도 개발 해보는 경험을 해보고자 합니다.
  <br>앞으로 배워나갈 내용을 잘 따라갈 수 있을지 조금은 우려스럽기도 하지만 꼭 많은 것들을 얻어가며 수료하고자 노력하겠습니다.
  <br>AI와 함께 능동적으로 성장하는 개발자가 되어 인정받는 동료가 되고 싶습니다!
