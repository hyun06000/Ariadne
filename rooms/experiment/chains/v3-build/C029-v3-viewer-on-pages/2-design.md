# 2. 실험 설계

오직 1-hypothesis.md의 가설 — **워크플로에 migrate + web --v3 추가로 v3 뷰어를 Pages에, v2 무회귀** — 을 검증한다.

## 정답을 도구보다 먼저 고정한다

정답: fresh clone에서 워크플로 build run 블록을 실행하면 `_site/v3.html`(v3 두 층 드릴다운)이 생기고, 기존 `_site/index.html`(v2)도 그대로 생긴다. 원격 notes 없이 원장만으로.

## ⭐ 설계 — v3.html 추가 + index 링크 (하위호환)

- 기존 `gil web -o _site/index.html`(v2) **유지**.
- 추가: `gil migrate`(fresh clone에 notes 각인) → `gil web --v3 -o _site/v3.html`.
- index.html에서 v3.html로 링크(사용자가 v3 뷰어에 닿게). 최소: v3.html 접근 가능.
- **원격 notes 불요**: migrate가 원장(커밋)만으로 각인(C026 형태).

## 절차

1. **워크플로 build run 블록 수정.** 기존 index.html 생성 뒤에 migrate + web --v3 추가.
2. **loom/C007 규약 검증.** 워크플로 run 블록을 추출해 fresh clone에서 실행 → v3.html 생성·구조 확인. "워크플로가 곧 테스트."
3. **v2 무회귀.** 같은 실행에서 index.html도 생성.

## ⭐ CI 제약 확인

- **migrate가 CI에서 도는가**: fresh clone은 전 커밋(fetch-depth:0). migrate는 커밋 subject·cycle.yaml에서 도출하니 커밋만 있으면 됨.
- **git user 설정**: migrate가 notes 각인(git notes add)하려면 CI에 user.email/name 필요할 수 있음 — 확인·필요시 워크플로에 추가.
- **커밋 불변**: migrate는 refs/notes만 건드림(C018). CI 원장 안전.

## 준비물

- `ariadne-pages.yml`(수정 대상) + 배포판 gil.py(migrate·web --v3).
- fresh clone 격리 검증 환경.

## 측정 방법 (4측정)

| 측정 | 확인 | 통과 기준 |
|---|---|---|
| **M1 v3 페이지 생성** | fresh clone에서 run 블록 실행 → _site/v3.html 생성, 두 층(DAG+스텝 트리) | 생성·구조 확인 |
| **M2 v2 무회귀** | 같은 실행에서 _site/index.html 생성 유지 | 생성됨 |
| **M3 원장-만 재현** | 원격 notes 없이(삭제 후) migrate → web --v3 성공 | notes 없이도 생성 |
| **M4 커밋 불변** | migrate가 CI clone 커밋 안 바꿈 | digest 불변 |

## 안전 철칙

1. **워크플로 수정은 로컬 실측 후 커밋** — CI는 실제 배포라, run 블록을 fresh clone에서 먼저 재현.
2. **v2 하위호환 최우선** — index.html 계속 생성이 게이트.
3. **loom/C007 검증 규약 준수** — 워크플로 run 블록 = 테스트.
4. **실제 Pages 배포는 push 후 상현님과 확인** — 워크플로 수정·로컬 검증까지 이 사이클.

## 사용자 컨펌

상현님이 "가자. 깃헙io에 보이게 하는 거부터 먼저"로 이 사이클을 우선 지시. 워크플로 수정은 실제 배포 파이프라인이라 loom/C007 규약(run 블록 fresh clone 재현)으로 로컬 실측 후 커밋. 실 배포 확인은 push 후 상현님과. 위임 범위 안 자율 진행.

- [x] 컨펌 받음 (일자: 2026-07-22, "깃헙io에 보이게 하는 거부터 먼저")
