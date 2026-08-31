---
id: step/verify/close
title: Verify 를 닫아 세계를 확정한다
summary: 가설대로 실행한 결과를 적어 닫는다. 그 순간 지금 폴더가 관측되어 Snapshot 이 된다. Verify 에는 판정이 없다.
applies_when:
  cycle_kind: experiment
  step_kind: verify
  step_status: open
related:
  - artifact/dirty/non-verify
  - artifact/restore
examples:
  - step/verify/close
---

[언제 읽는가]
  Experiment Cycle 에서 verify 자리가 열려 있고, 가설대로 실행을 마쳤을 때.
  파일을 바꿨고 그 변경을 세계로 남겨야 할 때.

[지금 할 일]
  Report 에 이 자리가 요구하는 칸을 적어 닫는다.

{{close_requires:experiment/verify}}

[불변식]
  Verify 를 닫는 순간 지금 프로젝트 폴더가 관측되어 Artifact 세계로 확정된다.
  세계를 확정할 권한은 Verify 에만 있다. 그 밖의 자리는 세계가 바뀌지 않았을 때만 닫힌다.
  같은 세계를 다시 확정하면 새 이름이 나지 않는다 — 기존 Snapshot 이름을 그대로 쓴다.
  아무것도 바꾸지 않은 Verify 도 정상적으로 닫힌다.
  Verify 에는 verdict 가 없다. 관측한 것을 적을 뿐, 성공인지 실패인지는 여기서 말하지 않는다.
  가설과 맞는지 읽는 것은 analysis 이고, 이 Cycle 을 판정하는 것은 outcome 이다.

[올바른 예]
      gil close <<'EOF'
      execution: 가설대로 캐시 계층을 넣고 같은 부하를 다시 걸었다
      result: p95 가 420ms 에서 180ms 로 내려갔고 오류율은 그대로였다
      EOF

  닫히면 그 자리와 확정된 세계를 알려 준다. 지금 세계는 gil status 로 다시 볼 수 있다.

[흔한 실패]
  Verify 에 성패 판정을 적으려는 것.

      verdict: success

  거절된다. verdict 는 outcome 의 칸이다. Verify 는 무엇을 했고 무엇이 보였는지만 적는다.

[관련 주제]
  artifact/dirty/non-verify
  artifact/restore
