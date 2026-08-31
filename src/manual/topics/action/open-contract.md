---
id: action/open-contract
title: 실행형 자리를 열 때 적는 행동 계약
summary: 지금 무엇을 하려는지 세 칸으로 적어야 실행형 Step 이 열린다. GIL 은 그 내용을 지어내지 않는다.
applies_when:
  project: present
  step_status: none
related:
  - current
---

[언제 읽는가]
  `gil open <종류>` 가 「무엇을 하려는지 적지 않았다」로 거절했을 때.
  세 칸 중 하나가 없거나 비어 있다고 거절당했을 때.

[지금 할 일]
  지금 열려는 그 행동을 세 칸으로 적어 stdin 으로 넘긴다.

      gil open <종류> <<'EOF'
      objective: …
      next_action: …
      done_when: …
      EOF

  칸은 이것뿐이다.

{{open_requires}}

[불변식]
  objective    이 행동이 풀려는 **한 가지** 목적
  next_action  지금 실제 세계에서 수행할 **바로 다음** 행동
  done_when    이 행동을 닫을 수 있는 **관측 가능한** 완료 조건

  세 칸 모두 비울 수 없다. 공백만 적은 것도 빈 것이다.
  하나의 자리에는 하나의 행동만 적는다 — 걸리는 Will 도 하나다.
  Cycle 을 여는 것(`gil open experiment` 같은 컨테이너)에는 계약이 필요 없다.

  **GIL 은 이 세 문장을 지어내지 않는다.** 종류 이름은 *무엇을* 할지 모른다.

[올바른 예]
      objective: 예약 실패가 재고를 바꾸는 책임 지점을 검증한다
      next_action: 공개 테스트와 acceptance 를 실행해 수정 전 실패 상태를 관측한다
      done_when: 실패한 요청 전후의 재고와 원장을 비교한 결과를 확보한다

[흔한 실패]
      next_action: gil close
      done_when: 작업을 완료한다

  `next_action` 에 GIL 명령을 적었다. GIL 명령은 기록하는 수단이지 실제 세계에서 하는
  일이 아니다. 여기 적는 것은 **폴더와 코드와 사람에게 하는 일**이다.

  `done_when` 이 「완료한다」로 자기를 가리킨다. 그러면 무엇을 보아야 닫을 수 있는지
  누구도 판정할 수 없다. **무엇이 손에 들어오면 끝인지**를 적는다.

[관련 주제]
  current
