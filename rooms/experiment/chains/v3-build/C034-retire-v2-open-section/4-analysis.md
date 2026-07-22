# 4. 결과 분석

## 통계적 결과

| 측정 | 기준(성공) | 실측 | 판정 |
|---|---|---|---|
| M1 crash 소멸 | 게이트 없이 line 330 crash 안 함 | crash 지점 330(open)→**619(close)** 이동, open 섹션 crash 소멸 | **PASS** |
| M2 게이트-독립 전진 | 게이트 없이 통과 항목 crash(0)에서 늘어남 | 게이트 없이 **40항목 PASS** | **PASS** |
| M3 open-git 잔여 | open-git 섹션 게이트 없이 crash하는지 | crash 지점이 close(619)라 open-git(1368) 도달 전 — 미도달 | **이월** |
| M4 v3 이동 생존 | 이동한 v3 3항목 새 위치서 PASS | V3-OPEN-CREATE·REJECT-EXISTING·RETIRE-GUIDANCE 전부 PASS | **PASS** |
| M5 회계 | 게이트 상속 총 = 137−10=127 | **127/127 ✔** | **PASS** |

## 데이터 직접 관찰

**crash 지점 이동 (M1의 실물):**
```
# C034 전 (게이트 없이): line 330 _seal_closed — 첫 v2 open 실패
# C034 후 (게이트 없이): line 619 close 섹션 — write_cycle 사이클에 5-report.md 없어서
FileNotFoundError: .../close-seal/rooms/experiment/chains/demo/C001-cyc/5-report.md
```
open 섹션의 v2 open crash가 **완전히 제거**됐고, 판정기가 open·예약·라운드를 넘어 close까지 진행한다. 새 crash(close, line 619)는 v2 open과 무관한 **별개 결합** — write_cycle이 만든 사이클을 close 테스트가 5-report 없이 봉인하려다 나는 것(다음 카브 좌표).

**게이트 없이 FAIL 항목들 (M2의 강등 — crash 아니라 정상 FAIL):**
- OPEN-SKIPS-RESERVED·OPEN-PROMOTES-OWNER·OPEN-LAST-RESERVATION-GIT (예약 섹션, `impl.run(..., "open", ...)` 호출 → 게이트 없이 은퇴 안내 → rc=1 FAIL)
- ROUND-OPEN·ROUND-OPEN-GIT·ROUND-CLOSE-VERDICT·ROUND-LIST-SAFE·FSCK-R15 (라운드는 v2 open으로 사이클 만든 뒤 round 테스트)

이들은 **crash에서 FAIL로 강등**됐다 — 판정기가 무너지지 않고 계속 진행하며 정직히 FAIL을 보고한다. C033 M5의 "crash가 전체를 무너뜨림"이 여기선 국소 FAIL로 격하됐다.

**회계 (M5):** 137 − 10(제거한 v2 open 항목) = 127. v3 3항목은 이미 137에 셈됨(C033), 이동만 했으니 순감 없음. **127/127 = 정확한 회계** — 제거지 회귀 아님.

## 예상과 달랐던 것

1. **crash가 사라진 게 아니라 "밀렸다".** 설계 시 open 섹션 제거로 게이트 없이 훨씬 멀리 가리라 봤고 맞았으나(open→close), crash가 완전히 소멸한 건 아니다. close 섹션의 **write_cycle+5-report 결합**이 새 crash원. v2 결합은 open 호출 층(C034가 처리)과 write_cycle 산출물 층(다음 카브)의 **두 겹**이었다 — C034가 첫 겹을 벗겼다.

2. **예약·라운드 항목이 crash 아니라 FAIL로 강등된 게 중요하다.** 이들도 v2 open을 호출하지만, open 섹션과 달리 그 결과를 `_seal_closed` 같은 후속 파일 읽기로 바로 안 쓰기에 crash 대신 rc=1 FAIL. **판정기가 v2 open 호출을 견디는 정도가 섹션마다 다르다** — 파일 읽기가 뒤따르면 crash, 종료코드만 보면 FAIL. 게이트-독립 완성은 이 FAIL 항목들도 v3로 재작성해야.

## 판정

**가설 채택 (supported).** 기각조건 대조:

- 기각조건 1 (open-git 잔여 crash)? **미도달** — crash가 close(619)라 open-git(1368) 전에 멈춤. open-git은 close 카브 후 드러남(정직히 이월).
- 기각조건 2 (write_cycle 층 v2 결합)? **부분 참 — 반증 아니라 다음 겹의 실증.** close 섹션이 write_cycle+5-report로 게이트 없이 crash. 그러나 이는 **v2 결합의 두 번째 겹**이지 C034 조각(open 호출 층)의 실패가 아니다. C034가 첫 겹을 정확히 벗겼다(crash 330→619).
- 기각조건 3 (v3 이동 FAIL)? **아님** — v3 3항목 새 위치서 PASS.
- 기각조건 4 (설명 안 되는 감소)? **아님** — 137−10=127 정확한 회계.

**핵심 결론**: **버전리스의 실질 전진.** v2 open 섹션을 실제 제거해(전진 삭제) 게이트 없이 crash하던 근원을 없앴다 — 판정기가 open을 넘어 close까지 진행하고, 게이트 없이 40항목이 통과한다(crash 때 0). 회계 정확(137→127). 동시에 **다음 관문**이 실측으로 드러났다: v2 결합은 두 겹(open 호출 + write_cycle 산출물)이고, close 섹션의 write_cycle+5-report가 다음 crash원이다. C034가 첫 겹을 벗겼고 다음 겹의 좌표를 찍었다 — 상현님 "전진 삭제"를 crash 근원부터 작은 확실함으로.
