# 1. 가설 수립

## 이전 사이클의 교훈

부모 **C037**(withdraw 셋업 open→헬퍼). 버전리스 여정이 crash 최전선을
open(330)→close(619)→step(1342)→withdraw(1476)→**guard(~1832)** 로 밀어왔다.
게이트 없이 통과 항목이 0→40→75→84→**106**까지 올라왔다. 게이트 상속 시
conformance는 121/121 유지. gil.py는 C032 이후 무변경(conformance만 수정).

확립된 두 패턴: ① **셋업 open→헬퍼 교체**(C035·C037, open이 셋업일 뿐인 검사) —
write_cycle+git으로 대체, 판정 의미 불변. ② **v2 전용 검사 제거**(C034·C036,
"사이클-간을 보는가" 판별) — v3 대응 없으면 제거.

## 문제 분할

GUARD 섹션(conformance.py 1816~1867)을 실측 분류하니 앞선 두 패턴이 **둘 다
그대로는 안 맞는다**:

- **GUARD-OWNER-OK**(1837): owner-x open으로 C001-mine 생성 → 후속 `_seal_closed`(1840)가
  그 사이클을 읽음. 게이트 없이 v2 open이 은퇴 안내로 거부 → cycle.yaml 없음 →
  **현 crash원**(line 92). 이건 셋업 성격 → 패턴①(헬퍼) 적용 가능.
- **GUARD-PRIMARY-REFUSE / LINKED-OK / RESERVED-OK / RESERVED-AUTHOR**: guard 동작
  자체(author≠owner 거부, 워크트리 통과, 예약 예외)를 검사 → **셋업 아님, 검사 대상**.
  패턴①도 ②도 부적합 — C050 안전은 버전 무관하게 살아야 하므로 제거 불가.

**결정적 실측**(격리 재현): 게이트 없이는 owner-x·intruder open **둘 다 은퇴 안내로
거부**된다(v2 open 자체 은퇴). 따라서 PRIMARY-REFUSE는 게이트 없이 "우연히 통과"하되
guard가 아니라 **은퇴 때문에** 통과 — 검사 의미가 붕괴한다. **guard 검사는 v2 open
인터페이스 위에 지어져 있어, v2 open이 은퇴하면 이 경로로는 guard를 검증할 수 없다.**

첫 정복 문제: **crash를 없애면서 guard 동작 검사를 v2 open 은퇴에 독립시킨다.**
guard 함수(`_guard_primary_owner`)는 순수 (repo, author) 함수라 open과 이미 분리돼
있다 — open을 경유하지 않고 **author를 받는 살아있는 경로**로 guard를 직접 검사하면
v2 은퇴와 무관해진다. 후보 경로: `gil correct`(3252서 guard 호출, author 필수, v3
계약에서 살아남음)로 guard 동작을 검사.

## 가설

> **가설**: GUARD-OWNER-OK가 만들던 셋업 사이클을 write_cycle 헬퍼로 대체(패턴①)하고,
> guard 동작 검사(PRIMARY-REFUSE·RESERVED-*)를 v2 open이 아니라 **살아있는
> author-경로(correct 또는 v3 커밋)로 재작성**하면, 게이트 없이 crash가 guard(~1832)를
> 넘어 다음 좌표로 밀리고(통과 106→증가), 게이트 상속 시 conformance 121/121이 유지되며,
> guard 검사가 v2 open 은퇴에 독립해 C050 안전이 버전 무관하게 검증된다.

## 기각 조건

1. 셋업 헬퍼화·검사 재작성 후에도 게이트 없이 crash가 guard 자리(~1832)에 그대로면 →
   crash원 진단이 틀렸다(기각).
2. guard를 author-경로로 검사할 수 없다면(correct/v3 커밋 어느 것도 guard를 안 태움) →
   "guard가 open 인터페이스에 결합" 가정이 틀렸고 접근 재설계 필요(기각·좌표 이동).
3. 게이트 상속 시 121/121이 깨지면(무회귀 위반) → 재작성이 판정 의미를 바꿨다(기각).
