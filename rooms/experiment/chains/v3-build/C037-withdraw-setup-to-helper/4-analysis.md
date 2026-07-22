# 4. 결과 분석

## 통계적 결과

| 측정 | 기준 | 실측 | 판정 |
|---|---|---|---|
| M1 crash 소멸 | 게이트 없이 1476 crash 안 함 | crash 1476(withdraw)→**92(guard `_seal_closed`)** | **PASS** |
| M2 전진 | 통과 84에서↑ | **84→106** (+22) | **PASS** |
| M3 판정 불변 | withdraw 3항목 게이트 상속 PASS | RETRACTS·REJECTS-CLOSED·ATOMIC 전부 PASS | **PASS** |
| M4 회계 | 게이트 상속 121 유지 | **121/121 ✔** | **PASS** |
| M5 다음 crash 좌표 | crash 위치 기록 | guard 섹션(~1832) | **기록** |

## 데이터 직접 관찰

**셋업 교체 3형태 (실측):**
- RETRACTS·ATOMIC: `open --git` → `write_cycle(step=1)` + git commit. 사이클 1커밋 = withdraw revert 대상 동일.
- REJECTS-CLOSED: `open+step×5+close`(7 gil 호출) → `write_cycle(status=closed, step=5)` + git commit + `git tag cycle/demo/C001-to-seal`(1 헬퍼+2 git). **닫힌 사이클 = write_cycle(closed) + 봉인 태그**로 재현(C036 close-seal 실증 재사용).

**WITHDRAW-RETRACTS의 Revert 검증이 헬퍼 위에서도 통과:** RETRACTS는 `not os.path.isdir(cdir)`(withdraw가 디렉토리 소멸) + Revert 커밋 각인을 확인. write_cycle이 만든 사이클을 withdraw가 revert해 디렉토리를 지우고 Revert 커밋을 남김 — **withdraw는 "무엇이 사이클을 만들었나"(open vs write_cycle)와 무관하게 마지막 사이클 커밋을 revert**. 셋업 수단 독립성 재확인.

**crash 이동 사슬 확장 (C034~C037):** open(330)→close(619)→step(1342)→withdraw(1476)→**guard(92)**. 다섯 번째 벗김.

## 예상과 달랐던 것

1. **+22, C036(+9)보다 크다.** withdraw crash가 그 뒤 web·fsck·deploy·releases 등 다수 섹션을 막고 있었다(전부 write_cycle 셋업이라 v2 open 무관 — crash만 없으면 통과). **crash 제거 파급은 하류에 write_cycle 섹션이 많을수록 크다** — withdraw 뒤가 그랬다.

2. **REJECTS-CLOSED 셋업이 7 gil 호출 → 3 헬퍼 호출로 단순화.** open+step×5+close를 write_cycle(closed)+태그로 대체하니 셋업이 짧아지고 게이트-독립. **헬퍼 교체는 crash 해소만이 아니라 셋업 간결화** — gil을 순차로 여러 번 부르던 걸 상태 직접 구성으로.

## 판정

**가설 채택 (supported).** 기각조건 대조:

- 기각조건 1 (Revert 검증 다른 결과)? **아님** — RETRACTS PASS, withdraw가 헬퍼 커밋을 정상 revert.
- 기각조건 2 (닫힌 사이클 재현 못 함)? **아님** — write_cycle(closed)+태그가 봉인 재현, REJECTS-CLOSED PASS.
- 기각조건 3 (withdraw 항목 FAIL)? **아님** — 3항목 전부 PASS.
- 기각조건 4 (전진 실패)? **아님** — 84→106.

**핵심 결론**: 게이트 없이 84→106 전진(누적 0→40→75→84→106). withdraw 셋업 open을 헬퍼로 교체해 crash를 guard로 밀었다. C035 패턴이 기계적으로 재현됨(판정 의미 불변). **다음 관문**: guard 섹션(C050 병렬 안전) — 셋업이 아니라 open guard 검사라 v3 open에 guard 부착 + V3-GUARD-* 재작성(제거 아님, 안전은 버전 무관). guard를 넘으면 판정기 끝(2020)이 가깝다 — 게이트 없이 완전 초록 = GIL_V2_OPEN 제거의 문턱.
