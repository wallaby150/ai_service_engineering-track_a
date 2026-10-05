# Git 작업 방식

git flow를 쓴다. 혼자 하는 프로젝트지만 협업이 아니라 **되돌리기와 검수**를 위해서다.

## 브랜치

| 브랜치 | 역할 |
|---|---|
| `master` | 배포되는 것만. 직접 커밋하지 않는다 (12주차 배포의 방아쇠) |
| `develop` | 기본 작업 브랜치. 모든 회전이 여기서 갈라지고 여기로 돌아온다 |
| `feature/<이름>` | 회전 하나 = 지시 하나 |
| `release/<버전>` | 태그 전 정리. 혼자일 때는 건너뛸 수 있다 |
| `hotfix/<이름>` | 배포된 것이 고장났을 때만 |

> 저장소가 `master`로 시작했으므로 릴리스 브랜치 이름은 `master`를 그대로 쓴다.

## 회전 하나의 모양

```bash
git switch develop && git pull
git switch -c feature/<이름>
# ... 작업 단위마다 커밋 ...
git switch develop && git merge --no-ff feature/<이름>
```

릴리스:

```bash
git switch master && git merge --no-ff develop
git tag -a v0.X -m "<한 줄 요약>"     # 태그는 사람이 찍는다
git push origin master develop --tags
```

## 커밋 규칙

- 작업 단위마다 커밋한다. 한 커밋에 한 주제
- 제목은 영어 명령형 한 줄(예: `Add the conditional sampling engine`), 이유는 본문에
- 코드와 그 코드를 설명하는 문서는 같은 커밋에서 고친다
- 마음에 안 드는 회전은 브랜치째 버린다: `git switch develop && git branch -D feature/<이름>`

## 태그

| 태그 | 의미 |
|---|---|
| v0.1 | 문서·샘플 화면 — "무엇을 만들 것인가" |
| v0.2 | AI 없이 도는 제품 — 기준선 |
| v0.5 | AI 자리 하나 — v0.2와 비교해 좋아진 것 |
| v1.0 | 배포 — 남의 기계와 공개 URL에서 동작 |
