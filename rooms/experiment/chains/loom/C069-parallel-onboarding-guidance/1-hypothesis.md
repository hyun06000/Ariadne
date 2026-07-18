# 1. 가설 수립

## 이전 사이클의 교훈

C050~C062로 병렬(worktree) 기능 — `gil worktree add/land`, 예약, 주 체크아웃 소유 guard — 을 완성했으나, 상현님 관찰: **"길을 최신 버전으로 받은 클로드가 병렬 기능을 사용하지 않는다. 안내가 잘 되어 있나?"** 감사 결과(3-verification/audit-before.md): 기능은 `gil help worktree`로 탐침되지만, 신규 에이전트가 읽는 온보딩 경로(README.ai.md·QUICKSTART·CLAUDE.md §3·experiment/README)의 병렬 언급이 **전부 0**이고, SPEC 명령 표엔 `gil worktree` 행조차 없다.

## 문제 분할

병렬 기능은 "만들어졌지만 안내되지 않았다". 안내 공백을 신규 에이전트의 읽기 경로에 메운다:
1. **README.ai.md** — 자율 온보딩 스크립트. 병렬 섹션("Step E")이 없으니 순차만 배운다. → 여기가 최고 레버리지.
2. **CLAUDE.md §3** — 부트스트랩. "사이클로 일하라"가 순차 전용. → 병렬 워크트리 문단.
3. **SPEC** — 명령 표에 `gil worktree add/land` 행 부재, §6가 명령을 안 가리킴. → 표 행 + §6.8(v3).
4. **QUICKSTART** — 병렬 절 부재. → §4.5 + `gil help worktree` 포인터.

도구 코드(gil.py·go)는 안 바꾼다 — 기능이 아니라 **안내**가 문제다.

## 가설

> **가설**: 병렬 워크트리 워크플로(`gil worktree add`로 격리 사이클, `land`로 병합, 소유 guard, "네 워크트리에서 일하라")를 신규 에이전트의 읽기 경로 4곳(README.ai.md·CLAUDE.md·SPEC·QUICKSTART)에 명시하면, 온보딩만으로 병렬 기능을 발견·사용할 수 있게 되고, 도구 코드 무변경이라 flat·conformance·양 구현 바이트는 그대로다.

## 기각 조건

- 안내 추가 후에도 신규 에이전트 경로(README.ai.md·QUICKSTART·CLAUDE.md)에서 병렬 워크플로를 못 찾으면 기각.
- 도구 파일(gil.py·go·conformance.py)이 바뀌거나 conformance가 90/90·83/83에서 회귀하면 기각(이 사이클은 문서 전용이어야 함).
