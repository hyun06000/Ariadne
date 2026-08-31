---
id: current
title: 지금 어디에서 이어 갈 것인가
summary: 새 세션은 gil context 로 복원하고, 같은 세션은 명령이 준 다음 수를 따른다. 전체 명세를 먼저 읽지 않는다.
related:
  - artifact/restore
---

[언제 읽는가]
  GIL 프로젝트를 처음 만났거나, 세션이 끊겨 지금 무엇을 하던 중이었는지 모를 때.

[지금 할 일]
  세션이 바뀌었다면 — 지금 이어받을 행동을 복원한다.

      gil context

  같은 세션 안이라면 — 방금 명령이 준 다음 수를 그대로 따른다. context 를 다시 읽지 않는다.

  지금 자리와 세계만 짧게 보고 싶다면 —

      gil status

[불변식]
  한 번에 하나의 행동만 열려 있다.
  전체 명세를 먼저 읽지 않는다. 필요한 규칙 하나가 생긴 순간에 그 주소 하나를 읽는다.
  gil context 는 온보딩이고 gil status 는 지금 자리의 짧은 표시다. 둘을 바꿔 쓰지 않는다.

[올바른 예]
  새 세션:

      gil context

  이어 걷는 중:

      gil status

[흔한 실패]
  같은 세션에서 명령마다 gil context 를 다시 부르는 것.
  context 는 이어받을 때 한 번 읽는 것이고, 그 뒤에는 각 명령의 receipt 가 다음 수를 말한다.

[관련 주제]
  artifact/restore
