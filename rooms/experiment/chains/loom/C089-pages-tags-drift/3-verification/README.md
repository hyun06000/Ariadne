# 3. 검증 — CI 태그 미포함 drift 오표시

## 재현
`_build_releases_data` + `_render_releases_panel`을 세 시나리오로 (임시 저장소):
- A: 현 저장소(태그 71개) → tags_readable=True, in_tag=True.
- B: CHANGELOG만 있고 태그 0(git init+commit, no tag = CI 상태) → tags_readable=False, rdrift 배지 억제.
- C: 태그 일부만(v1.1.0 태그, v1.2.0은 CHANGELOG만) → tags_readable=True, v1.2.0 진짜 drift 배지 유지.
- D: `gil pages -o -`에 `fetch-depth: 0` 포함.

## 결과
| 시나리오 | 기대 | 결과 |
|---|---|---|
| A 태그있음 | readable True, drift 없음 | PASS |
| B CI모사 | readable False, rdrift 억제 | PASS |
| C 진짜 drift | 배지 유지 | PASS |
| D 워크플로 | fetch-depth: 0 | PASS |
| E 회귀 | baseline 5 FAIL 동일 | PASS(0) |

## 원인
CLI `gil releases`·로컬 `gil web`은 태그(71개)를 읽어 전부 `[TC]`인데, github.io는 CI의 `actions/checkout@v4`가 태그를 안 가져와(shallow) 뷰어가 in_tag=False → 전 릴리스 "⚠ CHANGELOG만". 근본=워크플로 fetch-depth, 방어=뷰어가 "태그 못 읽음"을 감지해 오탐 억제.
