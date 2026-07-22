# 4. 결과 분석

## 통계적 결과

| 측정 | 기준 | 결과 | 판정 |
|---|---|---|---|
| M1 crash 소멸 | crash가 guard(~1832) 넘어 이동 | **Traceback 0 — crash 완전 소멸, 끝까지 완주** | PASS(초과달성) |
| M2 게이트 없이 통과 | 106 → 증가 | 106 → **109**(+3) | PASS |
| M3 guard 은퇴 독립 | guard 거부 메시지로 PASS | PRIMARY-REFUSE 지문("주 작업공간")으로 PASS | PASS |
| M4 무회귀 | 게이트 상속 121/121 | **121/121** | PASS |
| M5 다음 좌표 | crash 밀린 지점 | crash 소멸 → 12개 병렬 FAIL 목록 | 확정 |

## 데이터 직접 관찰

**M1이 예상(crash 이동)을 넘어 crash 완전 소멸로 나왔다.** C034~C037은 crash를 판정기
뒤로 한 겹씩 밀었을 뿐(open→close→step→withdraw→guard) 매번 다음 crash가 있었다. 그런데
guard 셋업을 write_cycle로 바꾸고 나니 `grep -c Traceback log-gateless.txt`가 **0**.
판정기가 처음으로 게이트 없이 끝(2020)까지 예외 없이 완주한다. 데이터로 확인: 이전
crash 사슬의 마지막 고리(guard 92)가 끊기자 뒤에 더 이상 v2 open을 **파일 읽기로 즉시
소비하는** 셋업이 없었다 — 남은 v2 open 결합은 전부 종료코드만 보는 FAIL 항목이었다.

**M3의 은퇴 독립을 지문으로 증명.** 게이트 없이 PRIMARY-REFUSE가 PASS인데, 만약 correct가
아니라 open이었다면 "gil open은 이제 v3"라는 **은퇴 안내**로 rc≠0이 되어 검사가 우연히
초록이 됐을 것이다(guard를 검사하는 게 아니라 은퇴를 검사). correct는 v3에서 은퇴하지
않으므로 rc≠0이 오직 guard에서만 오고, 로그의 거부 메시지가 "…owner-x의 주 작업공간이다
— author 'intruder'로 여기서 커밋할 수 없다"임을 지문으로 확인. **guard가 실제로 탔다.**

**M4 회귀는 계측기 오염, 반증 아님.** 첫 실행 120/121의 유일 FAIL은 승격 결함이 아니라
write_cycle에 `closed` 날짜를 안 줘 C001-mine이 R8 위반(status closed인데 closed null)
→ reserve가 fsck에서 거부 → 예약 없어 alice open이 guard 거부. `closed="2026-01-02"`
추가로 즉시 121/121. Weft·Bobbin "계측기 vs 반증 구분"의 헬퍼-인자판 — 셋업 헬퍼가
fsck 계약을 안 지키면 하류 검사가 무너진다.

## 예상과 달랐던 것

- **crash가 "밀리는" 게 아니라 "소멸"했다.** C034~C037의 정신모델(crash를 뒤로 미는
  사슬)이 여기서 종결됐다. crash 이동 사슬은 "v2 open을 즉시 파일로 소비하는 셋업"의
  목록이었고, 그게 다 떨어지자 사슬 자체가 끝났다. **다음 정신모델은 "crash 최전선"이
  아니라 "게이트 없이 남은 FAIL 목록"** — 순차 crash가 아니라 병렬로 처리 가능한 12항목.
- **guard는 open이 아니라 커밋-층 계약이었다(설계 가정 실증).** correct가 guard를 태운다는
  실측이 접근 전체를 지탱했다. "guard = open의 기능" 정신모델을 버리고 "guard = author의
  커밋 자격"으로 보니, v2 open 은퇴가 guard 검증을 못 막는다. C032 "인터페이스 정체성
  전환"의 guard판: 인터페이스(open→correct)는 바뀌어도 계약(주 체크아웃 소유)은 불변.

## 판정

**채택 (supported).** 가설대로 셋업 헬퍼화 + guard 검사를 author-경로로 재작성하니
게이트 없이 crash가 소멸하고(기준 초과), 통과 106→109, 게이트 상속 121/121 유지, guard가
v2 open 은퇴에 독립해 C050 안전이 버전 무관하게 검증됐다. 기각조건 셋 다 불충족:
① crash가 guard 자리에 안 남음(소멸) · ② correct가 guard를 탐(접근 유효) · ③ 121/121 유지.

**정직한 경계**: GUARD-RESERVED-OK는 게이트 없이 FAIL로 이월 — 예약 예외는 open 전용
(correct 미적용)이라 v3 open이 author·예약을 받기 전엔 검사 표면이 없다. RESERVED-*는
게이트 상속 하에선 여전히 v2 open으로 PASS. gil.py 무변경(conformance만). guard 함수
자체(`_guard_primary_owner`)는 이 사이클에서 안 건드림 — 살아있는 계약을 검사 경로만
v3화했다.
