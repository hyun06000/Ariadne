# 5. 보고 — v3-build/C006-close-seal-and-cycle-states

부모: v3-build/C005-git-imprint-and-viewer-wire (supported). 저자: Clew. 소환자: 없음
(main 단독, Sheen C007 병렬). 판정: **supported (채택)**.

## 요약

C005의 씨앗(close 봉인 표현 + 진행 중/다중 잎)을 풀어, `gilv3` v0.3에 **사이클 상태
분류기**(산 잎 개수로 in_progress/solved/multi_solution 순수 계산)와 **close 게이트**,
그리고 **cycle.yaml 봉인**(steps.yaml과 별개 층)을 붙였다. 세 트리 변형이 정확히 세
상태로 분류되고(M1), in_progress close가 거부되며(M2), 봉인이 steps.yaml을 안 오염시켰다
(M3). 세 kill 조건 미발동 → 닫는다.

## 무엇을 했나

1. **gilv3 v0.3** (C005 복사 후 확장, 닫힌 사이클 C005 원본 불변):
   - `cycle_state(nodes)`: 산 잎 개수로 상태 계산 — 0=in_progress, 1=solved,
     ≥2=multi_solution. **트리에서 순수 계산**(상태 필드 저장 0).
   - close 게이트: in_progress면 거부, solved/multi_solution이면 허용(multi는 경고).
   - **cycle.yaml 봉인**: `state`·`verdict`·`live_leaves`·`closed`를 별개 파일에.
     steps.yaml은 안 건드림. close가 이제 빈 커밋이 아니다(C005 씨앗 해소).
   - status 확장: 사이클 상태·산 잎·죽은 잎 출력.
2. **세 트리 변형** (build-cases.sh): in-progress(산 잎 0)·solved(1)·multi(2)를 gilv3
   명령으로 생성.
3. **측정** (measure.py): M1 분류·M2 게이트+봉인·M3 무오염 — ALL PASS.

## 핵심 발견

- **상태는 "몇 개의 정답에 닿았나"의 순수 함수**: 분류기가 트리 위상을 안 보고 산 잎
  개수만 봤다. multi 변형에서 산 잎 s4·s7 둘을 세어 multi_solution 판정. 상태 계산에
  포인터 순회조차 불필요 — C002 데이터 모델이 상태까지 공짜로 파생한다.
- **게이트가 분류에서 그대로 나왔다**: close 전용 규칙 없이 `cycle_state`가 게이트를
  파생. in_progress에선 cycle.yaml조차 안 생겼다(봉인이 게이트 뒤). "모델이 명령을
  강제한다"(C002 M3)가 open→step(C003)→close(C006) 전 명령에서 성립.
- **봉인도 별개 층**: C005가 "깃은 별개 층"을 세웠고, C006이 "봉인은 cycle.yaml 별개
  파일 층"을 더했다. steps.yaml(논리 트리)은 깃 층·봉인 층 어느 것도 안 오염시킨다 —
  **한 데이터 모델, 여러 직교 층**(트리·깃·봉인).

## 판정 근거

| # | 측정 | 결과 |
|---|---|---|
| M1 | 상태 분류 (3 변형) | ✅ 3/3 |
| M2 | close 게이트 + 봉인 | ✅ in_progress 거부·solved/multi 봉인·multi 경고 |
| M3 | steps.yaml 무오염 | ✅ 6필드, 봉인은 cycle.yaml |

세 kill 조건 미발동, 산 잎 도달 → **닫는다** (그리디).

## 다음 사이클을 위한 제안 (이 보고서가 부모)

- **C007+ 뷰어 상태 배지** (Sheen 병렬 중): cycle.yaml의 state를 뷰어가 배지로
  (in_progress ◐ / solved ● / multi_solution ●●). C004 3제안의 "close 판정 배지"가 이제
  데이터(cycle.yaml)를 갖췄다.
- **C0xx — v3 fsck**: cycle.yaml ↔ steps.yaml 정합(state가 실제 산 잎 개수와 맞나,
  live_leaves가 실제 success 노드와 맞나) 검증. v2 fsck의 v3판.
- 그 뒤: 포기(abandon) 상태 · close 깃 태그 · 다중 정답 선택 알고리즘 · BFS 팁 ·
  `fail` 일원화 · v2 백업+rooms 보존.

## 정직한 경계

- **포기(abandon)와 진행 중을 통합**했다 — 둘 다 "산 잎 0". 포기를 명시하고 싶으면 새
  상태가 필요(씨앗). 지금은 그리디 통합.
- **multi_solution은 분류·봉인만** — "여러 정답 중 무엇을 고르나"의 선택 알고리즘은
  범위 밖(chain.md: 최적화는 새 사이클). 경고만 출력.
- 봉인 검증은 사이클 디렉토리(cases/)에서 파일 조작으로 — v2 gil 원장·태그와는 아직
  독립(gilv3는 프로토타입). v3 fsck·태그는 후속.
- 이 사이클도 v2 고정 5스텝으로 진행. Sheen이 병렬로 C007(상호작용 뷰어)를 짓는 중 —
  land 시 뷰어 상태 배지와 접속 가능.
