# 1. 가설 수립

## 이전 사이클의 교훈

부모 **C028**이 v3 눈의 읽기 축(`gil web --v3`)을 배포판 gil.py에 통합해, 배포판 gil이 v3 쓰기(migrate)+읽기(web)를 다 갖췄다. "v3만 쓴다"의 도구 기반이 완성됐다.

상현님 방향 전환: **"이거 깃헙io에 보이게 하는 거부터 먼저."** 문서 갱신보다 v3 뷰어가 실제 GitHub Pages에 보이는 게 먼저다 — 실물이 눈에 보이는 값어치.

## 문제 — 지금 Pages는 v2 뷰어만 배포한다

현 상태 확인:
- `https://hyun06000.github.io/Ariadne/` HTTP 200 (살아있음).
- 워크플로 `ariadne-pages.yml`가 push마다 `gil web -o _site/index.html` 생성 — **v2 뷰어**.
- **v3 뷰어(`gil web --v3`)는 Pages에 안 보인다.**

v3 뷰어는 notes를 읽는데, CI(fresh clone)가 notes를 가지려면:
- 원격 notes fetch(오래된 스냅샷 위험, C023 시점 73b18f4a) — 부적합.
- **CI에서 매번 `gil migrate`로 새로 각인**(항상 최신, 원격 notes 불요) — 적합.

## ⭐ 핵심 설계 — CI가 migrate 후 web --v3 (C026 형태 정합)

C026 형태("v3 = v2 위의 눈, 원장만 있으면 눈은 언제든 재각인")가 정답을 준다: CI가 fresh clone에서 **`gil migrate`(notes 각인) → `gil web --v3`(v3 페이지 생성)**. 원격 notes에 안 기대고, 원장(커밋)만으로 항상 최신 v3 눈을 만든다.

## 문제 분할

1. **워크플로에 v3 페이지 생성 추가** — 기존 v2(`index.html`) 유지 + v3(`v3.html` 또는 별 경로) 추가. migrate → web --v3.
2. **검증** — 이 워크플로는 loom/C007 규약("run 블록 추출해 fresh clone에서 실행")으로 검증된다. 추가한 v3 스텝도 그 방식으로 실측.
3. **v2 페이지 무회귀** — 기존 index.html 계속 생성(하위호환).

**첫 번째로 정복할 것: 워크플로에 migrate + web --v3 스텝 추가 + 로컬 실측.** 이유 — 실물이 보이게 하는 게 상현님 우선순위. 가장 작은 카브: v3 페이지 하나를 CI가 만들게 하고 로컬에서 그 스텝을 실측(fresh clone → migrate → web --v3 → HTML 존재·구조 확인).

## 가설

> **가설**: `ariadne-pages.yml` 워크플로의 build 스텝에 `gil migrate`(notes 각인) + `gil web --v3 -o _site/v3.html`(v3 페이지 생성)를 추가하면, (a) fresh clone에서 그 run 블록을 추출·실행했을 때 v3 페이지가 생성되고(상위 계보 DAG + 하위 스텝 트리 두 층), (b) 기존 v2 index.html 생성은 무회귀이며, (c) 원격 notes에 안 기대고 원장만으로 최신 v3 눈이 만들어진다 — 즉 push 시 v3 뷰어가 GitHub Pages에 보이게 된다.

## 기각 조건

- fresh clone에서 migrate → web --v3가 v3 페이지를 못 만들면 → **기각**(CI 재현 실패).
- 추가한 스텝이 기존 v2 index.html 생성을 깨면 → **기각**(회귀).
- v3 페이지가 원격 notes에 의존해야만 생기면 → **기각**(원장-만-으로 재현 실패, C026 형태 위반).
- 워크플로 run 블록이 loom/C007 검증 방식으로 실측 불가하면 → **조사**(검증 규약 이탈).
