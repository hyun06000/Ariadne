---
id: artifact/restore
title: 작업 폴더를 기준 세계로 되돌린다
summary: 지금 위치가 요구하는 Snapshot 으로 파일만 되돌린다. 목표를 고르지 않고 Graph 와 Journey 는 건드리지 않는다.
applies_when:
  world_state: dirty
related:
  - artifact/dirty/non-verify
  - current
---

[언제 읽는가]
  파일을 바꿔 놓았는데 지금 자리에서 그 변경을 확정할 수 없어 막혔을 때.
  gil status 가 `상태: dirty` 라고 말할 때.

[지금 할 일]
      gil restore

  인수는 없다. 되돌아갈 세계는 지금 서 있는 자리가 이미 정한다.

[불변식]
  목표 Snapshot 을 인수로 고르지 않는다. 파일 하나만 고를 수도 없다.
  --force 도, 예/아니오 확인도, 먼저 실행해야 하는 status 도 없다 — 명령 실행 자체가 복원 의사다.
  Artifact 파일만 되돌린다. 현재 Step·Active Will·Journey·Graph·Snapshot registry 는 그대로다.
  되돌리는 것은 행동 취소가 아니다. 열려 있던 자리는 열린 채 남고, 하려던 일을 마친 뒤 정상 Report 로 닫는다.
  이미 기준 세계와 같으면 오류가 아니라 성공적인 no-op 이다.
  도중에 프로세스가 죽어도 다음 GIL 명령이 먼저 복구한 뒤에야 진행한다.

[올바른 예]
      gil restore

  성공하면 되돌린 Snapshot 이름과 교체·생성·삭제한 개수, 그리고 그대로 열려 있는 자리와
  걸린 행동을 알려 준다.

      Artifact 세계를 snapshot:A2 로 복원했다.

      교체  2개
      생성  1개
      삭제  3개

[흔한 실패]
  되돌릴 Snapshot 을 인수로 적는 것.

      gil restore snapshot:A2

  거절된다. 목표는 고르는 값이 아니라 지금 위치에서 유도되는 값이다.

[관련 주제]
  artifact/dirty/non-verify
