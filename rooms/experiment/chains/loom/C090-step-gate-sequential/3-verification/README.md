# 3. 검증 — step-by-step 강제

## 재현 (임시 저장소, 새 gil)
```bash
gil open demo first --new-chain --title t --author me
ls .../C001-first/                 # M1: 1-hypothesis.md + cycle.yaml만
gil step demo C001-first 2         # M2a: 거부(스텝1 미완)
gil step demo C001-first 5         # M3: 거부
printf '# 1\n\n실질 내용\n' > .../1-hypothesis.md
gil step demo C001-first 2         # M2b: 통과 + 2-design 생성 + 다음 안내
```

## 결과
| 측정 | 기대 | 결과 |
|---|---|---|
| M1 open 1스텝만 | 1-hypothesis+cycle.yaml만 | PASS |
| M2a 미완 가드 | step 2 거부·무변화 | PASS |
| M3 순차 | step 5 바로 거부 | PASS |
| M2b 전이+생성+안내 | 통과·2-design 생성·다음 안내 | PASS |
| M5 뷰어 | 없는 스텝 "아직 — 이전 스텝 완수 필요" | PASS (gil-data content null + JS 문구) |
| M6 하위호환 | 기존 5파일 사이클 fsck 0 | PASS |
| M7 사전등록 보존 | 1에 kill조건 쓰고 step 2 통과 | PASS (내용 불제약) |
| M8 회귀 | baseline 5 FAIL 동일 | PASS(0) |
| STEP-GATE conformance | only_step1·blocked·advanced | PASS |

## 코드 변경 (gil.py)
- `_STEP_SCAFFOLD`·`_step_written`·`_content_substantive`·`_create_step_file` 신설.
- `open`: 1-hypothesis만 스캐폴딩(커스텀 _template의 1스텝 존중).
- `cmd_step`: 전이 가드(1..N-1 실질 작성 검증, 미완이면 무변화 거부) + 다음 스텝 생성 + 안내 출력.
- 뷰어 `stepHtml`/`renderMd`에 emptyMsg 인자, 스텝은 "아직 — 이전 스텝 완수 필요"(존재 문서는 "(없음)" 유지).

## dogfooding 한계 (정직)
이 사이클(C090) 자신은 **옛 gil로 열려** 5파일이 다 스캐폴딩됐다(step-by-step 강제 이전). 그래서 이 사이클로는 새 open의 "1스텝만"을 자기검증할 수 없어, 임시 저장소 + 새 gil로 M1~M3를 검증했다. 다음 사이클부터 새 open이 적용된다.

## 밟은 버그 (dogfooding이 잡음)
step 4 전이 때 이 사이클 자신이 거부당했다: 1-hypothesis 본문이 "5스텝을 전부 `(작성할 것)`로 스캐폴딩"이라고 그 문구를 **인용**했는데, 초기 `_content_substantive`가 "스캐폴딩 마크가 텍스트 어디든 있으면 미완"으로 판정해 **거짓 양성**. → 판정을 "본문 실질 줄이 그 마크 하나뿐일 때만 미완"으로 정교화. **새 강제가 자기 자신에게 적용되며(dogfooding) 거짓 양성을 즉시 드러냈다** — 기각 조건 "정상 흐름을 막으면 기각"에 실제로 걸릴 뻔한 것을 잡음.
