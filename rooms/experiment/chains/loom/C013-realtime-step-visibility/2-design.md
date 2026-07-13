# 2. 실험 설계

## 절차 (판정 표를 겸해 선고정)

1. **스키마** — `step: 1..5` (선택 필드). R9: 존재하면 1~5 정수, `status: closed`이면서 존재하면 5. 템플릿에 `step: 1` 추가. 스텝 이름: 1 가설 · 2 설계 · 3 검증 · 4 분석 · 5 보고.
2. **도구 (v0.6.0)** — `gil open`: step:1 기록 + `--git`(열림 커밋 "gil: open …") + `--push` 신설. `gil step <chain> <id> <n>`: 열린 사이클만, 1~5 검증, 갱신 커밋 "gil: step … → n/5" (+--push). `gil close`: step을 5로 마감, `--push` 추가. fsck: R9.
3. **뷰어** — gil-data JSON에 step 포함. SVG의 열린 노드 둘째 줄: `open · ●●●○○ 3/5 검증`. 테이블 상태 칸에 동일 표기.
4. **conformance 확장** — STEP-OK(전이 반영), STEP-REJECT-RANGE(범위 밖 거부+무변화), STEP-REJECT-CLOSED(닫힌 사이클 거부), FSCK-R9, OPEN-CREATE에 step:1 요건 추가, WEB-JSON에 step 존재 요건. 기존 항목 무회귀.
5. **판정** — conformance × 파이썬 v0.6.0 전항목 PASS. 릴리스 v0.6.0.
6. **시연** — 이 사이클의 3→4→5 전이를 **새 도구의 `gil step --git --push`로** 수행 (1·2는 도구 탄생 전이라 수동 커밋 — 기록됨). 원격 git log에 전이 커밋이 남는지 확인.

## 측정 방법

| # | 항목 | 통과 기준 |
|---|---|---|
| 1 | 도구·정합 | conformance(확장판) 전항목 PASS — 신설 STEP·R9 포함, 기존 회귀 0 |
| 2 | 표시 | 실제 레포 web: 열린 C013의 JSON에 step, 렌더에 스텝 인디케이터 |
| 3 | 시연 | 원격 git log에 C013의 open·스텝 전이·close가 독립 커밋으로 존재 |

## 사용자 컨펌

- [x] 컨펌 받음 (2026-07-14, 박상현 — 기능 자체가 사용자 제안: "스텝별로 커밋을 한다던지")
