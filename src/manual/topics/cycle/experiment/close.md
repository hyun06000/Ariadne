---
id: cycle/experiment/close
title: Experiment Cycle 을 닫는다
summary: 안의 판정이 끝난 실험을 Cycle Report 로 닫는다. 안의 Step 을 옮겨 적지 않고, 마지막 Outcome 을 가리켜 같은 판정을 말한다.
applies_when:
  cycle_kind: experiment
  cycle_status: open
  step_kind: outcome
  step_status: closed
related:
  - cycle/revisit/target
  - step/verify/close
  - current
---

[언제 읽는가]
  Experiment 안의 Outcome 까지 닫혀 이제 Cycle 자체를 닫을 자리일 때.
  `gil close` 가 Cycle Report 의 칸이나 값을 거절했을 때.

[지금 할 일]
  이 Cycle 을 닫는 Report 를 `gil close` 에 stdin 으로 넘긴다.
  요구하는 칸과 고를 수 있는 값은 이것뿐이다.

{{close_contract:experiment}}

[불변식]
  verdict 는 안의 **마지막 Outcome 과 같은** 판정이다. 두 계층이 다른 말을 하면 거절된다.
  outcome_ref 는 그 마지막 Outcome 의 **주소**다 — 화면의 `#5` 가 아니고, 이름이 가장 큰
  것도 아니다. 지금 서 있는 그 자리다.
  handoff 는 다음 Cycle 이 반드시 받아야 할 결과·실패·제약이고, 비울 수 없다.
  `revisit` 을 고르면 **어느 조상으로 돌아갈지도 함께** 적는다 —
  `next_direction.target_cycle_ref: cycle:C2`. 그 칸의 규칙은 `cycle/revisit/target` 에 있다.

  next_direction 은 verdict 가 허락하는 것만 고를 수 있다 — 무엇이 허락되는지는 위에 있다.

  **Cycle Report 는 안의 Step 을 복제하지 않는다.** 무엇을 했는지는 이미 그 자리들에
  적혀 있고, 여기 옮겨 적으면 같은 사실이 두 자리에 살며 한쪽이 낡는다.

  위 목록에 「아직 없음」으로 적힌 값이 있다면 **틀린 값이 아니라 아직 밟을 수 없는
  값**이다. 적을 수는 있으나 그 이동은 지금 걷기가 이어지지 않는다.

[올바른 예]
      gil close <<'EOF'
      verdict: success
      outcome_ref: step:C2/S5
      handoff_summary: 무효한 설정값이 다음 우선순위로 물러난다. 경계는 1 이상의 정수뿐이다
      next_direction.action: open_child
      next_direction.reason: 검증이 끝나 다음 실험으로 넘어간다
      EOF

[흔한 실패]
  `outcome_ref: #5` — 화면에 보이는 짧은 이름을 적었다. 그것은 **주소**라 `step:C2/S5`
  꼴이어야 한다. 안의 마지막 Outcome 이 `failure` 인데 Cycle 을 `success` 로 닫으려는
  것도 거절된다 — Cycle Report 가 제 안의 기록과 다른 말을 하게 되기 때문이다.

[관련 주제]
  step/verify/close
  current
