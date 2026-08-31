---
id: cycle/revisit/target
title: 되돌아갈 곳을 Cycle Report 에 적는다
summary: 실패한 Cycle 을 닫을 때 어느 조상으로 돌아갈지 함께 확정한다. 값은 canonical CycleRef 하나다.
applies_when:
  cycle_kind: experiment
  cycle_status: open
  step_kind: outcome
  step_status: closed
related:
  - cycle/revisit
  - cycle/experiment/close
---

[언제 읽는가]
  `gil close` 가 `next_direction.target_cycle_ref` 가 없다고 거절했을 때.
  적어 둔 값이 Cycle 주소로 읽히지 않거나, 이 Graph 에서 성립하지 않는다고 거절당했을 때.

[지금 할 일]
  Cycle Report 의 다음 방향 옆에 갈 곳을 한 줄 더 적는다.

      next_direction.action: revisit
      next_direction.target_cycle_ref: cycle:C2

[불변식]
  값은 `cycle:C2` 꼴의 canonical reference 하나다. bare `2` · 화면 축약 `#2` · 종류 없는 `C2`
  는 영구 reference 가 아니라 거절된다. `step:C1/S2` 나 `snapshot:A1` 처럼 **다른 종류의
  주소**도 여기 올 수 없다.

  대상은 지금 닫는 Cycle 의 **구조적 조상**이어야 한다. 자기 자신도, 형제도, 자손도 아니다.
  걸어온 길은 부모만 따라간다.

  대상은 닫혀 있어야 하고, 그 아래에 새 Cycle 이 날 수 있는 자리여야 한다.

  이 칸은 `action` 에 따른 조건부 칸이다. `revisit` 이면 필수이고, 그 밖의 방향에는
  **적을 수 없다** — 돌아갈 자리가 없는 방향이기 때문이다.

  한 번 적으면 확정이다. `gil revisit` 은 이 값을 읽을 뿐 인수로 다시 고르지 않는다.

[올바른 예]
      gil close <<'EOF'
      verdict: failure
      outcome_ref: step:C3/S5
      handoff_summary: 이 접근으로는 성공 조건을 채우지 못한다
      next_direction.action: revisit
      next_direction.target_cycle_ref: cycle:C2
      next_direction.reason: C2 가 확정한 세계에서 다른 가설을 시도한다
      EOF

[흔한 실패]
      next_direction.target_cycle_ref: 2
      next_direction.target_cycle_ref: #2
      next_direction.target_cycle_ref: step:C2/S5

  셋 다 거절된다. 앞의 둘은 종류가 없고, 마지막은 Step 의 주소다.

  성공으로 닫으면서 갈 곳을 적는 것도 거절된다. 성공은 자식을 열지 되돌아가지 않는다.

[관련 주제]
  cycle/revisit
