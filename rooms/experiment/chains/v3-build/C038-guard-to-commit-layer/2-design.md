# 2. 실험 설계

## 접근 확정 — guard 검사를 open이 아니라 correct(author-경로)로

1-hypothesis 실측 두 개가 접근을 확정했다:

- **게이트 없이 v2 open은 owner·intruder 무관 전부 은퇴 안내로 거부** → guard를 v2
  open으로 검사하면 은퇴가 guard를 가려 검사 의미가 붕괴한다.
- **correct는 guard를 태우고 v2 은퇴에 독립**(격리 실측): `correct --author intruder`는
  "owner-x의 주 작업공간이다" guard 거부, `correct --author owner-x`는 guard 통과(그
  다음 필드 검증에서 걸림 = guard는 넘었다는 증거).

**핵심 통찰(C032 연장)**: guard는 "open의 기능"이 아니라 커밋-층 계약("author가 이 주
체크아웃에 커밋할 자격이 있는가")이다. `_guard_primary_owner(repo, author)`는 순수 함수로
이미 open과 분리, open·correct 두 진입점서 호출. v2 open이 은퇴해도 guard 계약은
correct라는 살아있는 author-경로로 온전히 검증된다.

## 절차

1. **GUARD-OWNER-OK 셋업 헬퍼화**: owner-x `open --git`→`_seal_closed`(1840, crash원)를
   `write_cycle(gd, "demo", "C001-mine", status="closed", step=5, author="owner-x")` +
   `gdg("add","-A"); gdg("commit")` + `git tag cycle/demo/C001-mine`로 대체
   (C037 REJECTS-CLOSED 패턴 재사용).
2. **GUARD-PRIMARY-REFUSE 재작성**: intruder `open` 거부 검사를 intruder `correct
   demo/C001-mine --author intruder` 거부 검사로 — guard 거부 메시지("주 작업공간")를
   확인해 은퇴 우연 통과와 구별.
3. **GUARD-OWNER-OK 검사 재작성**: owner-x `correct`가 guard를 미거부(거부 메시지 부재)
   확인. correct는 필드 검증서 걸려도 guard는 넘음.
4. **GUARD-LINKED-OK 재작성**: 링크드 워크트리에서 someone `correct`가 guard 미거부.
5. **GUARD-RESERVED-OK/AUTHOR 이월**: 예약 예외는 open 전용(correct 미적용) → v3 open이
   author·예약 미수용이라 검사 표면 없음. 좌표만 찍고 이월(매듭 순서 2번 예약 섹션과 통합).
6. 배포판 conformance.py에 적용, 게이트 상속(121/121)·게이트 없이(통과 수·crash 좌표) 측정.

## 준비물

- 배포판 `rooms/deployment/ariadne-spec/{conformance.py,gil.py}` (gil.py 무변경 목표)
- Python 3.9, git. 헬퍼 `write_cycle`·`_seal_closed`·`make_sandbox` (conformance.py 내장)
- 실행: `python3 conformance.py --gil "python3 …/gil.py"` (게이트 없이) /
  `GIL_V2_OPEN=1 …` (게이트 상속)

## 측정 방법

- **M1 crash 소멸**: 게이트 없이 crash가 guard(~1832)를 넘어 다음 좌표로 이동. 기준=이동.
- **M2 게이트 없이 통과**: 106 → 증가. 기준=증가.
- **M3 guard 은퇴 독립**: PRIMARY-REFUSE가 게이트 없이 guard 거부 메시지로 PASS(은퇴
  우연 아님). 기준=거부 메시지 존재.
- **M4 무회귀**: 게이트 상속 conformance 121/121. 기준=불변.
- **M5 다음 좌표**: crash 밀린 지점 기록.

## 사용자 컨펌

- 상현님 자율 위임("지금부터 판단 위임, 물어보지 말고 자율 사이클 계속. gil v3 쓸 수
  있을 때 불러줘"). GUARD v3 이전은 매듭 순서 1번, AskUserQuestion 선제 응답으로
  자율 승인됨. 접근 B(커밋-층/author-경로)를 판단으로 채택.
- [x] 컨펌 받음 (일자: 2026-07-22, 자율 위임)
