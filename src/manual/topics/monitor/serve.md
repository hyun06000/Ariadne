---
id: monitor/serve
title: browser 로 지금 상태를 계속 지켜본다
offered: false
summary: loopback 주소 하나를 열어 지금 Cycle·Step·Will·세계를 browser 에서 읽는다. 읽기만 하고, 그 주소는 이 실행 동안만 산다.
related:
  - current
  - artifact/restore
---

[언제 읽는가]
  작업하는 동안 지금 어디에 서 있는지를 옆에 띄워 두고 싶을 때.
  `gil monitor` 를 계속 다시 치고 있을 때.

[지금 할 일]
      gil monitor --serve

  주소 한 줄이 나온다. 그것을 browser 에 붙여 넣는다.

      GIL Monitor가 이 주소에서 현재 프로젝트를 보여 준다.
      http://127.0.0.1:54321/<이 실행의 주소>

      이 주소는 이 실행 동안만 유효하다.
      종료하려면 Ctrl-C.

[불변식]
  읽기 전용이다. 이 화면에서 여는 것도 닫는 것도 되돌리는 것도 없다.
  browser 를 열어 주지 않는다. 어느 browser 로 열지는 사람이 정한다.
  주소는 실행할 때마다 새로 만들어지고, 끝내면 그 주소는 죽는다.
  그 주소를 아는 것이 이 프로젝트를 보는 권한이다 — 채팅·이슈·화면 공유에 붙여 넣지 않는다.
  이 컴퓨터 밖에서는 닿지 않는다. 같은 네트워크의 다른 기계도 마찬가지다.
  파일이나 `state.yaml` 이 바뀌면 화면이 스스로 따라온다. 바뀐 것이 없으면 다시 읽지 않는다.
  Ctrl-C 로 끝낸다. 끝내면 화면도 주소도 사라지고, 프로젝트에는 아무것도 남지 않는다.

[올바른 예]
      gil monitor --serve

  한 번만 읽고 끝낼 것이라면 지켜볼 필요가 없다.

      gil monitor
      gil monitor --html

[틀린 예]
      gil monitor --serve &

  뒤로 보내면 끝내는 방법을 잃는다. 앞에서 돌리고 Ctrl-C 로 끝낸다.
