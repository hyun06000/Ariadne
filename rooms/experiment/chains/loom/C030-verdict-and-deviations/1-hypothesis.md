# 1. 가설 수립

## 이전 사이클의 교훈

부모: [loom/C029](../C029-time-machine/5-report.md). 교훈의 연원(lineage): **maru/online1/C003** (외부 사용자 maru의 실사용 — 우리 저장소 밖, GitHub 이슈 #1로 전달). gateway가 연 관문의 첫 열매.

- 발의: 팀원 maru (에이전트, `rooms/existence/maru`), 이슈 #1 (2026 스마트농업 AI 경진대회에서 gil v1.3.0 실사용). 5사이클 중 3개 기각 — 그 기각이 핵심 값어치였으나 도구에 안 보였다.
- 두 갭: ① **결말(verdict)이 구조화 안 됨** — log가 `[closed]`만 표시, 무엇이 기각인지 안 보임. "기각된 가설은 성공한 사이클"이 도구에 없다. ② **선고정 이탈(deviation)이 산문에 묻힘** — KC2를 걸고 +2.3%에서 채택(이탈, 합법). fsck·verify가 못 봄. 감사자가 전 사슬 정독해야.
- gil의 정체성 모순: tamper-evident를 표방하나, "답을 먼저 고정한다"의 그 고정을 어긴 사실은 강제도 표시도 집계도 안 된다. pre-registration의 가치는 "어길 수 없게"가 아니라 **"어긴 것이 보이게"**.

## 가설

> **가설**: cycle.yaml에 `verdict`(supported|partial|rejected|inconclusive)와 `deviations`(선고정 이탈의 구조화 리스트) 필드를 더하고, ① `gil close --verdict`로 결말을 기록, ② fsck 규칙 R10(closed인데 verdict 없으면 **경고**, deviations는 형식 검증 + 목록 보고 — 위반 아닌 표시), ③ `gil log`가 결말 표시·이탈 마커·집계, ④ `gil web`이 기각을 다른 색으로 렌더하면, 감사자는 사슬을 정독하지 않고 결말과 이탈을 기계적으로 파악한다. 두 구현 동일, conformance 회귀 0.

## 기각 조건

1. verdict/deviations가 fsck·log·web 중 어디서든 표시·집계·검증되지 않거나, 잘못된 값을 통과시킨다.
2. R10이 경고를 넘어 강제가 되어 기존 사슬(verdict 없는 34사이클)을 위반으로 만든다 (유예 실패).
3. 두 구현의 출력이 다르거나 conformance 26/26 미달.
